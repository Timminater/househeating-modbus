"""Optional observed diagnostics and explicitly authorized weather compensation."""
import asyncio
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import logging
from math import isfinite
from time import monotonic, time

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

from househeating_modbus.operation import CurveConfig, CurveModel, OperationLedger, relay_value
from househeating_modbus.telemetry import valid_reading
from .monitoring import source_reading

_LOGGER=logging.getLogger(__name__)
MODES={"heating_setpoint":(1,5),"floor_setpoint":(3,7),"dhw_setpoint":(2,),"cooling_setpoint":(0,)}
NATIVE_CURVES={"heating_setpoint":"heating_curve","floor_setpoint":"floor_curve","dhw_setpoint":"dhw_curve","cooling_setpoint":"cooling_curve"}


class OperationManager:
    def __init__(self,hass,coordinator):
        self.hass,self.coordinator=hass,coordinator
        options=coordinator.entry.options
        self.statistics=bool(options.get("operation_statistics",False))
        self.config=CurveConfig.from_options(options)
        self.model=CurveModel(self.config)
        self.max_age=max(90,2.5*coordinator.update_interval.total_seconds())
        self.ledger=OperationLedger(hass.config.time_zone,self.max_age)
        self.store=Store(hass,1,f"househeating.operation.{coordinator.entry.entry_id}")
        self.command_store=Store(hass,1,f"househeating.curve_safety.{coordinator.entry.entry_id}")
        self.lock=asyncio.Lock()
        self.unsub=[]
        self.task=None
        self.closed=False
        self.running=False
        self.started=time()
        self.last_command=None
        self.last_attempt=None
        self.blocked=False
        self.values_cache={"curve_status":"disabled"}
        self.storage_error=False

    async def async_load(self):
        if self.statistics:
            state=await self.store.async_load()
            if state:
                self.ledger=OperationLedger(self.hass.config.time_zone,self.max_age,state)
        if self.config.automatic:
            command=await self.command_store.async_load()
            if command and command.get("confirmation_id")==self.config.confirmation_id:
                self.blocked=bool(command.get("pending"))
                self.last_command=command.get("last_command")
                at=command.get("at")
                if at is not None:
                    if not isinstance(at,(int,float)) or not isfinite(at) or not 0<=time()-at:
                        self.blocked=True
                    else:
                        self.last_attempt=monotonic()-(time()-at)
                if self.last_command is not None and (not isinstance(self.last_command,(int,float)) or not isfinite(self.last_command)):
                    self.blocked=True
                if self.blocked:
                    self.values_cache={"curve_status":"write_error"}

    def start(self):
        self.running=True
        if self.config.enabled:
            sources=[s for s in (self.config.outdoor_entity,self.config.pv_entity,self.config.battery_entity) if s]
            if sources:
                self.unsub.append(async_track_state_change_event(self.hass,sources,self._event))
            self.unsub.append(async_track_time_interval(self.hass,self._event,timedelta(seconds=30)))
            self._queue()

    @callback
    def _event(self,_):
        self._queue()

    def _queue(self):
        if self.running and not self.closed and self.config.enabled and (self.task is None or self.task.done()):
            self.task=self.hass.async_create_task(self.async_evaluate(),"HouseHeating weather curve")

    async def async_snapshot(self,snapshot):
        if self.closed:
            return
        if self.statistics:
            async with self.lock:
                value=relay_value(snapshot,"compressor_active",self.max_age)
                candidate=deepcopy(self.ledger)
                if self.storage_error:
                    candidate.previous=None
                    candidate.cycle_seconds=None
                window=snapshot.samples.get(0x1A) if snapshot else None
                at=window.end if window and value is not None else time()
                clock=window.monotonic_end if window and value is not None else monotonic()
                candidate.ingest(at,clock,value)
                try:
                    await self.store.async_save(candidate.export())
                except Exception:
                    self.storage_error=True
                    _LOGGER.exception("Could not persist HouseHeating observed diagnostics")
                else:
                    self.ledger=candidate
                    self.storage_error=False
        self._queue()

    def _external(self,entity,kind):
        state=self.hass.states.get(entity)
        if state is None or state.attributes.get("restored") or state.last_reported.timestamp()<self.started:
            return None
        if kind=="power":
            reading=source_reading(state,"power")
            return reading.value if valid_reading(reading,time(),self.config.max_age) else None
        try:
            value=float(state.state)
        except (TypeError,ValueError):
            return None
        if not isfinite(value) or not 0<=time()-state.last_reported.timestamp()<=self.config.max_age:
            return None
        unit=state.attributes.get("unit_of_measurement")
        device_class=state.attributes.get("device_class")
        if kind=="temperature" and device_class=="temperature" and unit in ("°C","°F","K"):
            return (value-32)*5/9 if unit=="°F" else value-273.15 if unit=="K" else value
        if kind=="battery" and device_class=="battery" and unit=="%" and 0<=value<=100:
            return value
        return None

    def _outdoor(self,snapshot):
        if self.config.outdoor_entity:
            return self._external(self.config.outdoor_entity,"temperature")
        if not snapshot:
            return None
        if not self.coordinator.last_update_success or not self.coordinator.device.unit.connected:
            return None
        window=snapshot.samples.get(0x4A)
        if not window or not 0<=time()-window.end<=self.config.max_age or not 0<=monotonic()-window.monotonic_end<=self.config.max_age:
            return None
        return snapshot.value("outdoor_temperature",self.coordinator.device.config)

    def _advice(self,snapshot):
        outdoor=self._outdoor(snapshot)
        if outdoor is None:
            raise ValueError("Outdoor source unavailable")
        pv=self._external(self.config.pv_entity,"power") if self.config.pv_entity else None
        battery=self._external(self.config.battery_entity,"battery") if self.config.battery_entity else None
        return self.model.calculate(outdoor,pv,battery,monotonic(),self.coordinator.device.config.limits(self.config.target))

    async def async_evaluate(self):
        if self.closed or not self.config.enabled:
            return
        if self.blocked:
            return
        snapshot=self.coordinator.device.snapshot
        try:
            advice=self._advice(snapshot)
        except ValueError:
            self.model.reset()
            self.values_cache={"curve_status":"source_unavailable"}
            self.coordinator.async_update_listeners()
            return
        self.values_cache=advice|{"curve_status":"advisory"}
        if self.config.automatic:
            if not self.coordinator.device.control_ready:
                self.values_cache["curve_status"]="control_locked"
            else:
                try:
                    # Persist an inhibit before any possible write. An interrupted
                    # process cannot silently retry the same uncertain command.
                    await self.command_store.async_save({"confirmation_id":self.config.confirmation_id,
                        "pending":True,"last_command":self.last_command,"at":time()})
                    # Use the same command lock, fresh validation, allowlist and
                    # readback as the UI. Never call unit.write_register here.
                    def plan(fresh):
                        if self.closed:
                            return []
                        result=self._advice(fresh)
                        self.values_cache.update(result)
                        if fresh.raw.get(0x305)!=1 or fresh.raw.get(0x304) not in MODES[self.config.target]:
                            self.values_cache["curve_status"]="inactive_mode"
                            return []
                        native=NATIVE_CURVES[self.config.target]
                        reg=self.coordinator.device.snapshot.value(native,self.coordinator.device.config)
                        window=fresh.samples.get({"heating_curve":0x314,"floor_curve":0x316,"dhw_curve":0x315,"cooling_curve":0x313}[native])
                        if reg!=0 or window is None or not 0<=time()-window.end<=self.max_age:
                            self.values_cache["curve_status"]="native_curve_active"
                            return []
                        current=fresh.value(self.config.target,self.coordinator.device.config)
                        if self.last_command is not None and current!=self.last_command:
                            self.blocked=True
                            self.values_cache["curve_status"]="manual_override"
                            return []
                        target=result["curve_advised_target"]
                        if self.last_attempt is not None and monotonic()-self.last_attempt<self.config.cooldown_seconds:
                            self.values_cache["curve_status"]="cooldown"
                            return []
                        if current is None or abs(current-target)<self.config.step_degrees:
                            self.values_cache["curve_status"]="unchanged"
                            return []
                        self.last_attempt=monotonic()
                        self.last_command=target
                        self.values_cache["curve_status"]="controlling"
                        return [(self.config.target,target)]
                    self.coordinator.force_optional=True
                    await self.coordinator.async_control(plan)
                    await self.command_store.async_save({"confirmation_id":self.config.confirmation_id,
                        "pending":self.blocked,"last_command":self.last_command,
                        "at":time()-(monotonic()-self.last_attempt) if self.last_attempt is not None else None})
                except Exception:
                    self.blocked=True
                    self.values_cache["curve_status"]="write_error"
                    _LOGGER.exception("Weather curve stopped after an unconfirmed command; no automatic retry")
        self.coordinator.async_update_listeners()

    def values(self):
        result=self.ledger.values(time()) if self.statistics else {}
        if self.config.enabled:
            result.update(self.values_cache)
        return result

    def diagnostics(self):
        return {"observed_statistics":self.ledger.export() if self.statistics else None,
                "storage_error":self.storage_error,"weather_curve":asdict(self.config),
                "values":self.values(),"latched_stop":self.blocked}

    async def async_close(self):
        self.closed=True
        for unsub in self.unsub:
            unsub()
        if self.task and not self.task.done():
            await self.task
        self.values_cache={"curve_status":"disabled"}
        # Every accepted statistics update is already persisted; do not
        # overwrite a good stored ledger with an uncommitted candidate.
