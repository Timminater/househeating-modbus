import pytest
from fake_unit import FakeUnit

from househeating_modbus import DeviceConfig, HeatPump, WriteRejected
from househeating_modbus.controls import DHW_MODES, SPACE_MODES, dhw_plan, floor_plan, space_plan
from househeating_modbus.registers import MODE_OPTIONS


def apply(raw, commands):
    result = dict(raw)
    for key, value in commands:
        if key == "power":
            result[0x305] = int(value)
        else:
            result[0x304] = MODE_OPTIONS[value]
    return result


@pytest.mark.parametrize("mode", sorted(MODE_OPTIONS.values()))
@pytest.mark.parametrize("power", [0, 1])
@pytest.mark.parametrize("requested", ["off", "heat", "cool", "floor_heating"])
def test_space_mode_matrix(mode, power, requested):
    raw = {0x304: mode, 0x305: power}
    result = apply(raw, space_plan(raw, requested))
    if requested == "off":
        assert result[0x305] == (power if mode in DHW_MODES else 0)
        if power and mode in DHW_MODES:
            assert result[0x304] == 2
    else:
        assert SPACE_MODES[result[0x304]] == requested
        # Only hot water that is actually running is retained.
        assert (result[0x304] in DHW_MODES) == (power == 1 and mode in DHW_MODES)
        assert result[0x305] == 1


@pytest.mark.parametrize("mode", sorted(MODE_OPTIONS.values()))
@pytest.mark.parametrize("power", [0, 1])
@pytest.mark.parametrize("enabled", [False, True])
def test_dhw_mode_matrix(mode, power, enabled):
    raw = {0x304: mode, 0x305: power}
    result = apply(raw, dhw_plan(raw, enabled))
    if enabled and not power:
        # A remembered space mode of a stopped unit must not start with hot water.
        assert result[0x304] == 2 and result[0x305] == 1
        return
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
    await pump.async_write("dhw_setpoint", 75)
    assert unit.writes == [(0x302, 750)]
    with pytest.raises(WriteRejected):
        await pump.async_write("heating_setpoint", 61)
    pump.config = DeviceConfig(verify_delay=0)
    with pytest.raises(WriteRejected):
        await pump.async_write("dhw_setpoint", 66)


@pytest.mark.asyncio
async def test_fast_optional_updates_without_slow_refresh_and_failure_clears():
    unit = FakeUnit()
    pump = HeatPump(unit)
    await pump.async_update()
    slow = pump.snapshot.optional_timestamp
    unit.data[0x54] = 510
    unit.data[0x5C] = 333
    await pump.async_update()
    assert pump.snapshot.value("dhw_temperature", pump.config) == 51
    assert pump.snapshot.value("input_power", pump.config) == 3.33
    assert pump.snapshot.optional_timestamp == slow
    unit.fail_addresses.add(0x54)
    await pump.async_update()
    assert pump.snapshot.value("dhw_temperature", pump.config) is None
    assert pump.snapshot.layout_valid
    unit.fail_addresses.clear()
    await pump.async_update()
    assert pump.snapshot.value("dhw_temperature", pump.config) == 51


@pytest.mark.parametrize("mode", sorted(MODE_OPTIONS.values()))
@pytest.mark.parametrize("power", [0, 1])
@pytest.mark.parametrize("enabled", [False, True])
def test_floor_heating_switch_matrix(mode, power, enabled):
    raw = {0x304: mode, 0x305: power}
    if mode not in (1, 3, 5, 7):
        with pytest.raises(WriteRejected):
            floor_plan(raw, enabled)
        return
    commands = floor_plan(raw, enabled)
    assert all(key == "operating_mode" for key, _ in commands)
    result = apply(raw, commands)
    assert (result[0x304] in (3, 7)) == enabled
    # Hot water, power and (implicitly) the profile are never touched.
    assert (result[0x304] in DHW_MODES) == (mode in DHW_MODES)
    assert result[0x305] == power


@pytest.mark.asyncio
async def test_hot_water_inputs_read_without_extended_groups():
    unit = FakeUnit()
    pump = HeatPump(unit, DeviceConfig(extended=False, curves=False))
    snap = await pump.async_update()
    assert snap.value("dhw_temperature", pump.config) == 50
    assert snap.raw[0x130] == 1
    assert not any(a == 0x72 or a == 0x51 for a, _ in unit.reads)
    probe_unit = FakeUnit()
    probe = HeatPump(probe_unit, DeviceConfig(extended=False, curves=False, hot_water=False))
    await probe.async_update()
    assert not any(a in (0x54, 0x130) for a, _ in probe_unit.reads)
