"""Tariff parsing and price control against the HA runtime and a simulated device."""

from datetime import UTC, datetime, timedelta
from time import time
from types import MappingProxyType
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import probatio
import pytest
from homeassistant.config_entries import ConfigEntries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from test_monitoring import MemoryStore, options_flow
from test_real_runtime import harness

from custom_components.househeating import binary_sensor, sensor
from custom_components.househeating.price_control import PriceManager
from custom_components.househeating.price_learning import PriceEnergyLearning
from custom_components.househeating.price_options import DEFAULTS
from custom_components.househeating.price_plan import PricePlan, Tariff, choose_plan, read_tariffs


def forecast(start, prices, minutes=15):
    step = timedelta(minutes=minutes)
    return [
        {
            "start_date": start + index * step,
            "end_date": start + (index + 1) * step,
            "price_tax_included": {"amount": round(price * 10_000_000)},
        }
        for index, price in enumerate(prices)
    ]


@pytest.mark.parametrize("hours", [0.5, 1, 1.5, 2, 2.5, 3])
def test_plan_uses_contiguous_intervals_and_limits_pause(hours):
    start = datetime(2026, 10, 25, 0, tzinfo=UTC)
    rows = read_tariffs({"forecast": forecast(start, [0.2] * 16 + [0.45] * 20)})
    plan = choose_plan(rows, start.timestamp(), hours * 3600, 0.05, 0.1, {})
    assert plan is not None
    assert plan.pause.end - plan.pause.start == hours * 3600
    assert plan.charge.end <= plan.pause.start
    assert plan.saving_per_kwh == pytest.approx(0.23)


def test_hourly_and_missing_intervals():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    attributes = {
        "forecast": [
            {"start_date": start, "electricity_price": -1_000_000},
            {"start_date": start + timedelta(hours=8), "electricity_price": 3_000_000},
        ]
    }
    rows = read_tariffs(attributes)
    assert rows[0].price == -0.1
    assert choose_plan(rows, start.timestamp(), 1800, 0.05, 0.1, {}) is None
    attributes["forecast"][1]["start_date"] = start + timedelta(minutes=30)
    with pytest.raises(ValueError, match="Overlapping"):
        read_tariffs(attributes)
    with pytest.raises(KeyError, match="forecast"):
        read_tariffs({"predict": []})


def test_repeated_local_hour_and_extra_energy():
    zone = ZoneInfo("Europe/Amsterdam")
    start = datetime(2026, 10, 25, 0, tzinfo=UTC)
    rows = forecast(start, [0.20] * 4 + [0.21] * 4)
    for row in rows:
        row["start_date"] = row["start_date"].astimezone(zone).isoformat()
        row["end_date"] = row["end_date"].astimezone(zone).isoformat()
    parsed = read_tariffs({"forecast": rows})
    assert parsed[3].end == parsed[4].start
    assert choose_plan(parsed, start.timestamp(), 3600, 0, 0.1, {}) is None


ROOM = "climate.room"
DEMAND = "binary_sensor.room_demand"
TARIFF = "sensor.renamed_tariff"


def register_tariff(hass):
    return (
        er.async_get(hass)
        .async_get_or_create(
            "sensor",
            "zonneplan_one",
            "installation_current_quarter_hourly_electricity_tariff",
            suggested_object_id="renamed_tariff",
        )
        .entity_id
    )


def test_deferral_chooses_cheaper_block_immediately_after_peak():
    start = datetime(2026, 11, 23, 16, tzinfo=UTC)
    rows = read_tariffs({"forecast": forecast(start, [0.5] * 4 + [0.2] * 8)})
    assert choose_plan(rows, start.timestamp(), 3600, 0.05, 0.1, {}) is None
    plan = choose_plan(rows, start.timestamp(), 3600, 0.05, 0.1, {}, allow_defer=True)
    assert plan.defer
    assert plan.pause.end == plan.charge.start
    assert plan.saving_per_kwh == pytest.approx(0.30)


