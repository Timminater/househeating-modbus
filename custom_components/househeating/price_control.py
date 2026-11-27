"""Home Assistant orchestration for optional dynamic heating tariffs."""

import asyncio
import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from functools import partial
from math import floor, isfinite
from time import time

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .price_learning import RETENTION, PriceEnergyLearning
from .price_options import DEFAULTS, is_zonneplan_tariff
from .price_plan import PricePlan, Tariff, allows_preheat, choose_plan, read_tariffs

_LOGGER = logging.getLogger(__name__)
HEATING_MODES = (1, 3)


def number(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (ValueError, TypeError):
        return None


class PriceManager:
    def __init__(self, hass, coordinator):
        self.hass = hass
        self.coordinator = coordinator
        self.config = coordinator.entry.options["price_control"]
        self.automatic = self.config["mode"] == "automatic"
        self.preheat_ratio = int(self.config.get("preheat_ratio", DEFAULTS["preheat_ratio"]))
        self.max_preheat_gap = int(self.config.get("max_preheat_gap", DEFAULTS["max_preheat_gap"])) * 60
        self.store = Store(hass, 1, f"househeating.price_control.{coordinator.entry.entry_id}")
        self.saved = {}
        self.plan = None
        self.recovery_plan = None
        self.price_checked_at = None
        self.visible_plan = None
        self.status = "waiting"
        self.lock = asyncio.Lock()
        self.cancel = None
        self.idle_since = None
        self.no_demand_since = None
        self.pump_idle_since = None
        self.pump_retry_at = 0
        self.next_history_sample = 0
        self.next_plan_at = 0
        self.learning = PriceEnergyLearning()

    async def load(self):
        try:
            self.saved = await self.store.async_load() or {}
            if not isinstance(self.saved, dict):
                raise ValueError("Invalid price control storage")
            now = time()
            if spec := self.saved.get("plan"):
                restored = self.restore_plan(spec)
                if now < restored.pause.end:
                    if self.accepts_plan(restored):
                        self.plan = restored
                    else:
                        self.saved["plan"] = None
                        await self.save()
                elif restored.defer and now < restored.charge.end:
                    self.recovery_plan = restored
            if spec := self.saved.get("recovery_plan"):
                restored = self.restore_plan(spec)
                if restored.defer and restored.pause.end <= now < restored.charge.end:
                    self.recovery_plan = restored
            if self.automatic and self.saved.get("authorization") != self.config["authorization"]:
                self.saved.pop("manual", None)
                self.saved.pop("pending", None)
                self.saved.pop("expected_power", None)
                self.saved.pop("water_restore_pending", None)
                self.plan = self.recovery_plan = None
                self.saved["plan"] = None
                self.saved.pop("recovery_plan", None)
                self.saved["authorization"] = self.config["authorization"]
                await self.save()
        except (HomeAssistantError, TypeError, ValueError, KeyError):
            self.saved = {"blocked": True}

    def accepts_plan(self, plan):
        if plan.defer:
            return self.config.get("allow_defer", False)
        return allows_preheat(plan.charge, plan.pause, self.preheat_ratio, self.max_preheat_gap)

    @staticmethod
    def restore_plan(spec):
        return PricePlan(
            Tariff(**spec["charge"]),
            Tariff(**spec["pause"]),
            spec["saving_per_kwh"],
            spec["energy_kwh"],
            spec.get("defer", False),
        )

    async def save(self):
        await self.store.async_save(dict(self.saved))

    def start(self):
        if self.cancel is None:
            self.cancel = async_track_time_interval(self.hass, self.tick, timedelta(seconds=15))
            self.hass.async_create_task(self.tick(None), "HouseHeating price control")

    async def close(self):
        if self.cancel is None:
            return
        self.cancel()
        self.cancel = None
        async with self.lock:
            if self.automatic:
                try:
                    await self.restore_room()
                    await self.adjust_water(restore=True)
                    if self.saved.get("paused") and self.demand() is True:
                        await self.power(True, require_pause=True)
                except (HomeAssistantError, OSError):
                    _LOGGER.warning("Price control could not restore its temporary settings", exc_info=True)

    def state(self, entity_id):
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is not None and state.state not in ("unknown", "unavailable") and not state.attributes.get("restored"):
            return state
        return None

    def demand_for(self, entity_id):
        state = self.state(entity_id)
        if state is None:
            return None
        if state.domain == "climate":
            if state.state in ("off", "cool", "dry", "fan_only"):
                return False
            action = state.attributes.get("hvac_action")
            if action is not None:
                return action == "heating"
            current = number(state.attributes.get("current_temperature"))
            target = number(state.attributes.get("temperature"))
            return current < target if current is not None and target is not None else None
        if state.state in ("on", "off"):
            return state.state == "on"
        value = number(state.state)
        return value > 0 if value is not None else None

    def demand(self):
        values = [self.demand_for(key) for key in self.config.get("demand_entities", ())]
        if True in values:
            return True
        return False if values and None not in values else None

    def comfort(self):
        entities = set(self.config.get("comfort_entities", ()))
        if entity := self.config.get("climate_entity"):
            entities.add(entity)
        active = False
        for entity in entities:
            state = self.state(entity)
            if state is None:
                return False
            if state.state in ("off", "cool", "dry", "fan_only"):
                continue
            active = True
            current = number(state.attributes.get("current_temperature"))
            target = number(state.attributes.get("temperature"))
            own = self.saved.get("room")
            if own and own["entity"] == entity and target == own["target"]:
                target = own["original"]
            margin = self.temperature_delta(self.config["comfort_margin"])
            if current is None or target is None or current < target - margin - 1e-6:
                return False
        return active

    def temperature_delta(self, celsius):
        return celsius * 1.8 if self.hass.config.units.temperature_unit == "Â°F" else celsius

    def buffer_ready(self):
        entity = self.config.get("buffer_entity")
        if not self.config["buffer"] or not entity:
            return True
        state = self.state(entity)
        if state is None:
            return False
        value = number(state.state)
        unit = state.attributes.get("unit_of_measurement")
        if value is None or unit not in ("Â°C", "Â°F", "K"):
            return False
        if unit == "Â°F":
            value = (value - 32) * 5 / 9
        elif unit == "K":
            value -= 273.15
        return value is not None and value >= self.config["buffer_min"]

    def electrical_watts(self):
        if self.config.get("power_entity"):
            state = self.state(self.config["power_entity"])
            if state is None:
                return None
            watts = number(state.state)
            unit = state.attributes.get("unit_of_measurement")
            if watts is None or watts < 0 or unit not in ("W", "kW"):
                return None
            return watts * 1000 if unit == "kW" else watts
        device = self.coordinator.device
        power = device.snapshot.value("input_power", device.config)
        return None if power is None else power * 1000

    def observe_power(self, now):
        if now < self.next_history_sample or (watts := self.electrical_watts()) is None:
            return
        self.next_history_sample = now + 900
        history = self.saved.get("history", [])
        self.saved["history"] = [row for row in history if row[0] > now - 14 * 86400] + [[now, watts]]

    @staticmethod
    def learning_slot(stamp):
        local = dt_util.as_local(datetime.fromtimestamp(stamp, UTC))
        return local.hour * 4 + local.minute // 15

    def observe_learning(self, now):
        snapshot = self.coordinator.device.snapshot
        device_config = self.coordinator.device.config
        plan = self.visible_plan
        outdoor = snapshot.value("outdoor_temperature", device_config)
        valid = (
            self.coordinator.last_update_success
            and snapshot.raw.get(0x304) in HEATING_MODES
            and 0 <= now - snapshot.timestamp <= max(60, 3 * self.coordinator.update_interval.total_seconds())
        )
        signal = self.state(self.config.get("execution_entity"))
        external = not self.automatic and signal is not None and signal.state == "on"
        if not self.automatic and self.config.get("execution_entity") and signal is None:
            valid = False
        room = self.saved.get("room")
        room_state = self.state(room["entity"]) if room and room.get("purpose") == "preheat" else None
        water = self.saved.get("water")
        water_key = "floor_setpoint" if snapshot.raw.get(0x304) == 3 else "heating_setpoint"
        preheated = (room_state is not None and number(room_state.attributes.get("temperature")) == room["target"]) or (
            water is not None and snapshot.value(water_key, device_config) == water["target"]
        )
        data = self.saved.setdefault("preheat_learning", {})
        strategy = [
            self.config.get(key)
            for key in ("power_entity", "execution_entity", "climate_entity", "preheat_offset", "water_boost")
        ]
        changed = data.get("strategy") != strategy
        if changed:
            data.clear()
            data["strategy"] = strategy
            self.learning = PriceEnergyLearning()
        results = data.get("results", [])
        expired = [row for row in results if row[0] < now - RETENTION]
        if expired:
            data["results"] = [row for row in results if row[0] >= now - RETENTION]
            changed = True
        return (
            self.learning.observe(
                data,
                now,
                plan,
                watts=self.electrical_watts() if valid else None,
                outdoor=outdoor,
                automatic=self.automatic,
                external=external,
                preheated=self.automatic and preheated,
                paused=self.automatic and bool(self.saved.get("paused")),
                interrupted=self.automatic
                and self.status
                in ("manual_override", "command_unconfirmed", "control_unavailable", "pump_unavailable"),
                local_slot=self.learning_slot,
            )
            or changed
        )

    def learning_estimate(self):
        return self.learning.estimate(self.saved.get("preheat_learning", {}))

    def power_history(self):
        groups = {}
        for stamp, watts in self.saved.get("history", []):
            groups.setdefault(int(stamp // 3600) % 24, []).append(watts)
        return {hour: sum(values) / len(values) for hour, values in groups.items() if len(values) >= 4}

    def forecast(self, now):
        entity_id = self.config.get("price_entity")
        state = self.state(entity_id)
        if state is None or not is_zonneplan_tariff(er.async_get(self.hass).async_get(entity_id)):
            return ()
        try:
            rows = read_tariffs(state.attributes)
        except (ArithmeticError, KeyError, TypeError, ValueError):
            return ()
        return rows if any(row.start <= now < row.end for row in rows) else ()

    async def pump(self, now):
        cfg = self.config
        start = cfg.get("pump_start")
        feedback = cfg.get("pump_feedback") or start
        if not cfg["buffer"] or not start:
            return
        requests = [self.demand_for(key) for key in cfg["demand_entities"]]
        if key := cfg.get("floor_pump"):
            requests.append(self.demand_for(key))
        required = True in requests
        if required or None in requests:
            self.pump_idle_since = None
        elif self.pump_idle_since is None:
            self.pump_idle_since = now
        actual = self.demand_for(feedback)
        if actual is None:
            self.status = "pump_unavailable"
            return
        if now < self.pump_retry_at:
            return
        can_stop = self.pump_idle_since is not None and now - self.pump_idle_since >= cfg["pump_overrun"] * 60
        if (required and not actual) or (can_stop and actual):
            self.pump_retry_at = now + 60
            if start.startswith("button."):
                await self.call("button", "press", start if required else cfg["pump_stop"])
            else:
                await self.call("switch", "turn_on" if required else "turn_off", start)

    async def call(self, domain, service, entity, **values):
        await self.hass.services.async_call(domain, service, {"entity_id": entity, **values}, blocking=True)

    async def warm_room(self, now):
        await self.set_room_target(self.config["preheat_offset"], "preheat", self.plan.charge.start)

    async def set_room_target(self, offset, purpose, block_start):
        entity = self.config.get("climate_entity")
        attempt_key = "room_attempt" if purpose == "preheat" else "hold_attempt"
        if not entity or self.saved.get("room") or self.saved.get(attempt_key) == block_start:
            return
        state = self.state(entity)
        if state is None or state.state not in ("heat", "auto", "heat_cool"):
            return
        original = number(state.attributes.get("temperature"))
        step = number(state.attributes.get("target_temp_step")) or 0.1
        maximum = number(state.attributes.get("max_temp"))
        minimum = number(state.attributes.get("min_temp"))
        offset = self.temperature_delta(offset)
        if original is None or maximum is None or step <= 0 or not offset:
            return
        steps = floor((abs(offset) + 1e-6) / step)
        target = round(original + (steps if offset > 0 else -steps) * step, 6)
        if target == original or target > maximum or (minimum is not None and target < minimum):
            return
        self.saved[attempt_key] = block_start
        self.saved["room"] = dict(entity=entity, original=original, target=target, purpose=purpose)
        await self.save()
        await self.call("climate", "set_temperature", entity, temperature=target)

    async def restore_room(self):
        own = self.saved.get("room")
        if own is None or (state := self.state(own["entity"])) is None:
            return
        if number(state.attributes.get("temperature")) == own["target"]:
            await self.call("climate", "set_temperature", own["entity"], temperature=own["original"])
        self.saved.pop("room", None)
        await self.save()

    async def adjust_water(self, *, restore=False):
        """Share the device's verified write path and preserve manual setpoints."""
        own = self.saved.get("water")
        if restore:
            if own is None:
                return
        elif (
            own is not None
            or not self.config.get("water_boost")
            or self.saved.get("water_attempt") == self.plan.charge.start
            or self.demand() is not True
        ):
            return
        options = self.coordinator.entry.options
        if options.get("weather_curve", {}).get("automatic"):
            return
        device = self.coordinator.device
        snapshot = device.snapshot
        mode = snapshot.raw.get(0x304)
        if mode not in HEATING_MODES or (restore and own["mode"] != mode):
            return
        key = "floor_setpoint" if mode == 3 else "heating_setpoint"
        native = "floor_curve" if mode == 3 else "heating_curve"
        current = snapshot.value(key, device.config)
        if current is None:
            return
        if restore:
            if current != own["target"]:
                self.saved.pop("water", None)
                self.saved.pop("water_restore_pending", None)
                await self.save()
                return
            if self.saved.get("water_restore_pending"):
                self.status = "command_unconfirmed"
                return
            target = own["original"]
        else:
            if snapshot.raw.get(0x305) != 1:
                return
            low, high = device.config.limits(key)
            target = min(floor(high), floor(current + self.config["water_boost"]))
            if current < low or target <= current:
                return
            self.saved["water_attempt"] = self.plan.charge.start
            self.saved["water"] = dict(mode=mode, original=current, target=target)
            await self.save()
        sent = False

        def command(fresh):
            nonlocal sent
            if (
                fresh.raw.get(0x304) != mode
                or fresh.value(key, device.config) != current
                or (
                    not restore
                    and (
                        fresh.raw.get(0x305) != 1
                        or 0 not in fresh.raw
                        or fresh.raw[0] & 0x100
                        or fresh.value(native, device.config) != 0
                    )
                )
            ):
                return []
            sent = True
            return [(key, target)]

        if restore:
            self.saved["water_restore_pending"] = True
            await self.save()
        self.coordinator.force_optional = True
        try:
            await self.coordinator.async_control(command)
        except HomeAssistantError:
            if not sent:
                if not restore:
                    self.saved.pop("water", None)
                self.saved.pop("water_restore_pending", None)
                await self.save()
            raise
        if (restore and sent) or (not restore and not sent):
            self.saved.pop("water", None)
        self.saved.pop("water_restore_pending", None)
        if restore or not sent:
            await self.save()

    @staticmethod
    def idle(snapshot):
        raw = snapshot.raw
        return raw.get(0x40) == 0 and 0 in raw and not raw[0] & 0x100

    async def power(self, enabled, *, price_pause=False, require_pause=False):
        """Persist ownership and revalidate against the command's fresh poll."""
        if self.saved.get("pending") or self.saved.get("manual"):
            return
        sent = False
        previous_pause = bool(self.saved.get("paused"))
        self.saved["pending"] = {"target": int(enabled), "price_pause": price_pause}
        if price_pause:
            self.saved["plan"] = asdict(self.plan)
        await self.save()

        def command(snapshot):
            nonlocal sent
            raw = snapshot.raw
            if (
                raw.get(0x304) not in HEATING_MODES
                or raw.get(0x305) != int(not enabled)
                or (not enabled and not self.idle(snapshot))
                or (enabled and self.demand() is not True)
                or (require_pause and not previous_pause)
                or (price_pause and not self.can_pause(time()))
                or (not enabled and not price_pause and self.demand() is not False)
            ):
                return []
            sent = True
            return [("power", enabled)]

        try:
            await self.coordinator.async_control(command)
        except HomeAssistantError:
            if sent:
                self.status = "command_unconfirmed"
                return
            self.status = "control_unavailable"
        if sent:
            observed = self.coordinator.device.snapshot.raw.get(0x305)
            if observed != int(enabled):
                self.status = "command_unconfirmed"
                return
            self.saved["expected_power"] = observed
            self.saved["paused"] = price_pause and not enabled
        self.saved.pop("pending", None)
        await self.save()

    def covered_peak(self, now):
        if not self.plan or not self.plan.pause.start <= now < self.plan.pause.end:
            return False
        covered_until = now
        for row in self.forecast(now):
            if row.end <= covered_until:
                continue
            if row.start > covered_until:
                break
            covered_until = row.end
            if covered_until >= self.plan.pause.end:
                break
        return covered_until >= self.plan.pause.end

    def hold_needed(self, now):
        if not self.config["buffer"] or not self.config.get("hold_during_peak") or not self.covered_peak(now):
            return False
        state = self.state(self.config.get("climate_entity"))
        if state is None or state.state not in ("heat", "auto", "heat_cool"):
            return False
        current = number(state.attributes.get("current_temperature"))
        target = number(state.attributes.get("temperature"))
        own = self.saved.get("room")
        if own and own["entity"] == state.entity_id and target == own["target"]:
            if own.get("purpose") == "hold":
                return True
            target = own["original"]
        if self.saved.get("hold_attempt") == self.plan.pause.start:
            return False
        margin = self.temperature_delta(self.config["comfort_margin"])
        return current is not None and target is not None and current <= target - margin + 1e-6

    def can_pause(self, now):
        return (
            self.covered_peak(now)
            and now >= self.saved.get("pause_lock_until", 0)
            and self.comfort()
            and self.buffer_ready()
            and not self.hold_needed(now)
        )

    async def tick(self, _):
        if self.cancel is None or self.lock.locked():
            return
        async with self.lock:
            if self.cancel is None:
                return
            try:
                now = time()
                await self.update(now)
                if self.observe_learning(time()):
                    await self.save()
            except (HomeAssistantError, OSError, TimeoutError, ValueError, KeyError, TypeError):
                self.price_checked_at = self.visible_plan = None
                self.status = "control_unavailable"
                _LOGGER.debug("Price control could not complete the update", exc_info=True)
            self.coordinator.async_update_listeners()

    async def update(self, now):
        if self.automatic and (self.saved.get("blocked") or self.saved.get("pending")):
            self.price_checked_at = self.visible_plan = None
            await self.restore_room()
            await self.adjust_water(restore=True)
            self.status = "command_unconfirmed"
            return
        old_sample = self.next_history_sample
        self.observe_power(now)
        rows = self.forecast(now)
        previous = (self.plan, self.recovery_plan)
        if self.recovery_plan and now >= self.recovery_plan.charge.end:
            self.recovery_plan = None
        if self.plan and self.plan.defer and self.plan.pause.end <= now < self.plan.charge.end:
            self.recovery_plan = self.plan
            self.saved["recover_until"] = self.plan.charge.end
        if not rows or (self.plan and now >= self.plan.pause.end):
            self.plan = None
        if (
            rows
            and now >= max(self.next_plan_at, self.saved.get("recover_until", 0))
            and (not self.plan or now < min(self.plan.charge.start, self.plan.pause.start))
        ):
            self.plan = await self.hass.async_add_executor_job(
                partial(choose_plan, preheat_ratio=self.preheat_ratio, max_preheat_gap=self.max_preheat_gap),
                rows,
                now,
                int(float(self.config["max_hours"]) * 3600),
                self.config["minimum_spread"],
                self.config["extra_energy"] / 100,
                self.power_history(),
                self.config.get("allow_defer", False),
            )
            self.next_plan_at = now + 60
        if previous != (self.plan, self.recovery_plan) or old_sample != self.next_history_sample:
            self.saved["plan"] = asdict(self.plan) if self.plan else None
            if self.recovery_plan:
                self.saved["recovery_plan"] = asdict(self.recovery_plan)
            else:
                self.saved.pop("recovery_plan", None)
            await self.save()
        phase = "normal" if rows else "price_unavailable"
        if self.plan:
            if not self.plan.defer and self.plan.charge.start <= now < self.plan.charge.end:
                phase = "preheat"
            elif self.plan.pause.start <= now < self.plan.pause.end:
                if self.hold_needed(now):
                    phase = "holding_temperature"
                else:
                    phase = "pause" if self.can_pause(now) else "comfort_or_buffer"
            else:
                phase = "scheduled"
        self.status = phase
        self.price_checked_at = now if rows else None
        self.visible_plan = (self.recovery_plan or self.plan) if rows else None
        if not self.automatic:
            return

        try:
            await self.pump(now)
        except HomeAssistantError:
            self.status = "pump_unavailable"
            _LOGGER.debug("Secondary pump command failed", exc_info=True)
        snapshot = self.coordinator.device.snapshot
        raw = snapshot.raw
        valid = (
            self.coordinator.last_update_success
            and self.coordinator.device.control_ready
            and 0 <= now - snapshot.timestamp <= max(60, 3 * self.coordinator.update_interval.total_seconds())
        )
        if not valid or raw.get(0x304) not in HEATING_MODES:
            self.idle_since = None
            await self.restore_room()
            self.status = "control_unavailable"
            return
        if self.idle(snapshot):
            if self.idle_since is None:
                self.idle_since = now
        else:
            self.idle_since = None

        actual = raw.get(0x305)
        if actual not in (0, 1):
            return
        expected = self.saved.get("expected_power")
        if self.saved.get("manual") or (expected is not None and expected != actual):
            if not self.saved.get("manual"):
                self.saved["manual"] = True
                await self.save()
            await self.restore_room()
            await self.adjust_water(restore=True)
            self.status = "manual_override"
            return
        if expected is None:
            self.saved["expected_power"] = actual
            await self.save()
        if phase == "preheat":
            await self.warm_room(now)
        elif phase == "holding_temperature":
            own = self.saved.get("room")
            if own and own.get("purpose") != "hold":
                await self.restore_room()
            await self.set_room_target(0.1 - self.config["comfort_margin"], "hold", self.plan.pause.start)
        else:
            await self.restore_room()
        await self.adjust_water(restore=phase != "preheat")

        demand = self.demand()
        if demand is False:
            if self.no_demand_since is None:
                self.no_demand_since = now
        else:
            self.no_demand_since = None
        confirmed_idle = self.idle_since is not None and now - self.idle_since >= 60
        if phase == "pause":
            if actual == 1 and confirmed_idle:
                await self.power(False, price_pause=True)
            elif actual == 1:
                self.status = "waiting_for_compressor"
            return
        if (
            self.plan
            and self.plan.pause.start <= now < self.plan.pause.end
            and self.saved.get("pause_lock_until", 0) < self.plan.pause.end
        ):
            self.saved["pause_lock_until"] = self.plan.pause.end
            await self.save()
        if demand is True and actual == 0:
            await self.power(True)
        elif actual == 1 and confirmed_idle and self.no_demand_since is not None and now - self.no_demand_since >= 900:
            await self.power(False)

    def block_active(self, block):
        now = self.price_checked_at
        if now is None:
            return None
        if (plan := self.visible_plan) is None:
            return False
        tariff = getattr(plan, block)
        return tariff.start <= now < tariff.end

    def attributes(self):
        if self.plan is None:
            return {}
        result = asdict(self.plan)
        for block in ("charge", "pause"):
            for key in ("start", "end"):
                result[block][key] = datetime.fromtimestamp(result[block][key], UTC).isoformat()
        energy = self.plan.energy_kwh
        if energy is not None:
            result["estimated_saving_at_import_tariff"] = round(energy * self.plan.saving_per_kwh, 4)
        return result
