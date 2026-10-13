import asyncio
from dataclasses import replace

import pytest

from househeating_modbus import (BY_KEY, DeviceConfig, HeatPump, Snapshot, CommunicationError,
                                VerificationError, WriteRejected, SELECTS, SETPOINT_KEYS)
from househeating_modbus.models import signed16
from househeating_modbus.registers import WRITABLE_ADDRESSES
from fake_unit import FakeUnit, memory


async def device_ready(config=None, unit=None):
    unit = unit or FakeUnit()
    device = HeatPump(unit, config or DeviceConfig(verify_delay=0))
    await device.async_update()
    identity = device.validate_for_control()
    device.authorized_identity = identity.fingerprint
    return device, unit


@pytest.mark.asyncio
async def test_startup_is_read_only_and_pacing_delegated():
    unit = FakeUnit()
    device = HeatPump(unit)
    result = await device.async_update()
    assert not unit.writes
    assert unit.spacing == .12 and unit.timeout == 5
    assert result.layout_valid
    assert not device.control_ready
    assert result.value("water_outlet_temperature", device.config) == 32
    assert result.value("input_power", device.config) == 2.57
    assert all(0 < count <= 16 for _, count in unit.reads)


@pytest.mark.parametrize("measurement_divisor,setpoint_divisor", [(1, 1), (1, 10), (10, 1), (10, 10)])
@pytest.mark.asyncio
async def test_independent_scaling(measurement_divisor, setpoint_divisor):
    config = DeviceConfig(measurement_divisor=measurement_divisor, setpoint_divisor=setpoint_divisor, verify_delay=0)
    unit = FakeUnit(memory(setpoint_divisor, measurement_divisor))
    device, unit = await device_ready(config, unit)
    assert device.snapshot.value("water_outlet_temperature", config) == 32
    await device.async_write("floor_setpoint", 38)
    assert unit.writes == [(0x303, 38 * setpoint_divisor)]


@pytest.mark.parametrize("raw,expected", [(0, 0), (32767, 32767), (32768, -32768), (65535, -1), (65436, -100)])
def test_signed(raw, expected):
    assert signed16(raw) == expected


def test_temperature_negative_point_one_not_sentinel():
    assert Snapshot({0x4A: 65535}).value("outdoor_temperature", DeviceConfig()) == -.1
    assert Snapshot({0x4A: 32768}).value("outdoor_temperature", DeviceConfig()) is None


@pytest.mark.parametrize("address,bit,key", [(2, 7, "water_inlet_temperature"), (2, 13, "water_outlet_temperature"),
                                            (4, 8, "buffer_temperature"), (2, 6, "dhw_temperature")])
def test_faulted_temperature_is_not_exposed(address, bit, key):
    raw = memory()
    raw[BY_KEY[key].address] = 350
    raw[address] = 1 << bit
    assert Snapshot(raw).value(key, DeviceConfig()) is None


@pytest.mark.parametrize("key,value", [("factory_reset", 1), ("compressor_force", 80), ("0x0330", 8192),
                                       ("water_outlet_temperature", 30), ("buffer_temperature", 30)])
@pytest.mark.asyncio
async def test_no_access_to_service_or_measurement_writes(key, value):
    device, unit = await device_ready()
    before = list(unit.reads)
    with pytest.raises(WriteRejected):
        await device.async_write(key, value)
    assert not unit.writes and unit.reads == before


@pytest.mark.asyncio
async def test_locked_controls_do_no_io():
    unit = FakeUnit()
    device = HeatPump(unit)
    with pytest.raises(WriteRejected):
        await device.async_write("power", True)
    assert not unit.writes and not unit.reads


@pytest.mark.parametrize("key,value", [("heating_setpoint", 61), ("floor_setpoint", 46), ("dhw_setpoint", 66),
                                       ("cooling_setpoint", 6), ("floor_setpoint", 19),
                                       ("heating_setpoint", float("nan")), ("heating_setpoint", float("inf")),
                                       ("heating_setpoint", 35.5), ("floor_setpoint", True),
                                       ("power", 2), ("power", "on"), ("operating_mode", "reserve"),
                                       ("operating_profile", "turbo"), ("heating_curve", "high_9")])