async def runtime(tmp_path, **config):
    coordinator, unit = await harness(tmp_path)
    unit.data.update({0x304: 3, 0x305: 1, 0x40: 0, 0: 0})
    await coordinator.async_refresh()
    dr.async_setup(coordinator.hass)
    await dr.async_load(coordinator.hass)
    await er.async_load(coordinator.hass, load_empty=True)
    assert register_tariff(coordinator.hass) == TARIFF
    settings = {
        **DEFAULTS,
        "mode": "automatic",
        "authorization": "confirmed",
        "price_entity": TARIFF,
        "demand_entities": [DEMAND],
        "comfort_entities": [ROOM],
        **config,
    }
    object.__setattr__(coordinator.entry, "options", MappingProxyType({"price_control": settings}))
    manager = PriceManager(coordinator.hass, coordinator)
    manager.store = MemoryStore()
    await manager.load()
    now = time()
    start = datetime.fromtimestamp(now - 1800, UTC)
    manager.hass.states.async_set(TARIFF, "0.40", {"forecast": forecast(start, [0.4] * 10)})
    manager.hass.states.async_set(DEMAND, "on")
    manager.hass.states.async_set(ROOM, "heat", {"current_temperature": 21, "temperature": 20.5})
    manager.plan = PricePlan(Tariff(now - 7200, now - 3600, 0.2), Tariff(now - 30, now + 1800, 0.4), 0.18, None)
    manager.idle_since = now - 100
    manager.call = AsyncMock()
    return manager, unit


@pytest.mark.asyncio
async def test_advice_entities_track_price_blocks_and_recovery(tmp_path, monkeypatch):
    manager, unit = await runtime(tmp_path, mode="advice")
    coordinator = manager.coordinator
    coordinator.entry.runtime_data = coordinator
    manager.hass.config_entries = ConfigEntries(manager.hass, {})
    monkeypatch.setattr(
        manager.hass.config_entries,
        "async_get_entry",
        lambda entry_id: coordinator.entry if entry_id == coordinator.entry.entry_id else None,
    )
    entities = {}

    def collect(new_entities):
        entities.update((entity.key, entity) for entity in new_entities)

    for platform in (sensor, binary_sensor):
        await platform.async_setup_entry(manager.hass, coordinator.entry, collect)
    assert "price_charge_active" not in entities
    coordinator.price_control = manager
    for platform in (sensor, binary_sensor):
        await platform.async_setup_entry(manager.hass, coordinator.entry, collect)

    assert {key for key in entities if key.startswith("price_")} == {
        "price_plan",
        "price_observed_extra_energy",
        *sensor.PRICE_DETAILS,
        "price_charge_active",
        "price_pause_active",
    }
    summary = entities["price_plan"]
    assert summary.unique_id == f"{coordinator.entry.entry_id}_price_plan"
    cheap = entities["price_charge_active"]
    expensive = entities["price_pause_active"]
    for key, entity in entities.items():
        if key.startswith("price_"):
            assert entity.device_info["identifiers"] == {
                ("househeating", f"{coordinator.entry.entry_id}_price_control")
            }
    assert not cheap.available and not expensive.available

    now = time()
    manager.plan = PricePlan(Tariff(now + 60, now + 120, 0.20), Tariff(now - 60, now + 60, 0.40), 0.18, 2.0, True)
    await manager.update(now)
    assert cheap.available and cheap.is_on is False
    assert expensive.is_on is True
    assert entities["price_charge_start"].native_value == datetime.fromtimestamp(now + 60, UTC)
    assert entities["price_charge_tariff"].native_value == 0.20
    assert entities["price_pause_tariff"].native_value == 0.40
    assert entities["price_saving_per_kwh"].native_value == 0.18
    assert entities["price_estimated_saving"].native_value == 0.36
    assert summary.extra_state_attributes["estimated_saving_at_import_tariff"] == 0.36

    await manager.update(now + 60)
    assert cheap.is_on is True and expensive.is_on is False
    assert summary.extra_state_attributes == {}

    restored = PriceManager(manager.hass, coordinator)
    restored.store = manager.store
    with monkeypatch.context() as clock:
        clock.setattr("custom_components.househeating.price_control.time", lambda: now + 60)
        await restored.load()
    coordinator.price_control = restored
    assert not cheap.available and restored.plan is None
    await restored.update(now + 60)
    assert cheap.is_on is True and expensive.is_on is False

    await restored.update(now + 120)
    assert cheap.is_on is False and expensive.is_on is False
    assert entities["price_estimated_saving"].native_value is None
    restored.hass.states.async_set(TARIFF, "unavailable")
    await restored.update(now + 121)
    assert not expensive.available and expensive.is_on is None
    assert not entities["price_charge_start"].available
    assert entities["price_charge_tariff"].native_value is None
    manager.call.assert_not_awaited()
    assert not unit.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("buffer", [False, True])
