"""Real HA 2026.10.1 classes and schemas; only the physical Modbus unit is simulated."""
import importlib
import asyncio
from pathlib import Path
from types import MappingProxyType
import sys
from contextlib import asynccontextmanager

import pytest
import probatio
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntries
from homeassistant.components.climate import HVACMode
from homeassistant.components.water_heater import STATE_HEAT_PUMP, STATE_OFF
from homeassistant.exceptions import HomeAssistantError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from fake_unit import FakeUnit
from custom_components.househeating import config_flow
from custom_components.househeating._vendor.househeating_modbus import HeatPump, DeviceConfig
from custom_components.househeating.climate import HouseHeatingClimate
from custom_components.househeating.water_heater import HouseHeatingWaterHeater
from custom_components.househeating.coordinator import HouseHeatingCoordinator


async def harness(tmp_path, *, authorized=True):
    hass = HomeAssistant(str(tmp_path))
    entry = ConfigEntry(version=1, minor_version=1, domain='househeating',
                        title='Test', data={'name': 'Test'}, options={}, source='user',
                        unique_id='test', discovery_keys=MappingProxyType({}), subentries_data=None)
    unit = FakeUnit()
    pump = HeatPump(unit, DeviceConfig(verify_delay=0))
    await pump.async_update()
    if authorized:
        pump.authorized_identity = pump.validate_for_control().fingerprint
    coordinator = HouseHeatingCoordinator(hass, entry, pump, 30)
    coordinator.data = pump.snapshot
    return coordinator, unit


def test_actual_imports_and_schemas():
    for part in ('', 'config_flow', 'climate', 'water_heater', 'sensor', 'binary_sensor',
                 'number', 'select', 'switch', 'button', 'diagnostics'):
        importlib.import_module('custom_components.househeating' + ('.' + part if part else ''))
    assert isinstance(config_flow.connection_schema({}), probatio.Schema)
    for divisor in ('1', '10'):
        data = config_flow.connection_schema({})({'name': 'Test', 'transport': 'tcp',
                    'host': '192.0.2.1', 'unit_id': 1, 'measurement_divisor': divisor,
                    'setpoint_divisor': divisor})
        assert data['setpoint_divisor'] == divisor
    with pytest.raises(probatio.Invalid):
        config_flow.connection_schema({})({'name':'Test', 'transport':'tcp', 'unit_id':0})


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
    assert unit.writes == [(0x304, 5)]
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
    monkeypatch.setattr(config_flow, 'async_get_temporary_unit', temporary)
    flow = config_flow.HouseHeatingConfigFlow()
    flow.hass = hass
    flow.context = {'source': 'user'}
    form = await flow.async_step_user()
    assert isinstance(form['data_schema'], probatio.Schema)
    result = await flow.async_step_user({'name':'Test', 'transport':'tcp', 'host':'192.0.2.1',
                    'unit_id':1, 'measurement_divisor':'1', 'setpoint_divisor':'10'})
    assert result['options']['measurement_divisor'] == 1
    assert result['options']['setpoint_divisor'] == 10
    assert result['options']['allow_control'] is False
    assert not unit.writes


@pytest.mark.asyncio
async def test_live_setpoint_route_and_global_profile(tmp_path):
    coordinator, unit = await harness(tmp_path)
    climate = HouseHeatingClimate(coordinator)
    await climate.async_set_hvac_mode(HVACMode.COOL)
    await climate.async_set_temperature(temperature=18)
    assert unit.data[0x300] == 180
    await climate.async_set_preset_mode('floor_heating')
    await climate.async_set_temperature(temperature=36)
    assert unit.data[0x303] == 360
    await climate.async_set_preset_mode('silent')
    assert unit.data[0x307] == 2
    await HouseHeatingWaterHeater(coordinator).async_turn_off()
    assert unit.data[0x307] == 2
    await climate.async_set_preset_mode('floor_heating')
    assert unit.data[0x307] == 0 and climate.preset_mode == 'floor_heating'
    await climate.async_set_preset_mode('standard')
    assert unit.data[0x304] == 1 and climate.preset_mode == 'standard'


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
    await asyncio.gather(HouseHeatingClimate(coordinator).async_turn_off(),
                         HouseHeatingWaterHeater(coordinator).async_turn_off())
    assert unit.data[0x305] == 0
    assert unit.max_active == 1
