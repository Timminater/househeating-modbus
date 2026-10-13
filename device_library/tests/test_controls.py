import pytest
from househeating_modbus.controls import DHW_MODES, SPACE_MODES, dhw_plan, space_plan
from househeating_modbus import DeviceConfig, HeatPump, WriteRejected
from househeating_modbus.registers import MODE_OPTIONS
from fake_unit import FakeUnit


def apply(raw, commands):
    result = dict(raw)
    for key, value in commands:
        if key == 'power':
            result[0x305] = int(value)
        else:
            result[0x304] = MODE_OPTIONS[value]
    return result


@pytest.mark.parametrize('mode', sorted(MODE_OPTIONS.values()))
@pytest.mark.parametrize('power', [0, 1])
@pytest.mark.parametrize('requested', ['off', 'heat', 'cool', 'floor_heating'])
def test_space_mode_matrix(mode, power, requested):
    raw = {0x304: mode, 0x305: power}
    result = apply(raw, space_plan(raw, requested))
    if requested == 'off':
        assert result[0x305] == (power if mode in DHW_MODES else 0)
        if power and mode in DHW_MODES:
            assert result[0x304] == 2
    else:
        assert SPACE_MODES[result[0x304]] == requested
        assert (result[0x304] in DHW_MODES) == (mode in DHW_MODES)
        assert result[0x305] == 1


@pytest.mark.parametrize('mode', sorted(MODE_OPTIONS.values()))
@pytest.mark.parametrize('power', [0, 1])
@pytest.mark.parametrize('enabled', [False, True])
def test_dhw_mode_matrix(mode, power, enabled):
    raw = {0x304: mode, 0x305: power}
    result = apply(raw, dhw_plan(raw, enabled))
    assert SPACE_MODES.get(result[0x304]) == SPACE_MODES.get(mode)
    if enabled:
        assert result[0x304] in DHW_MODES and result[0x305] == 1
    elif mode == 2:
        assert result[0x305] == 0
    else:
        assert result[0x304] not in DHW_MODES and result[0x305] == power


@pytest.mark.asyncio
async def test_dhw_75_is_opt_in_heating_stays_60():
    unit = FakeUnit()
    pump = HeatPump(unit, DeviceConfig(max_dhw=75, verify_delay=0))
    await pump.async_update()
    pump.authorized_identity = pump.validate_for_control().fingerprint
    await pump.async_write('dhw_setpoint', 75)
    assert unit.writes == [(0x302, 750)]
    with pytest.raises(WriteRejected):
        await pump.async_write('heating_setpoint', 61)
    pump.config = DeviceConfig(verify_delay=0)
    with pytest.raises(WriteRejected):
        await pump.async_write('dhw_setpoint', 66)


@pytest.mark.asyncio
async def test_fast_optional_updates_without_slow_refresh_and_failure_clears():
    unit = FakeUnit()
    pump = HeatPump(unit)
    await pump.async_update()
    slow = pump.snapshot.optional_timestamp
    unit.data[0x54] = 510
    unit.data[0x5C] = 333
    await pump.async_update()
    assert pump.snapshot.value('dhw_temperature', pump.config) == 51
    assert pump.snapshot.value('input_power', pump.config) == 3.33
    assert pump.snapshot.optional_timestamp == slow
    unit.fail_addresses.add(0x54)
    await pump.async_update()
    assert pump.snapshot.value('dhw_temperature', pump.config) is None
    assert pump.snapshot.layout_valid
    unit.fail_addresses.clear()
    await pump.async_update()
    assert pump.snapshot.value('dhw_temperature', pump.config) == 51