async def test_pause_restart_and_comfort_releases_heat(tmp_path, buffer):
    manager, unit = await runtime(tmp_path, buffer=buffer)
    await manager.update(time())
    assert unit.writes == [(0x305, 0)]
    reloaded = PriceManager(manager.hass, manager.coordinator)
    reloaded.store = manager.store
    await reloaded.load()
    await reloaded.update(time())
    assert unit.writes == [(0x305, 0)]
    reloaded.hass.states.async_set(ROOM, "heat", {"current_temperature": 19, "temperature": 20.5})
    await reloaded.update(time())
    assert unit.writes[-1] == (0x305, 1)
    reloaded.hass.states.async_set(ROOM, "heat", {"current_temperature": 21, "temperature": 20.5})
    assert not reloaded.can_pause(time())


@pytest.mark.asyncio
async def test_lost_tariff_resumes_and_manual_toggle_yields_control(tmp_path):
    manager, unit = await runtime(tmp_path)
    await manager.update(time())
    manager.hass.states.async_set(TARIFF, "unavailable")
    await manager.update(time())
    assert unit.writes == [(0x305, 0), (0x305, 1)]
    await manager.coordinator.async_write("power", False)
    await manager.update(time())
    assert manager.status == "manual_override"
    assert unit.writes == [(0x305, 0), (0x305, 1), (0x305, 0)]


@pytest.mark.asyncio
@pytest.mark.parametrize("advice", [False, True])
async def test_pump_runs_on_either_demand_during_price_pause(tmp_path, advice):
    manager, unit = await runtime(
        tmp_path,
        mode="advice" if advice else "automatic",
        buffer=True,
        pump_start="button.start",
        pump_stop="button.stop",
        pump_feedback="sensor.speed",
        floor_pump="switch.floor",
    )
    manager.hass.states.async_set("sensor.speed", "0")
    manager.hass.states.async_set("switch.floor", "off")
    await manager.update(time())
    if advice:
        manager.call.assert_not_awaited()
        assert not unit.writes
        return
    manager.call.assert_awaited_once_with("button", "press", "button.start")
    manager.call.reset_mock()
    manager.pump_retry_at = 0
    manager.hass.states.async_set(DEMAND, "off")
    manager.hass.states.async_set("switch.floor", "on")
    await manager.update(time())
    manager.call.assert_awaited_once_with("button", "press", "button.start")
    assert unit.writes == [(0x305, 0)]


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["defrost", "compressor", "cold_buffer", "missing_price"])
async def test_price_guard(tmp_path, condition):
    manager, unit = await runtime(tmp_path, buffer=True, buffer_entity="sensor.buffer")
    manager.hass.states.async_set("sensor.buffer", "40", {"unit_of_measurement": "Â°C"})
    if condition == "defrost":
        unit.data[0] = 0x100
    elif condition == "compressor":
        unit.data[0x40] = 24
    elif condition == "cold_buffer":
        manager.hass.states.async_set("sensor.buffer", "25", {"unit_of_measurement": "Â°C"})
    else:
        manager.hass.states.async_set(TARIFF, "unavailable")
    await manager.coordinator.async_refresh()
    await manager.update(time())
    assert not unit.writes


@pytest.mark.asyncio
async def test_thermostat_manual_target_is_preserved(tmp_path):
    manager, _ = await runtime(tmp_path, climate_entity=ROOM)
    manager.hass.states.async_set(
        ROOM,
        "heat",
        {
            "current_temperature": 20,
            "temperature": 20.5,
            "max_temp": 30,
            "target_temp_step": 0.1,
        },
    )
    await manager.warm_room(time())
    manager.call.assert_awaited_once_with("climate", "set_temperature", ROOM, temperature=20.8)
    manager.hass.states.async_set(ROOM, "heat", {"temperature": 21})
    await manager.restore_room()
    assert manager.call.await_count == 1
    assert "room" not in manager.saved


