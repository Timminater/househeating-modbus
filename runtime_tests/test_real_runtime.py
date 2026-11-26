"""Real HA 2026.10.1 classes and schemas; only the physical Modbus unit is simulated."""

import asyncio
import importlib
import sys
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import probatio
import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.components.water_heater import STATE_HEAT_PUMP, STATE_OFF
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, Unauthorized

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


@pytest.mark.asyncio
async def test_register_browser_reads_only_documented_addresses(tmp_path, monkeypatch):
    from inspect import unwrap

    from homeassistant.components.frontend import DATA_PANELS
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    from custom_components.househeating import register_browser as browser

    coordinator, unit = await harness(tmp_path)
    entry = coordinator.entry
    hass = coordinator.hass
    hass.config_entries = ConfigEntries(hass, {})
    dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    entry.runtime_data = coordinator
    monkeypatch.setattr(hass.config_entries, "async_entries", lambda domain: [entry])
    monkeypatch.setattr(
        hass.config_entries, "async_get_entry", lambda entry_id: entry if entry_id == entry.entry_id else None
    )
    monkeypatch.setattr(hass, "http", SimpleNamespace(async_register_static_paths=AsyncMock()), raising=False)
    await browser.async_register_browser(hass)
    panel = hass.data[DATA_PANELS][browser.REGISTER_PANEL_PATH]
    revision = sha256(browser.SCRIPT_PATH.read_bytes()).hexdigest()[:16]
    script_url = f"/househeating_static/register_browser-{revision}.js"
    assert panel.require_admin and panel.config["_panel_custom"]["module_url"] == script_url
    assert panel.config["_panel_custom"]["name"] == f"househeating-register-browser-{revision}"
    assert hass.http.async_register_static_paths.call_args.args[0][0].url_path == script_url
    assert panel.sidebar_title is None and panel.config_panel_domain is None
    handler, schema = hass.data["websocket_api"]["househeating/register_browser/read"]
    assert handler is browser.ws_read
    assert schema({"id": 1, "type": "househeating/register_browser/read", "entry_id": entry.entry_id, "address": 39})

    connection = SimpleNamespace(user=SimpleNamespace(is_admin=False), send_result=Mock(), send_error=Mock())
    message = {"id": 1, "entry_id": entry.entry_id}
    with pytest.raises(Unauthorized):
        browser.ws_read(hass, connection, {**message, "address": 0x0027})
    connection.user.is_admin = True
    registry = er.async_get(hass)
    relay = registry.async_get_or_create(
        "binary_sensor",
        "househeating",
        f"{entry.entry_id}_zone_1_pump_active",
        config_entry=entry,
        suggested_object_id="renamed_zone_pump",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )
    reads_before = list(unit.reads)
    browser.ws_catalog(hass, connection, message)
    assert any(row[:3] == (0x001C, 0x001C, 4) for row in connection.send_result.call_args.args[1]["rows"])
    browser.ws_snapshot(hass, connection, message)
    assert connection.send_result.call_args.args[1]["samples"][0x004F]["value"] == 28
    assert connection.send_result.call_args.args[1]["entities"]["28:4"] == [
        {"id": relay.entity_id, "name": None, "enabled": False}
    ]
    registry.async_update_entity(relay.entity_id, disabled_by=None)
    browser.ws_snapshot(hass, connection, message)
    assert connection.send_result.call_args.args[1]["entities"]["28:4"][0]["enabled"]
    registry.async_update_entity(relay.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    browser.ws_snapshot(hass, connection, message)
    assert not connection.send_result.call_args.args[1]["entities"]["28:4"][0]["enabled"]
    assert unit.reads == reads_before

    read = unwrap(browser.ws_read)
    snapshot = coordinator.device.snapshot
    unit.data[0x0027] = 47
    await read(hass, connection, {**message, "address": 0x0027})
    sample = connection.send_result.call_args.args[1]
    assert sample["raw"] == 47 and sample["source"] == "manual" and sample["at"] >= snapshot.timestamp
    assert coordinator.device.snapshot is snapshot
    await read(hass, connection, {**message, "address": 0x003F})
    assert connection.send_error.call_args.args[1] == "not_documented"
    assert unit.reads == [*reads_before, (0x0027, 1)]

    unit.read_coils = AsyncMock(return_value=[True])
    await read(hass, connection, {**message, "address": 0x1001})
    unit.read_coils.assert_awaited_once_with(0x1001, 1)
    assert connection.send_result.call_args.args[1]["raw"] == 1
    unit.fail_addresses.add(0x0027)
    await read(hass, connection, {**message, "address": 0x0027})
    assert connection.send_error.call_args.args[1] == "read_failed"
    assert not unit.writes

    handler, schema = hass.data["websocket_api"]["househeating/register_browser/write"]
    assert handler is browser.ws_write
    request = schema(
        {
            **message,
            "type": "househeating/register_browser/write",
            "address": 0x013A,
            "value": 35,
            "expected": 40,
        }
    )
    connection.user.is_admin = False
    with pytest.raises(Unauthorized):
        browser.ws_write(hass, connection, request)
    connection.user.is_admin = True
    write = unwrap(browser.ws_write)
    unit.data[0x013A] = 40
    await write(hass, connection, {**request, "address": 0x001C})
    assert connection.send_error.call_args.args[1] == "not_writable"
    await write(hass, connection, {**request, "expected": 39})
    assert connection.send_error.call_args.args[1] == "command_rejected"
    await write(hass, connection, {**request, "value": 61})
    assert connection.send_error.call_args.args[1] == "command_rejected"
    assert not unit.writes

    unit.drop_write = True
    await write(hass, connection, request)
    assert connection.send_error.call_args.args[1] == "command_failed"
    assert unit.writes == [(0x013A, 35)]
    unit.drop_write = False
    await write(hass, connection, request)
    result = connection.send_result.call_args.args[1]
    assert result["result"] == "verified"
    assert result["sample"]["raw"] == unit.data[0x013A] == 35
    assert unit.writes == [(0x013A, 35), (0x013A, 35)]
    await write(hass, connection, {**request, "expected": 35})
    assert connection.send_result.call_args.args[1]["result"] == "unchanged"
    assert len(unit.writes) == 2

    browser.ws_catalog(hass, connection, message)
    writable = connection.send_result.call_args.args[1]["writable"]
    assert {0x013A, 0x0192, 0x0800, 0x0331, 0x1000, 0x101D} <= set(writable)
    assert not {0x001C, 0x0308, 0x1018, 0x1002} & set(writable)
    unit.data[0x0192] = 35
    await write(hass, connection, {**request, "address": 0x0192, "expected": 35, "value": 36})
    assert connection.send_result.call_args.args[1]["sample"]["raw"] == 36
    assert unit.writes[-1] == (0x0192, 36)

    unit.read_coils = AsyncMock(side_effect=[[False], [True]])
    unit.write_coil = AsyncMock()
    await write(hass, connection, {**request, "address": 0x1000, "expected": 0, "value": 1})
    unit.write_coil.assert_awaited_once_with(0x1000, True)
    assert unit.read_coils.await_count == 2
    assert connection.send_result.call_args.args[1]["sample"]["raw"] == 1


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


@pytest.mark.asyncio
async def test_catalog_entities_disabled_by_default_and_poll_enabled_addresses(tmp_path, monkeypatch):
    from datetime import timedelta
    from logging import getLogger

    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_platform import EntityPlatform

    from custom_components.househeating import register_browser as browser
    from custom_components.househeating.binary_sensor import async_setup_entry as setup_binary_sensors
    from custom_components.househeating.entity import CatalogEntity
    from custom_components.househeating.sensor import async_setup_entry as setup_sensors

    coordinator, unit = await harness(tmp_path, authorized=False)
    hass, entry = coordinator.hass, coordinator.entry
    hass.config_entries = ConfigEntries(hass, {})
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _: entry)
    monkeypatch.setattr(hass.config_entries, "async_entries", lambda _: [entry])
    entry.runtime_data = coordinator
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    monkeypatch.setattr(hass, "http", SimpleNamespace(async_register_static_paths=AsyncMock()), raising=False)
    await browser.async_register_browser(hass)
    coordinator.catalog_registers = hass.data[browser.CATALOG_KEY][2]
    reads_before = list(unit.reads)
    platforms = {}
    for domain, setup in (("sensor", setup_sensors), ("binary_sensor", setup_binary_sensors)):
        platform = platforms[domain] = EntityPlatform(
            hass=hass,
            logger=getLogger(__name__),
            domain=domain,
            platform_name="househeating",
            platform=None,
            scan_interval=timedelta(seconds=30),
            entity_namespace=None,
        )
        platform.config_entry = entry
        entities = []
        await setup(hass, entry, entities.extend)
        await platform.async_add_entities([entity for entity in entities if isinstance(entity, CatalogEntity)])

    registry, devices = er.async_get(hass), dr.async_get(hass)
    registered = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(registered) == len(coordinator.catalog_registers) == 567
    assert all(item.disabled and not hass.states.get(item.entity_id) for item in registered)
    assert unit.reads == reads_before
    pump = next(item for item in registered if item.unique_id.endswith("_catalog_001c_bit_2"))
    assert (
        pump.device_id
        == devices.async_get_child_device_by_identifier(("househeating", f"{entry.entry_id}_io"), entry.entry_id).id
    )
    frequency = next(item for item in registered if item.unique_id.endswith("_catalog_0027"))
    assert (
        frequency.device_id
        == devices.async_get_child_device_by_identifier(
            ("househeating", f"{entry.entry_id}_compressor"), entry.entry_id
        ).id
    )
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=True), send_result=Mock())
    browser.ws_snapshot(hass, connection, {"id": 1, "entry_id": entry.entry_id})
    assert connection.send_result.call_args.args[1]["entities"]["28:2"][0]["enabled"] is False

    unit.data.update({0x1C: 4, 0x27: 38})
    unit.reads.clear()
    await coordinator.async_refresh()
    assert (0x27, 1) not in unit.reads
    for item in (pump, frequency):
        registry.async_update_entity(item.entity_id, disabled_by=None)
    from custom_components.househeating.binary_sensor import CatalogBinarySensor
    from custom_components.househeating.sensor import CatalogSensor

    await platforms["binary_sensor"].async_add_entities(
        [CatalogBinarySensor(coordinator, coordinator.catalog_registers["catalog_001c_bit_2"])]
    )
    await platforms["sensor"].async_add_entities(
        [CatalogSensor(coordinator, coordinator.catalog_registers["catalog_0027"])]
    )
    unit.reads.clear()
    await coordinator.async_refresh()
    assert hass.states.get(pump.entity_id).state == "on"
    assert hass.states.get(frequency.entity_id).state == "38"
    assert (0x19, 8) in unit.reads and (0x1C, 1) not in unit.reads
    assert unit.reads.count((0x27, 1)) == 1
    await platforms["sensor"].async_reset()
    unit.reads.clear()
    await coordinator.async_refresh()
    assert (0x27, 1) not in unit.reads and 0x27 not in coordinator.device.snapshot.raw
    assert not unit.writes
    await platforms["binary_sensor"].async_reset()


