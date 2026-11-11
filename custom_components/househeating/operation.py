"""Optional observed diagnostics and explicitly authorized weather compensation."""

import asyncio
import logging
from dataclasses import asdict
from datetime import timedelta
from math import isfinite
from time import monotonic, time

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

from ._vendor.househeating_modbus.models import VerificationError
from ._vendor.househeating_modbus.operation import CurveConfig, CurveModel, OperationLedger, relay_value
from ._vendor.househeating_modbus.telemetry import valid_reading
from .listeners import ManagerListeners
from .monitoring import SAVE_INTERVAL, source_reading

_LOGGER = logging.getLogger(__name__)
MODES = {"heating_setpoint": (1, 5), "floor_setpoint": (3, 7), "dhw_setpoint": (2,), "cooling_setpoint": (0,)}
NATIVE_CURVES = {
    "heating_setpoint": "heating_curve",
    "floor_setpoint": "floor_curve",
    "dhw_setpoint": "dhw_curve",
    "cooling_setpoint": "cooling_curve",
}
CURVE_ADDRESSES = {"heating_curve": 0x314, "floor_curve": 0x316, "dhw_curve": 0x315, "cooling_curve": 0x313}


class OperationManager(ManagerListeners):
    def __init__(self, hass, coordinator):
        super().__init__()
        self.hass, self.coordinator = hass, coordinator
        options = coordinator.entry.options
        self.statistics = bool(options.get("operation_statistics", False))
        self.config = CurveConfig.from_options(options)
        self.model = CurveModel(self.config)
        self.max_age = max(90, 2.5 * coordinator.update_interval.total_seconds())
        self.ledger = OperationLedger(hass.config.time_zone, self.max_age)
        self.store = Store(hass, 1, f"househeating.operation.{coordinator.entry.entry_id}")
        self.command_store = Store(hass, 1, f"househeating.curve_safety.{coordinator.entry.entry_id}")
        self.lock = asyncio.Lock()
        self.unsub = []
        self.task = None
        self.closed = False
        self.running = False
        self.started = time()
        self.last_command = None
        self.last_attempt = None
        self.blocked = False
        self.values_cache = {"curve_status": "disabled"}
        self.storage_error = False
        self.storage_invalid = False
        self.save_interval = SAVE_INTERVAL
        self._saved_at = None
        self._retry_at = None
        self._stop_unsub = None

    async def async_load(self):
        if self.statistics:
            state = await self.store.async_load()
            if state:
                try:
                    self.ledger = OperationLedger(self.hass.config.time_zone, self.max_age, state)
                except (ValueError, TypeError, KeyError):
                    # Never overwrite unreadable stored statistics; report them instead.
                    _LOGGER.exception("Stored HouseHeating operation statistics are invalid; statistics disabled")
                    self.statistics = False
                    self.storage_invalid = True
        if self.config.automatic:
            command = await self.command_store.async_load()
            if command and command.get("confirmation_id") == self.config.confirmation_id:
                self.blocked = bool(command.get("pending"))
                self.last_command = command.get("last_command")
                at = command.get("at")
                if at is not None:
                    if not isinstance(at, (int, float)) or not isfinite(at) or not 0 <= time() - at:
                        self.blocked = True
                    else:
                        self.last_attempt = monotonic() - (time() - at)
                if self.last_command is not None and (
                    not isinstance(self.last_command, (int, float)) or not isfinite(self.last_command)
                ):
                    self.blocked = True
                if self.blocked:
                    self.values_cache = {"curve_status": "write_error"}

    def start(self):
        self.running = True
        if self.statistics:
            self._stop_unsub = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_handle_stop)
        if self.config.enabled:
            sources = [s for s in (self.config.outdoor_entity, self.config.pv_entity, self.config.battery_entity) if s]
            if sources:
                self.unsub.append(async_track_state_change_event(self.hass, sources, self._event))
            self.unsub.append(async_track_time_interval(self.hass, self._event, timedelta(seconds=30)))
            self._queue()

    def reopen(self):
        """Resume after an unload attempt that left the entry loaded."""
        self.closed = False
        self.unsub = []
        self.start()

    async def _async_handle_stop(self, _event):
        # Home Assistant does not unload entries on shutdown; persist here.
        self._stop_unsub = None
        async with self.lock:
            await self._async_save_statistics(force=True)

    @callback
    def _event(self, _):
        self._queue()

    def _queue(self):
        if self.running and not self.closed and self.config.enabled and (self.task is None or self.task.done()):
            self.task = self.hass.async_create_task(self.async_evaluate(), "HouseHeating weather curve")

    async def _async_save_statistics(self, *, force=False):
        """Persist periodically instead of after every poll (SD-card wear)."""
        if not self.statistics:
            return
        if not force and self._saved_at is not None and monotonic() - self._saved_at < self.save_interval:
            return
        self._saved_at = monotonic()
        try:
            await self.store.async_save(self.ledger.export())
        except Exception:
            self.storage_error = True
            _LOGGER.exception("Could not persist HouseHeating observed diagnostics")
        else:
            self.storage_error = False

    async def async_snapshot(self, snapshot):
        if self.closed:
            return
        if self.statistics:
            async with self.lock:
                value = relay_value(snapshot, "compressor_active", self.max_age)
                window = snapshot.samples.get(0x1A) if snapshot else None
                at = window.end if window and value is not None else time()
                clock = window.monotonic_end if window and value is not None else monotonic()
                self.ledger.ingest(at, clock, value)
                await self._async_save_statistics()
        self._queue()

    def _external(self, entity, kind):
        state = self.hass.states.get(entity)
        if state is None or state.attributes.get("restored") or state.last_reported.timestamp() < self.started:
            return None
        if kind == "power":
            reading = source_reading(state, "power")
            return reading.value if valid_reading(reading, time(), self.config.max_age) else None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if not isfinite(value) or not 0 <= time() - state.last_reported.timestamp() <= self.config.max_age:
            return None
        unit = state.attributes.get("unit_of_measurement")
        device_class = state.attributes.get("device_class")
        if kind == "temperature" and device_class == "temperature" and unit in ("°C", "°F", "K"):
            return (value - 32) * 5 / 9 if unit == "°F" else value - 273.15 if unit == "K" else value
        if kind == "battery" and device_class == "battery" and unit == "%" and 0 <= value <= 100:
            return value
        return None

    def _outdoor(self, snapshot):
        if self.config.outdoor_entity:
            return self._external(self.config.outdoor_entity, "temperature")
        if not snapshot:
            return None
        if not self.coordinator.last_update_success or not self.coordinator.device.unit.connected:
            return None
        # A Modbus sample is at most one polling interval old by design; never
        # reject it only because the curve's external-source age is shorter.
        limit = max(self.config.max_age, self.max_age)
        window = snapshot.samples.get(0x4A)
        if not window or not 0 <= time() - window.end <= limit or not 0 <= monotonic() - window.monotonic_end <= limit:
            return None
        return snapshot.value("outdoor_temperature", self.coordinator.device.config)

    def _advice(self, snapshot):
        outdoor = self._outdoor(snapshot)
        if outdoor is None:
            raise ValueError("Outdoor source unavailable")
        pv = self._external(self.config.pv_entity, "power") if self.config.pv_entity else None
        battery = self._external(self.config.battery_entity, "battery") if self.config.battery_entity else None
        return self.model.calculate(
            outdoor, pv, battery, monotonic(), self.coordinator.device.config.limits(self.config.target)
        )

    def _decide(self, snapshot, target, *, fresh):
        """Return (status, write_needed). Only a fresh snapshot may latch an override."""
        raw = snapshot.raw
        device_config = self.coordinator.device.config
        if raw.get(0x305) != 1 or raw.get(0x304) not in MODES[self.config.target]:
            return "inactive_mode", False
        native = NATIVE_CURVES[self.config.target]
        identity = snapshot.identity
        if not device_config.curves or identity is None or identity.protocol < 130:
            return "native_curve_unknown", False
        native_value = snapshot.value(native, device_config)
        if native_value is None:
            return "native_curve_unknown", False
        if native_value != 0:
            return "native_curve_active", False
        if fresh:
            window = snapshot.samples.get(CURVE_ADDRESSES[native])
            if window is None or not 0 <= time() - window.end <= self.max_age:
                return "native_curve_unknown", False
        current = snapshot.value(self.config.target, device_config)
        if self.last_command is not None and current != self.last_command:
            if not fresh:
                return "controlling", True  # confirm a possible manual change with fresh data
            self.blocked = True
            return "manual_override", False
        if self.last_attempt is not None and monotonic() - self.last_attempt < self.config.cooldown_seconds:
            return "cooldown", False
        if current is None or abs(current - target) < self.config.step_degrees:
            return "unchanged", False
        return "controlling", True

    async def async_evaluate(self):
        if self.closed or not self.config.enabled or self.blocked:
            return
        snapshot = self.coordinator.device.snapshot
        try:
            advice = self._advice(snapshot)
        except ValueError:
            self.model.reset()
            self.values_cache = {"curve_status": "source_unavailable"}
            self.async_notify()
            return
        self.values_cache = advice | {"curve_status": "advisory"}
        if self.config.automatic:
            await self._async_automatic(snapshot, advice)
        self.async_notify()

    async def _async_automatic(self, snapshot, advice):
        if not self.coordinator.device.control_ready:
            self.values_cache["curve_status"] = "control_locked"
            return
        if not self.coordinator.last_update_success:
            # The coordinator's own polling recovers the connection; do not add traffic.
            self.values_cache["curve_status"] = "control_unavailable"
            return
        if self._retry_at is not None and monotonic() < self._retry_at:
            self.values_cache["curve_status"] = "control_unavailable"
            return
        # Decide from the latest poll first: no bus traffic or storage write when
        # nothing has to change. Only a likely write reads fresh data under the lock.
        status, needed = self._decide(snapshot, advice["curve_advised_target"], fresh=False)
        self.values_cache["curve_status"] = status
        if not needed:
            return
        try:
            # Persist an inhibit before any possible write. An interrupted
            # process cannot silently retry the same uncertain command.
            await self.command_store.async_save(
                {
                    "confirmation_id": self.config.confirmation_id,
                    "pending": True,
                    "last_command": self.last_command,
                    "at": time(),
                }
            )
        except Exception:
            self.blocked = True
            self.values_cache["curve_status"] = "write_error"
            _LOGGER.exception("Weather curve stopped: the safety state could not be stored")
            return
        planned = {}

        def plan(fresh):
            # Use the same command lock, fresh validation, allowlist and
            # readback as the UI. Never call unit.write_register here.
            if self.closed:
                return []
            try:
                result = self._advice(fresh)
            except ValueError:
                self.values_cache["curve_status"] = "source_unavailable"
                return []
            self.values_cache.update(result)
            target = result["curve_advised_target"]
            state, write = self._decide(fresh, target, fresh=True)
            self.values_cache["curve_status"] = state
            if not write:
                return []
            self.last_attempt = monotonic()
            planned["target"] = target
            return [(self.config.target, target)]

        self.coordinator.force_optional = True
        try:
            await self.coordinator.async_control(plan)
        except HomeAssistantError as err:
            if isinstance(err.__cause__, VerificationError):
                # A transmitted command could not be confirmed: latch, never retry.
                self.blocked = True
                self.last_command = planned.get("target", self.last_command)
                self.values_cache["curve_status"] = "write_error"
                _LOGGER.error("Weather curve stopped after an unconfirmed command; no automatic retry: %s", err)
            else:
                # Refused or unreadable BEFORE transmission: nothing was sent.
                key = getattr(err, "translation_key", None)
                self.values_cache["curve_status"] = (
                    "control_locked" if key == "control_locked" else "control_unavailable"
                )
                self._retry_at = monotonic() + self.max_age
                _LOGGER.warning("Weather curve skipped this round; no command was sent: %s", err)
        except Exception:
            self.blocked = True
            self.values_cache["curve_status"] = "write_error"
            _LOGGER.exception("Weather curve stopped after an unexpected control error; no automatic retry")
        else:
            self._retry_at = None
            if "target" in planned:
                self.last_command = planned["target"]
        try:
            await self.command_store.async_save(
                {
                    "confirmation_id": self.config.confirmation_id,
                    "pending": self.blocked,
                    "last_command": self.last_command,
                    "at": time() - (monotonic() - self.last_attempt) if self.last_attempt is not None else None,
                }
            )
        except Exception:
            self.blocked = True
            self.values_cache["curve_status"] = "write_error"
            _LOGGER.exception("Weather curve stopped: the safety state could not be stored")

    def values(self):
        result = self.ledger.values(time()) if self.statistics else {}
        if self.config.enabled:
            result.update(self.values_cache)
        return result

    def diagnostics(self):
        return {
            "observed_statistics": self.ledger.export() if self.statistics else None,
            "storage_error": self.storage_error,
            "storage_invalid": self.storage_invalid,
            "weather_curve": asdict(self.config),
            "values": self.values(),
            "latched_stop": self.blocked,
        }

    async def async_close(self):
        self.closed = True
        self.running = False
        for unsub in self.unsub:
            unsub()
        self.unsub = []
        if self._stop_unsub is not None:
            self._stop_unsub()
            self._stop_unsub = None
        if self.task and not self.task.done():
            await self.task
        self.values_cache = {"curve_status": "disabled"}
        async with self.lock:
            await self._async_save_statistics(force=True)
