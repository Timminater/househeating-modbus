"""Real HA 2026.10.1 classes and schemas; only the physical Modbus unit is simulated."""

import asyncio
import importlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import MappingProxyType

import probatio
import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.components.water_heater import STATE_HEAT_PUMP, STATE_OFF
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from fake_unit import FakeUnit

from custom_components.househeating import config_flow
from custom_components.househeating._vendor.househeating_modbus import DeviceConfig, HeatPump
from custom_components.househeating.climate import HouseHeatingClimate
from custom_components.househeating.coordinator import HouseHeatingCoordinator
from custom_components.househeating.switch import HouseHeatingFloorHeating
from custom_components.househeating.water_heater import HouseHeatingWaterHeater


async def harness(tmp_path, *, authorized=True):
    hass = HomeAssistant(str(tmp_path))
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="househeating",
        title="Test",
        data={"name": "Test"},
        options={},
        source="user",
        unique_id="test",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    unit = FakeUnit()
    pump = HeatPump(unit, DeviceConfig(verify_delay=0))
    await pump.async_update()
    if authorized:
        pump.authorized_identity = pump.validate_for_control().fingerprint
    coordinator = HouseHeatingCoordinator(hass, entry, pump, 30)
    coordinator.data = pump.snapshot
    return coordinator, unit


def test_actual_imports_and_schemas():
    for part in (
        "",
        "config_flow",
        "climate",
        "water_heater",
        "sensor",
        "binary_sensor",
        "number",
        "select",
        "switch",
        "button",
        "diagnostics",
    ):
        importlib.import_module("custom_components.househeating" + ("." + part if part else ""))
    assert isinstance(config_flow.connection_schema({}), probatio.Schema)
    for divisor in ("1", "10"):
        data = config_flow.connection_schema({})(
            {
                "name": "Test",
                "transport": "tcp",
                "host": "192.0.2.1",
                "unit_id": 1,
                "measurement_divisor": divisor,
                "setpoint_divisor": divisor,
            }
        )
        assert data["setpoint_divisor"] == divisor
    with pytest.raises(probatio.Invalid):
        config_flow.connection_schema({})({"name": "Test", "transport": "tcp", "unit_id": 0})


@pytest.mark.asyncio
async def test_real_entities_construct_and_measure(tmp_path):
    coordinator, _ = await harness(tmp_path)
    climate = HouseHeatingClimate(coordinator)
    boiler = HouseHeatingWaterHeater(coordinator)
    assert climate.available and boiler.available
    assert climate.current_temperature == 32
    assert climate.target_temperature == 35
    assert climate.hvac_mode == HVACMode.HEAT
    assert boiler.current_temperature == 50
    assert boiler.max_temp == 65
    assert boiler.operation_list == [STATE_OFF, STATE_HEAT_PUMP]
    assert climate.unique_id != boiler.unique_id


@pytest.mark.asyncio
async def test_combined_controls_preserve_other_function(tmp_path):
    coordinator, unit = await harness(tmp_path)
    climate = HouseHeatingClimate(coordinator)
    boiler = HouseHeatingWaterHeater(coordinator)
    await climate.async_turn_off()
    assert unit.data[0x304] == 2 and unit.data[0x305] == 1
    await climate.async_set_hvac_mode(HVACMode.COOL)
    assert unit.data[0x304] == 4
    await boiler.async_turn_off()
    assert unit.data[0x304] == 0 and unit.data[0x305] == 1
    await boiler.async_turn_on()
    assert unit.data[0x304] == 4 and unit.data[0x307] == 0


@pytest.mark.asyncio
async def test_locked_services_never_write(tmp_path):
    coordinator, unit = await harness(tmp_path, authorized=False)
    climate = HouseHeatingClimate(coordinator)
    boiler = HouseHeatingWaterHeater(coordinator)
    assert not climate.available and not boiler.available
    for operation in (climate.async_turn_on, boiler.async_turn_on):
        with pytest.raises(HomeAssistantError):
            await operation()
    assert not unit.writes


@pytest.mark.asyncio
async def test_uncertain_first_write_never_powers_on(tmp_path):
    coordinator, unit = await harness(tmp_path)
    unit.data[0x304], unit.data[0x305] = 1, 0
    unit.ack_error = True
    with pytest.raises(HomeAssistantError):
        await HouseHeatingWaterHeater(coordinator).async_turn_on()
    assert unit.writes == [(0x304, 2)]
    assert unit.data[0x305] == 0