@pytest.mark.asyncio
async def test_reject_invalid_values(key, value):
    device, unit = await device_ready()
    with pytest.raises(WriteRejected):
        await device.async_write(key, value)
    assert not unit.writes


@pytest.mark.parametrize("key", SETPOINT_KEYS)
@pytest.mark.asyncio
async def test_verified_setpoint_write_only_changes_its_own_register(key):
    device, unit = await device_ready()
    initial = dict(unit.data)
    value = 15 if key == "cooling_setpoint" else 40
    await device.async_write(key, value)
    changed = {a for a in unit.data if unit.data[a] != initial[a]}
    assert changed == {BY_KEY[key].address}
    assert len(unit.writes) == 1
    assert device.last_write["result"] == "verified"
    assert device.snapshot.value(key, device.config) == value


@pytest.mark.parametrize("key,option", [(key, option) for key, options in SELECTS.items() for option in options])
@pytest.mark.asyncio
async def test_select_options(key, option):
    device, unit = await device_ready()
    before_power = unit.data[0x305]
    await device.async_write(key, option)
    assert unit.data[BY_KEY[key].address] == SELECTS[key][option]
    assert unit.data[0x305] == before_power
    assert len(unit.writes) <= 1
    assert all(a in WRITABLE_ADDRESSES for a, _ in unit.writes)


@pytest.mark.asyncio
async def test_idempotent_setpoint_does_not_rewrite():
    device, unit = await device_ready()
    await device.async_write("heating_setpoint", 35)
    assert not unit.writes
    assert device.last_write["result"] == "unchanged"


@pytest.mark.asyncio
async def test_wrong_scaling_cannot_be_authorized():
    unit = FakeUnit(memory(divisor=1))
    device = HeatPump(unit, DeviceConfig())
    await device.async_update()
    with pytest.raises(WriteRejected):
        device.validate_for_control()
    assert not unit.writes


@pytest.mark.asyncio
async def test_wrong_scaling_on_fresh_read_does_not_write():
    device, unit = await device_ready()
    unit.data[0x301] = 35
    with pytest.raises(WriteRejected):
        await device.async_write("heating_setpoint", 40)
    assert not unit.writes


@pytest.mark.asyncio
async def test_changed_identity_locks_control():
    device, unit = await device_ready()
    unit.data[0x360] += 1
    with pytest.raises(WriteRejected):
        await device.async_write("power", False)
    assert device.authorized_identity is None
    assert not unit.writes


@pytest.mark.asyncio
async def test_identity_read_failure_blocks_write():
    device, unit = await device_ready()
    unit.fail_addresses.add(0x360)
    with pytest.raises(CommunicationError):
        await device.async_write("power", False)
    assert not unit.writes


@pytest.mark.asyncio
async def test_missing_identity_still_allows_monitoring():
    unit = FakeUnit()
    unit.fail_addresses.add(0x360)
    device = HeatPump(unit)
    snapshot = await device.async_update()
    assert snapshot.layout_valid and snapshot.identity is None
    assert "identity" in snapshot.errors
    with pytest.raises(WriteRejected):
        device.validate_for_control()


@pytest.mark.asyncio
async def test_protocol_version_gates_curve_reads_and_writes():
    device, unit = await device_ready(unit=FakeUnit(memory(protocol=120)))
    assert not any(address == 0x313 for address, _ in unit.reads)
    with pytest.raises(WriteRejected):
        await device.async_write("heating_curve", "high_2")
    assert not unit.writes


@pytest.mark.asyncio
async def test_failed_optional_block_does_not_poison_primary_or_reuse_old_data():
    device, unit = await device_ready()
    assert device.snapshot.value("buffer_temperature", device.config) == 31
    unit.fail_addresses.add(0x74)
    snapshot = await device.async_update(force_optional=True)
    assert snapshot.value("buffer_temperature", device.config) is None
    assert snapshot.value("water_outlet_temperature", device.config) == 32
    assert "zones" in snapshot.errors


