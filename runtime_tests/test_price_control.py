"""Tariff parsing and price control against the HA runtime and a simulated device."""

from datetime import UTC, datetime, timedelta
from time import time
from types import MappingProxyType
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import probatio
import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from test_monitoring import MemoryStore, options_flow
from test_real_runtime import harness

from custom_components.househeating.price_control import PriceManager
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