@pytest.mark.asyncio
async def test_optional_missing_and_recovery(tmp_path):
    coordinator, unit = await harness(tmp_path)
    boiler = HouseHeatingWaterHeater(coordinator)
    unit.fail_addresses.add(0x54)
    await coordinator.async_refresh()
    assert not boiler.available and boiler.current_temperature is None
    unit.fail_addresses.clear()
    await coordinator.async_refresh()
    assert boiler.available and boiler.current_temperature == 50


@pytest.mark.asyncio
async def test_real_config_flow_saves_explicit_scaling(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    unit = FakeUnit()

    @asynccontextmanager
    async def temporary(hass, params, unit_id):
        yield unit

    monkeypatch.setattr(config_flow, "async_get_temporary_unit", temporary)
    flow = config_flow.HouseHeatingConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    form = await flow.async_step_user()
    assert isinstance(form["data_schema"], probatio.Schema)
    result = await flow.async_step_user(
        {
            "name": "Test",
            "transport": "tcp",
            "host": "192.0.2.1",
            "unit_id": 1,
            "measurement_divisor": "1",
            "setpoint_divisor": "10",
        }
    )
    assert result["options"]["measurement_divisor"] == 1
    assert result["options"]["setpoint_divisor"] == 10
    assert result["options"]["allow_control"] is False
    assert not unit.writes


@pytest.mark.asyncio
async def test_live_setpoint_route_profile_presets_and_floor_switch(tmp_path):
    coordinator, unit = await harness(tmp_path)
    climate = HouseHeatingClimate(coordinator)
    floor = HouseHeatingFloorHeating(coordinator)
    assert climate.preset_modes == ["standard", "powerful", "silent"]
    await climate.async_set_hvac_mode(HVACMode.COOL)
    await climate.async_set_temperature(temperature=18)
    assert unit.data[0x300] == 180 and unit.data[0x304] == 4
    with pytest.raises(HomeAssistantError):  # floor heating never switches cooling to heating
        await floor.async_turn_on()
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await floor.async_turn_on()
    assert unit.data[0x304] == 7 and floor.is_on and climate.extra_state_attributes["floor_heating"]
    await climate.async_set_temperature(temperature=36)
    assert unit.data[0x303] == 360
    await climate.async_set_preset_mode("silent")
    assert unit.data[0x307] == 2 and unit.data[0x304] == 7 and climate.preset_mode == "silent"
    await HouseHeatingWaterHeater(coordinator).async_turn_off()
    assert unit.data[0x307] == 2 and unit.data[0x304] == 3
    # A profile preset never changes the space mode.
    await climate.async_set_preset_mode("standard")
    assert unit.data[0x307] == 0 and unit.data[0x304] == 3 and climate.preset_mode == "standard"
    await floor.async_turn_off()
    assert unit.data[0x304] == 1 and not floor.is_on and unit.data[0x307] == 0


@pytest.mark.asyncio
async def test_floor_switch_never_starts_a_stopped_unit(tmp_path):
    coordinator, unit = await harness(tmp_path)
    unit.data.update({0x304: 1, 0x305: 0})
    await HouseHeatingFloorHeating(coordinator).async_turn_on()
    assert unit.writes == [(0x304, 3)] and unit.data[0x305] == 0


@pytest.mark.asyncio
async def test_set_temperature_with_hvac_mode(tmp_path):
    from homeassistant.components.climate import ATTR_HVAC_MODE

    coordinator, unit = await harness(tmp_path)
    unit.data.update({0x304: 1, 0x305: 0})
    await HouseHeatingClimate(coordinator).async_set_temperature(temperature=20, **{ATTR_HVAC_MODE: HVACMode.COOL})
    # Mode first, setpoint of the resulting mode, power on last.
    assert unit.writes == [(0x304, 0), (0x300, 200), (0x305, 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,mode,power,expected",
    [
        (1 << 14, 1, 1, HVACAction.HEATING),
        (1 << 14, 7, 1, HVACAction.HEATING),
        (1 << 14, 0, 1, HVACAction.COOLING),
        (1 << 14, 4, 1, None),
        (1 << 12, 1, 1, HVACAction.IDLE),
        (1 << 14, 1, 0, HVACAction.OFF),
        (1 << 14, 2, 1, HVACAction.OFF),
    ],
)
async def test_hvac_action_from_reported_status(tmp_path, status, mode, power, expected):
    coordinator, unit = await harness(tmp_path)
    unit.data.update({0: status, 0x304: mode, 0x305: power})
    await coordinator.async_refresh()
    assert HouseHeatingClimate(coordinator).hvac_action == expected


@pytest.mark.asyncio
async def test_hot_water_from_stopped_unit_starts_only_hot_water(tmp_path):
    coordinator, unit = await harness(tmp_path)
    unit.data.update({0x304: 1, 0x305: 0})
    await HouseHeatingWaterHeater(coordinator).async_turn_on()
    assert unit.writes == [(0x304, 2), (0x305, 1)]
    assert HouseHeatingClimate(coordinator).hvac_mode == HVACMode.OFF


@pytest.mark.asyncio
async def test_water_heater_available_without_extended_groups(tmp_path):
    from dataclasses import replace

    coordinator, unit = await harness(tmp_path)
    coordinator.device.config = replace(coordinator.device.config, extended=False)
    coordinator.force_optional = True
    await coordinator.async_refresh()
    boiler = HouseHeatingWaterHeater(coordinator)
    assert boiler.available and boiler.current_temperature == 50


@pytest.mark.asyncio
async def test_fresh_sensor_fault_blocks_all_platform_commands(tmp_path):
    coordinator, unit = await harness(tmp_path)
    unit.data[2] |= 1 << 7
    with pytest.raises(HomeAssistantError):
        await HouseHeatingClimate(coordinator).async_turn_off()
    assert not unit.writes


@pytest.mark.asyncio
async def test_concurrent_off_commands_do_not_restore_other_function(tmp_path):
    coordinator, unit = await harness(tmp_path)
    unit.delay = 0.001
    await asyncio.gather(
        HouseHeatingClimate(coordinator).async_turn_off(), HouseHeatingWaterHeater(coordinator).async_turn_off()
    )
    assert unit.data[0x305] == 0
    assert unit.max_active == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected", [(0, 0), (4, 0), (1, 1), (5, 1), (3, 3), (7, 3)])
async def test_climate_turn_on_from_stopped_unit_starts_only_space_mode(tmp_path, mode, expected):
    coordinator, unit = await harness(tmp_path)
    unit.data.update({0x304: mode, 0x305: 0})
    await HouseHeatingClimate(coordinator).async_turn_on()
    assert unit.data[0x304] == expected and unit.data[0x305] == 1
    assert unit.writes == ([] if mode == expected else [(0x304, expected)]) + [(0x305, 1)]


@pytest.mark.asyncio
async def test_climate_turn_on_restores_cooling_after_dhw_only(tmp_path):
    coordinator, unit = await harness(tmp_path)
    unit.data[0x304] = 4
    climate = HouseHeatingClimate(coordinator)
    await climate.async_turn_off()
    assert unit.data[0x304] == 2
    # Recreating the entity must not lose the remembered space mode.
    await HouseHeatingClimate(coordinator).async_turn_on()
    assert unit.data[0x304] == 4 and unit.data[0x305] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,power,expected",
    [
        (1 << 13, 1, "fault_shutdown"),
        ((1 << 14) | (1 << 12), 1, "running"),
        (1 << 12, 1, "target_reached"),
        (1 << 15, 1, "waiting"),
        (0, 1, "standby"),
        (0, 0, "off"),
    ],
)
async def test_reported_operation_uses_status_not_temperature_prediction(tmp_path, status, power, expected):
    from custom_components.househeating.sensor import ReportedOperationSensor

    coordinator, unit = await harness(tmp_path)
    unit.data.update({0: status, 0x305: power, 0x11A: 4, 0x11B: 3, 0x125: 0, 0x160: 5})
    coordinator.force_optional = True
    await coordinator.async_refresh()
    sensor = ReportedOperationSensor(coordinator, "reported_operation")
    assert sensor.available
    assert sensor.native_value == expected
    assert sensor.extra_state_attributes["heating_cooling_hysteresis"] == 4
    assert sensor.extra_state_attributes["target_stop_behavior"] == 0
    assert not unit.writes


@pytest.mark.asyncio
async def test_faulted_sensor_entity_unavailable_and_fault_entity_named(tmp_path):
    from custom_components.househeating._vendor.househeating_modbus.registers import BY_KEY
    from custom_components.househeating.binary_sensor import FaultBinary
    from custom_components.househeating.sensor import HouseHeatingSensor

    coordinator, unit = await harness(tmp_path)
    unit.data[5] = 1 << 8
    await coordinator.async_refresh()
    sensor = HouseHeatingSensor(coordinator, BY_KEY["suction_temperature"])
    fault = FaultBinary(coordinator, 5, 8, "suction_sensor_fault")
    assert not sensor.available and sensor.native_value is None
    assert fault.available and fault.is_on
    assert fault.extra_state_attributes["manual_pdf_pages"] == [170, 171]
    unit.data[5] = 0
    await coordinator.async_refresh()
    assert sensor.available and not fault.is_on