@pytest.mark.asyncio
async def test_mandatory_failure_does_not_publish_partial_snapshot():
    device, unit = await device_ready()
    before = device.snapshot
    unit.data[0] = 123
    unit.fail_addresses.add(0x300)
    with pytest.raises(CommunicationError):
        await device.async_update()
    assert device.snapshot is before
    assert not device._slow_raw


@pytest.mark.parametrize("payload", [[], [1], ["12"] * 10, [True] * 10, [-1] * 10, [65536] * 10])
@pytest.mark.asyncio
async def test_invalid_payload(payload):
    unit = FakeUnit()
    unit.bad_payload = payload
    with pytest.raises(CommunicationError):
        await HeatPump(unit).async_update()
    assert not unit.writes


@pytest.mark.asyncio
async def test_write_rejected_by_device_is_not_retried_or_optimistic():
    device, unit = await device_ready()
    unit.drop_write = True
    before = device.snapshot.raw[0x301]
    with pytest.raises(VerificationError):
        await device.async_write("heating_setpoint", 40)
    assert unit.writes == [(0x301, 400)]
    assert device.snapshot.raw[0x301] == before
    assert device.last_write["result"] == "unconfirmed"


@pytest.mark.asyncio
async def test_ack_lost_after_real_change_never_retries_write():
    device, unit = await device_ready()
    unit.ack_error = True
    with pytest.raises(VerificationError):
        await device.async_write("heating_setpoint", 40)
    assert unit.data[0x301] == 400
    assert len(unit.writes) == 1


@pytest.mark.asyncio
async def test_curve_cache_does_not_revert_verified_result():
    device, unit = await device_ready()
    await device.async_write("heating_curve", "low_3")
    await device.async_update()
    assert device.snapshot.raw[0x314] == 13


@pytest.mark.asyncio
async def test_concurrent_poll_and_commands_are_serialized():
    device, unit = await device_ready()
    unit.delay = .001
    await asyncio.gather(device.async_update(), device.async_write("heating_setpoint", 40),
                         device.async_write("floor_setpoint", 38))
    assert unit.max_active == 1
    assert len(unit.writes) == 2


@pytest.mark.asyncio
async def test_cancellation_is_propagated():
    unit = FakeUnit()
    unit.delay = 10
    task = asyncio.create_task(HeatPump(unit).async_update())
    await asyncio.sleep(.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not unit.writes


@pytest.mark.parametrize("kwargs", [{"measurement_divisor": 2}, {"setpoint_divisor": 0},
                                    {"max_read": 101}, {"max_read": 0}, {"spacing": .01},
                                    {"max_floor": 65}, {"max_dhw": 70}, {"timeout": float("nan")}])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        DeviceConfig(**kwargs)


def test_all_write_addresses_are_only_normal_user_settings():
    assert WRITABLE_ADDRESSES == frozenset((0x300, 0x301, 0x302, 0x303, 0x304,
                                          0x305, 0x307, 0x313, 0x314, 0x315, 0x316))


def test_fault_bit_labels_preserve_unknown_bits():
    snapshot = Snapshot({2: 1 << 7, 5: 1 << 8})
    assert snapshot.faults == ["inlet_sensor_fault", "word_0005_bit_8"]


@pytest.mark.asyncio
async def test_idempotent_curve_adopts_externally_changed_value():
    device, unit = await device_ready()
    unit.data[0x314] = 12
    await device.async_write("heating_curve", "low_2")
    assert not unit.writes
    await device.async_update()
    assert device.snapshot.raw[0x314] == 12


@pytest.mark.parametrize("config", [{"measurement_divisor": True}, {"max_read": 1.5}])
def test_reject_wrong_types(config):
    with pytest.raises(ValueError):
        DeviceConfig(**config)


@pytest.mark.asyncio
async def test_disabled_curves_cannot_be_written():
    device, unit = await device_ready(config=DeviceConfig(curves=False, verify_delay=0))
    with pytest.raises(WriteRejected):
        await device.async_write("heating_curve", "high_2")
    assert not unit.writes