@pytest.mark.asyncio
async def test_hold_heats_at_lower_target_and_restores_on_lost_prices(tmp_path):
    manager, unit = await runtime(
        tmp_path,
        buffer=True,
        hold_during_peak=True,
        comfort_margin=0.3,
        climate_entity=ROOM,
    )
    await manager.update(time())
    assert unit.writes == [(0x305, 0)]
    state = {"current_temperature": 20.2, "temperature": 20.5, "max_temp": 30, "target_temp_step": 0.1}

    async def thermostat(domain, service, entity, *, temperature):
        state["temperature"] = temperature
        manager.hass.states.async_set(ROOM, "heat", state)

    manager.call.side_effect = thermostat
    manager.hass.states.async_set(ROOM, "heat", state)
    await manager.update(time())
    assert manager.status == "holding_temperature" and state["temperature"] == 20.3
    assert unit.writes[-1] == (0x305, 1)
    await manager.update(time())
    assert manager.call.await_count == 1
    manager.hass.states.async_set(TARIFF, "unavailable")
    await manager.update(time())
    assert state["temperature"] == 20.5


@pytest.mark.asyncio
@pytest.mark.parametrize("buffer", [False, True])
async def test_verified_water_boost_and_restore_on_both_layouts(tmp_path, buffer):
    manager, unit = await runtime(tmp_path, buffer=buffer, water_boost=2)
    unit.data[0x316] = 0
    await manager.coordinator.async_refresh()
    await manager.adjust_water()
    assert unit.writes == [(0x303, 370)]
    await manager.adjust_water(restore=True)
    assert unit.writes[-1] == (0x303, 350)


@pytest.mark.asyncio
async def test_water_boost_respects_native_curve_and_manual_target(tmp_path):
    manager, unit = await runtime(tmp_path, water_boost=2)
    unit.data[0x316] = 1
    await manager.adjust_water()
    assert not unit.writes
    unit.data[0x316] = 0
    manager.saved.pop("water_attempt")
    await manager.adjust_water()
    assert unit.writes == [(0x303, 370)]
    unit.data[0x303] = 360
    await manager.coordinator.async_refresh()
    await manager.adjust_water(restore=True)
    assert unit.writes == [(0x303, 370)]
    assert unit.data[0x303] == 360


@pytest.mark.asyncio
async def test_form_previews_and_saves_source(tmp_path, monkeypatch):
    flow, _ = await options_flow(tmp_path, monkeypatch)
    assert register_tariff(flow.hass) == TARIFF
    hourly = (
        er.async_get(flow.hass)
        .async_get_or_create(
            "sensor",
            "zonneplan_one",
            "installation_current_electricity_tariff",
            suggested_object_id="hourly_tariff",
        )
        .entity_id
    )
    er.async_get(flow.hass).async_get_or_create(
        "sensor", "zonneplan_one", "installation_current_gas_tariff", suggested_object_id="gas_tariff"
    )
    start = datetime.now(UTC) - timedelta(minutes=5)
    flow.hass.states.async_set(TARIFF, "0.4", {"forecast": forecast(start, [0.4, 0.5])})
    form = await flow.async_step_price_control()
    schema = form["data_schema"]
    assert {key.schema for key in schema.schema} == {"mode", "price_entity", "max_hours", "buffer"}
    price_selector = next(value for key, value in schema.schema.items() if key.schema == "price_entity")
    assert set(price_selector.config["include_entities"]) == {TARIFF, hourly}
    with pytest.raises(probatio.Invalid, match="price_entity"):
        schema({"mode": "advice", "price_entity": "sensor.other"})
    for mode, buffer, expected in (
        ("advice", False, {"comfort", "economics"}),
        ("advice", True, {"comfort", "hydraulics", "economics"}),
        ("automatic", False, {"comfort", "heating", "economics"}),
        ("automatic", True, {"comfort", "heating", "hydraulics", "economics"}),
    ):
        step = await flow.async_step_price_control(schema({"mode": mode, "price_entity": TARIFF, "buffer": buffer}))
        assert step["step_id"] == "price_settings"
        groups = {key.schema: value for key, value in step["data_schema"].schema.items()}
        assert set(groups) == expected
        if buffer:
            fields = {key.schema for key in groups["hydraulics"].schema.schema}
            assert "buffer_min" in fields
            assert ("pump_start" in fields) == (mode == "automatic")
    step = await flow.async_step_price_control(schema({"mode": "advice", "price_entity": TARIFF}))
    data = step["data_schema"]({"comfort": {"preheat_offset": 0.5}})
    preview = await flow.async_step_price_settings(data)
    assert preview["step_id"] == "price_confirm"
    assert preview["description_placeholders"]["price"] == "0.40000"
    result = await flow.async_step_price_confirm({"confirm": True})
    assert result["data"]["price_control"]["mode"] == "advice"
    assert result["data"]["price_control"]["preheat_offset"] == 0.5
    assert "forecast_attribute" not in result["data"]["price_control"]