@pytest.mark.asyncio
async def test_child_devices_move_existing_entities_without_changing_ids(tmp_path, monkeypatch):
    from datetime import timedelta
    from logging import getLogger

    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_platform import EntityPlatform

    from custom_components.househeating._vendor.househeating_modbus import BY_KEY
    from custom_components.househeating.binary_sensor import async_setup_entry as setup_binary_sensors
    from custom_components.househeating.sensor import HouseHeatingSensor

    coordinator, unit = await harness(tmp_path, authorized=False)
    hass, entry = coordinator.hass, coordinator.entry
    hass.config_entries = ConfigEntries(hass, {})
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _: entry)
    entry.runtime_data = coordinator
    dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)

    inlet = HouseHeatingSensor(coordinator, BY_KEY["water_inlet_temperature"])
    flow = HouseHeatingSensor(coordinator, BY_KEY["flow_raw"])
    frequency = HouseHeatingSensor(coordinator, BY_KEY["compressor_frequency"])
    power = HouseHeatingSensor(coordinator, BY_KEY["input_power"])
    devices, registry = dr.async_get(hass), er.async_get(hass)
    parent = devices.async_get_or_create(config_entry_id=entry.entry_id, **inlet.device_info)
    old_flow = registry.async_get_or_create(
        "sensor",
        "househeating",
        flow.unique_id,
        config_entry=entry,
        device_id=parent.id,
        suggested_object_id="my_original_flow",
    )
    platform = EntityPlatform(
        hass=hass,
        logger=getLogger(__name__),
        domain="sensor",
        platform_name="househeating",
        platform=None,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.config_entry = entry
    await platform.async_add_entities([flow, inlet, frequency, power])
    assert flow.entity_id == old_flow.entity_id
    assert registry.async_get(old_flow.entity_id).id == old_flow.id
    assert devices.async_get(registry.async_get(old_flow.entity_id).device_id).parent_device_id == parent.id
    assert inlet.device_entry.id == parent.id
    assert [entity.device_info["translation_key"] for entity in (flow, frequency, power)] == [
        "water_circuit",
        "compressor",
        "energy",
    ]

    heater = HouseHeatingWaterHeater(coordinator)
    unit.data.update({0x130: 0, 0x304: 1, 0x1D: 1 << 10, 0x1C: 1 << 4})
    await coordinator.device.async_update(force_optional=True)
    assert "parent_device_id" not in heater.device_info
    contacts = []
    await setup_binary_sensors(hass, entry, contacts.extend)
    for key in ("room_thermostat_contact_closed", "zone_1_pump_active"):
        entity = next(entity for entity in contacts if entity.key == key)
        assert entity.device_info["translation_key"] == "io"
        assert entity.is_on is True and not entity.entity_registry_enabled_default

    unit.data[0x130] = 1
    await coordinator.device.async_update(force_optional=True)
    child = devices.async_get_or_create_child(config_entry_id=entry.entry_id, **heater.device_info)
    assert child.parent_device_id == parent.id
    assert heater.device_info["translation_key"] == "domestic_hot_water"
    unit.data[0x130] = 0
    await coordinator.device.async_update(force_optional=True)
    assert heater.device_info["translation_key"] == "domestic_hot_water"
    assert not unit.writes
    await platform.async_reset()


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
