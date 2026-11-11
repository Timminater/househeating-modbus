"""HA lifecycle for read-only energy accounting and external sensor sources."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from time import monotonic, time

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_state_report_event,
)
from homeassistant.helpers.storage import Store

from househeating_modbus.telemetry import EnergyLedger, Reading, calculate, period_bounds
from .listeners import ManagerListeners

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
# Persist at most every five minutes (and on unload/shutdown). Writing the full
# ledger after every sample wore out SD cards, especially with 1 s meters.
SAVE_INTERVAL = 300.0
# Entities read the same values several times per state write.
VALUES_CACHE_SECONDS = 1.0


def source_reading(state, kind):
    """Normalize declared units; never interpret an unavailable/restored value as zero."""
    if state is None or state.attributes.get("restored"):
        return None
    units = {"power": {"W": 0.001, "kW": 1}, "energy": {"Wh": 0.001, "kWh": 1}}
    factor = units[kind].get(state.attributes.get("unit_of_measurement"))
    if factor is None or state.attributes.get("device_class") != kind:
        return None
    try:
        return Reading(float(state.state) * factor, state.last_reported.timestamp())
    except (ValueError, TypeError, AttributeError):
        return None


class MonitoringManager(ManagerListeners):
    def __init__(self, hass, coordinator, config):
        super().__init__()
        self.hass, self.coordinator, self.config = hass, coordinator, config
        self.store = Store(hass, STORAGE_VERSION, f"househeating.monitoring.{coordinator.entry.entry_id}")
        self.ledger = EnergyLedger(config, hass.config.time_zone)
        self.snapshot = None
        self.storage_error = False
        self.save_interval = SAVE_INTERVAL
        self._saved_at = None
        self._lock = asyncio.Lock()
        self._unsubscribers = []
        self._stop_unsub = None
        self._timer = None
        self._tasks = set()
        self._closed = False
        self._started_at = time()
        self._sources_seen = set()
        self._source_task = None
        self._source_dirty = False
        self._cache = None
        self._cache_at = 0.0

    async def async_load(self):
        state = await self.store.async_load()
        if state is not None:
            # Corrupt or unsupported storage must not silently reset visible totals.
            self.ledger = EnergyLedger(self.config, self.hass.config.time_zone, state)

    def start(self):
        self._stop_unsub = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_handle_stop)
        if self.config.source == "external":
            sources = [
                s
                for s in (self.config.external_power, self.config.external_energy, self.config.external_heat_power)
                if s
            ]
            self._unsubscribers.extend(
                (
                    async_track_state_change_event(self.hass, sources, self._source_event),
                    async_track_state_report_event(self.hass, sources, self._source_event),
                )
            )
        elif self.config.thermal_source == "external":
            sources = [self.config.external_heat_power]
            self._unsubscribers.extend(
                (
                    async_track_state_change_event(self.hass, sources, self._source_event),
                    async_track_state_report_event(self.hass, sources, self._source_event),
                )
            )
        self._schedule()

    async def _async_handle_stop(self, _event):
        # Home Assistant does not unload entries on shutdown; persist here.
        self._stop_unsub = None
        async with self._lock:
            await self._async_save(force=True)

    @callback
    def _source_event(self, event):
        if self._closed:
            return
        state = event.data.get("new_state")
        if state:
            self._sources_seen.add(state.entity_id)
        self._source_dirty = True
        if self._source_task is not None and not self._source_task.done():
            return

        async def drain():
            while self._source_dirty and not self._closed:
                self._source_dirty = False
                await self.async_process()

        task = self.hass.async_create_task(drain(), "HouseHeating source telemetry")
        self._source_task = task
        self._track(task)

    def _track(self, task):
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _reading(self, entity_id, kind):
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        # An already present sensor must actually report after startup. A restored
        # HA state or a stale retained counter may not become a fresh baseline.
        if entity_id not in self._sources_seen and state.last_reported.timestamp() < self._started_at:
            return None
        return source_reading(state, kind)

    async def async_snapshot(self, snapshot):
        # Called from the coordinator update, which refreshes all entities itself.
        self.snapshot = snapshot
        await self.async_process(notify=False)

    async def async_failure(self, *, notify=False):
        self.snapshot = None
        await self.async_process(notify=notify)

    async def _async_save(self, *, force=False):
        if not force and self._saved_at is not None and monotonic() - self._saved_at < self.save_interval:
            return
        self._saved_at = monotonic()
        try:
            await self.store.async_save(self.ledger.export())
        except Exception:  # The storage boundary: report, keep counting, retry later.
            self.storage_error = True
            _LOGGER.exception("Could not persist HouseHeating monitoring totals")
        else:
            self.storage_error = False

    async def async_process(self, *, notify=True):
        async with self._lock:
            if self._closed:
                return
            now, clock = time(), monotonic()
            power = self._reading(self.config.external_power, "power")
            counter = self._reading(self.config.external_energy, "energy")
            heat = (
                self._reading(self.config.external_heat_power, "power")
                if self.config.thermal_source == "external"
                else None
            )
            sample = calculate(self.snapshot, self.coordinator.device.config, self.config, now, clock, power, heat)
            self.ledger.ingest(sample, counter)
            self._cache = None
            await self._async_save()
            self._schedule()
        if notify:
            self.async_notify()

    def _computed(self):
        now = time()
        if self._cache is None or abs(now - self._cache_at) >= VALUES_CACHE_SECONDS:
            values = self.ledger.values(now)
            if self.storage_error:
                for key in (
                    "selected_electrical_power",
                    "water_flow_calibrated",
                    "water_delta_temperature",
                    "thermal_power_estimated",
                    "thermal_power_hydraulic_estimated",
                    "thermal_power_external_reported",
                    "cop_instant",
                    "eer_instant",
                ):
                    values[key] = None
                values["monitoring_status"] = "storage_error"
            aggregates = {
                scope: self.ledger.aggregate(scope, now) for scope in ("yesterday", "7d", "30d", "365d", "overall")
            }
            self._cache, self._cache_at = (values, aggregates), now
        return self._cache

    def values(self):
        return self._computed()[0]

    def aggregate(self, scope):
        return self._computed()[1][scope]

    def _schedule(self):
        if self._timer:
            self._timer()
            self._timer = None
        if self._closed:
            return
        now = time()
        deadlines = []
        if self.snapshot:
            deadlines.extend(
                w.end + self.config.max_age + 0.01
                for a, w in self.snapshot.samples.items()
                if a in (0x4F, 0x50, 0x58, 0x5C, 0x304) and w.end + self.config.max_age >= now
            )
        for key, kind in (
            (self.config.external_power, "power"),
            (self.config.external_energy, "energy"),
            (self.config.external_heat_power, "power"),
        ):
            value = self._reading(key, kind)
            if value and value.reported_at + self.config.max_age >= now:
                deadlines.append(value.reported_at + self.config.max_age + 0.01)
        deadlines.append(period_bounds(now, "day", self.ledger.zone)[1])

        @callback
        def tick(_now):
            self._timer = None
            if not self._closed:
                self._track(self.hass.async_create_task(self.async_process(), "HouseHeating telemetry clock"))

        self._timer = async_track_point_in_utc_time(self.hass, tick, datetime.fromtimestamp(min(deadlines), UTC))

    async def async_close(self):
        self._closed = True
        if self._timer:
            self._timer()
            self._timer = None
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []
        if self._stop_unsub is not None:
            self._stop_unsub()
            self._stop_unsub = None
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        async with self._lock:
            await self._async_save(force=True)

    @callback
    def connection_lost(self):
        if not self._closed:
            self._track(
                self.hass.async_create_task(self.async_failure(notify=True), "HouseHeating telemetry connection lost")
            )

    def diagnostics(self):
        return {
            "configuration": asdict(self.config),
            "values": self.values(),
            "storage_error": self.storage_error,
            "reasons": list(self.ledger.last_sample.reasons) if self.ledger.last_sample else ["no_sample"],
            "ledger": self.ledger.export(),
        }