@pytest.mark.asyncio
async def test_reopening_price_form_prefills_sections_and_allows_clearing(tmp_path, monkeypatch):
    flow, entry = await options_flow(tmp_path, monkeypatch)
    assert register_tariff(flow.hass) == TARIFF
    start = datetime.now(UTC) - timedelta(minutes=5)
    flow.hass.states.async_set(TARIFF, "0.4", {"forecast": forecast(start, [0.4, 0.5])})
    settings = {
        "mode": "advice",
        "price_entity": TARIFF,
        "buffer": True,
        "climate_entity": ROOM,
        "preheat_offset": 0.6,
        "water_boost": 0,
        "allow_defer": True,
        "buffer_entity": "sensor.tank_water",
        "buffer_min": 34,
        "extra_energy": 18,
        "power_entity": "sensor.heat_pump_watts",
        "execution_entity": "input_boolean.price_plan_executed",
    }
    object.__setattr__(entry, "options", MappingProxyType({**entry.options, "price_control": settings}))
    form = await flow.async_step_price_control({"mode": "advice", "price_entity": TARIFF, "buffer": True})
    schema = form["data_schema"]
    groups = {group["name"]: group for group in probatio.to_field_list(schema, custom_serializer=cv.custom_serializer)}
    for name, fields in {
        "comfort": ("climate_entity", "preheat_offset", "water_boost", "allow_defer"),
        "hydraulics": ("buffer_entity", "buffer_min"),
        "economics": ("extra_energy", "power_entity", "execution_entity"),
    }.items():
        group = groups[name]
        # HA treats a section-level default as the entire value and skips its children.
        assert "default" not in group
        children = {child["name"]: child for child in group["schema"]}
        for key in fields:
            assert children[key]["description"]["suggested_value"] == settings[key]

    preview = await flow.async_step_price_settings(schema({"economics": {"extra_energy": 18}}))
    assert preview["step_id"] == "price_confirm"
    result = await flow.async_step_price_confirm({"confirm": True})
    saved = result["data"]["price_control"]
    assert saved["climate_entity"] == ROOM
    assert saved["buffer_entity"] == "sensor.tank_water"
    assert saved["extra_energy"] == 18
    assert "power_entity" not in saved and "execution_entity" not in saved


def test_learns_from_confirmed_price_windows_with_matching_reference():
    learning = PriceEnergyLearning()
    data = {}
    first = 10 * 86400
    duration = 4 * 3600

    def local_slot(stamp):
        return stamp % 86400

    def observe(start, *, plan=None, automatic=False, external=False, gap=False, interrupted=False):
        for minute in range(0, duration // 60 + 1):
            now = start + minute * 60
            preheat = minute < 60
            peak = 60 <= minute < 120
            changed = plan is not None and (automatic or external)
            power = 2200 if changed and preheat else 0 if changed and peak else 1000
            learning.observe(
                data,
                now,
                plan,
                watts=None if gap and minute == 80 else power,
                outdoor=5,
                automatic=automatic,
                external=external and (preheat or peak),
                preheated=automatic and preheat,
                paused=automatic and peak,
                interrupted=interrupted and minute == 80,
                local_slot=local_slot,
            )

    for day in range(4):
        observe(first + day * 86400)
    for day, kind in enumerate(("advice", "auto", "manual", "gap", "interrupted", "auto"), start=4):
        start = first + day * 86400
        plan = PricePlan(Tariff(start, start + 3600, 0.20), Tariff(start + 3600, start + 7200, 0.40), 0.18, 1)
        observe(
            start,
            plan=plan,
            automatic=kind in ("auto", "gap", "interrupted"),
            external=kind == "manual",
            gap=kind == "gap",
            interrupted=kind == "interrupted",
        )
        if day == 6:
            assert learning.estimate(data)["percentage"] is None

    assert learning.estimate(data) == {
        "percentage": 20.0,
        "observed_percentage": 20.0,
        "sample_count": 3,
        "shifted_kwh": 3.0,
        "extra_kwh": 0.6,
    }
