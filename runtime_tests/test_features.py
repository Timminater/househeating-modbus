import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from test_monitoring import MemoryStore, manager, options_flow
from test_real_runtime import harness

from custom_components.househeating import monitoring
from custom_components.househeating._vendor.househeating_modbus.operation import CurveConfig
from custom_components.househeating.operation import OperationManager
from custom_components.househeating.sensor import MONITORING_SENSORS, OPERATION_SENSORS, OperationSensor


async def operation(tmp_path, *, authorized=True, automatic=False, statistics=False, **kw):
    coordinator, unit = await harness(tmp_path, authorized=authorized)
    unit.data[0x304] = 1
    await coordinator.async_refresh()
    cfg = CurveConfig(
        enabled=True,
        automatic=automatic,
        confirm_control=automatic,
        confirmation_id="approved-session" if automatic else "",
        inertia_minutes=0,
        **kw,
    )
    object.__setattr__(
        coordinator.entry,
        "options",
        MappingProxyType({"weather_curve": asdict(cfg), "operation_statistics": statistics}),
    )
    mgr = OperationManager(coordinator.hass, coordinator)
    mgr.store = MemoryStore()
    mgr.command_store = MemoryStore()
    coordinator.operation = mgr
    await mgr.async_load()
    return mgr, coordinator, unit


@pytest.mark.asyncio
async def test_curve_advisory_and_locked_automatic_never_write(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path)
    await mgr.async_evaluate()
    assert mgr.values()["curve_advised_target"] == 34
    assert mgr.values()["curve_status"] == "advisory" and not unit.writes
    mgr, coordinator, unit = await operation(tmp_path, authorized=False, automatic=True)
    await mgr.async_evaluate()
    assert mgr.values()["curve_status"] == "control_locked" and not unit.writes


@pytest.mark.asyncio
async def test_curve_uses_fresh_verified_write_without_changing_mode(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    await mgr.async_evaluate()
    assert unit.writes == [(0x301, 340)]
    assert coordinator.device.last_write["result"] == "verified"
    assert unit.data[0x304] == 1 and unit.data[0x305] == 1
    assert mgr.command_store.saved["pending"] is False
    await mgr.async_evaluate()
    assert len(unit.writes) == 1
    assert mgr.values()["curve_status"] == "cooldown"


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["native", "off", "mode", "fault", "identity"])
async def test_curve_preserves_all_control_guards(tmp_path, condition):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    if condition == "native":
        unit.data[0x314] = 1
    if condition == "off":
        unit.data[0x305] = 0
    if condition == "mode":
        unit.data[0x304] = 4
    if condition == "fault":
        unit.data[2] = 1 << 7
    if condition == "identity":
        unit.data[0x360] = 405
    await mgr.async_evaluate()
    assert not unit.writes


@pytest.mark.asyncio
async def test_uncertain_command_is_latched_across_reload_without_retry(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    unit.ack_error = True
    await mgr.async_evaluate()
    assert len(unit.writes) == 1 and mgr.blocked
    assert mgr.command_store.saved["pending"]
    store = mgr.command_store
    unit.ack_error = False
    reloaded = OperationManager(coordinator.hass, coordinator)
    reloaded.command_store = store
    coordinator.operation = reloaded
    await reloaded.async_load()
    assert reloaded.blocked
    await reloaded.async_evaluate()
    assert len(unit.writes) == 1


@pytest.mark.asyncio
async def test_curve_manual_override_and_storage_failure_stop_writes(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    await mgr.async_evaluate()
    await coordinator.async_write("heating_setpoint", 45)
    await mgr.async_evaluate()
    assert mgr.blocked and mgr.values()["curve_status"] == "manual_override"
    assert unit.data[0x301] == 450 and len(unit.writes) == 2
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    mgr.command_store.fail = True
    await mgr.async_evaluate()
    assert mgr.blocked and not unit.writes


@pytest.mark.asyncio
async def test_statistics_storage_failure_reported_retried_and_cleanup(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, statistics=True)
    mgr.save_interval = 0
    unit.data[0x1A] = 0
    await coordinator.async_refresh()
    mgr.store.fail = True
    unit.data[0x1A] = 1
    await coordinator.async_refresh()
    assert mgr.storage_error and mgr.ledger.starts == 1
    mgr.store.fail = False
    await coordinator.async_refresh()
    assert not mgr.storage_error and mgr.store.saved == mgr.ledger.export()
    mgr.start()
    await coordinator.hass.async_block_till_done()
    assert mgr.unsub
    await mgr.async_close()
    assert mgr.closed


@pytest.mark.asyncio
async def test_external_heat_real_reported_power_and_stale_rejection(tmp_path, monkeypatch):
    mgr, coordinator, _ = await manager(
        tmp_path, monkeypatch, thermal_source="external", external_heat_power="sensor.heat"
    )
    mgr.start()
    coordinator.hass.states.async_set("sensor.heat", "6000", {"device_class": "power", "unit_of_measurement": "W"})
    await coordinator.hass.async_block_till_done()
    await coordinator.async_refresh()
    assert mgr.values()["thermal_power_estimated"] == 6
    clock = datetime.now(UTC).timestamp() + 200
    monkeypatch.setattr(monitoring, "time", lambda: clock)
    await mgr.async_process()
    assert mgr.values()["thermal_power_estimated"] is None
    await mgr.async_close()


@pytest.mark.asyncio
async def test_curve_external_sources_require_fresh_units_and_missing_source_stops(tmp_path):
    mgr, coordinator, unit = await operation(
        tmp_path, automatic=True, pv_entity="sensor.pv", battery_entity="sensor.soc"
    )
    await mgr.async_evaluate()
    assert mgr.values()["curve_status"] == "source_unavailable" and not unit.writes
    coordinator.hass.states.async_set("sensor.pv", "3000", {"device_class": "power", "unit_of_measurement": "W"})
    coordinator.hass.states.async_set("sensor.soc", "90", {"device_class": "battery", "unit_of_measurement": "%"})
    await mgr.async_evaluate()
    assert len(unit.writes) == 1
    coordinator.hass.states.async_set("sensor.pv", "unavailable", {"device_class": "power", "unit_of_measurement": "W"})
    await mgr.async_evaluate()
    assert len(unit.writes) == 1 and mgr.values()["curve_status"] == "source_unavailable"


@pytest.mark.asyncio
async def test_options_keep_authorization_and_require_new_confirmation(tmp_path, monkeypatch):
    flow, entry = await options_flow(tmp_path, monkeypatch)
    form = await flow.async_step_weather_curve()
    data = form["data_schema"]({"enabled": True, "automatic": True, "confirm_control": False})
    assert (await flow.async_step_weather_curve(data))["errors"]["base"] == "invalid_curve"
    data["confirm_control"] = True
    result = await flow.async_step_weather_curve(data)
    assert result["data"]["authorized_identity"] == entry.options["authorized_identity"]
    assert result["data"]["allow_control"] is True
    assert result["data"]["unknown_future_option"] == "preserve"
    assert result["data"]["weather_curve"]["confirmation_id"]
    again = await flow.async_step_weather_curve(data)
    assert result["data"]["weather_curve"]["confirmation_id"] != again["data"]["weather_curve"]["confirmation_id"]
    data["water_max"] = 70
    assert (await flow.async_step_weather_curve(data))["errors"]["base"] == "invalid_curve"
    stats = await flow.async_step_operation({"operation_statistics": True})
    assert stats["data"]["authorized_identity"] == entry.options["authorized_identity"]


@pytest.mark.asyncio
async def test_dashboard_follows_registry_renames_and_disabled_entities(tmp_path, monkeypatch):
    from homeassistant.helpers import entity_registry as er

    from custom_components.househeating.dashboard import async_register_dashboard_service, dashboard_config

    flow, entry = await options_flow(tmp_path, monkeypatch)
    registry = er.async_get(flow.hass)
    item = registry.async_get_or_create(
        "sensor",
        "househeating",
        entry.entry_id + "_water_inlet_temperature",
        config_entry=entry,
        suggested_object_id="inlet",
    )
    registry.async_update_entity(item.entity_id, new_entity_id="sensor.renamed_inlet")
    config = dashboard_config(flow.hass, entry)
    import json

    assert "sensor.renamed_inlet" in json.dumps(config)
    registry.async_update_entity("sensor.renamed_inlet", disabled_by=er.RegistryEntryDisabler.USER)
    assert "sensor.renamed_inlet" not in json.dumps(dashboard_config(flow.hass, entry))
    async_register_dashboard_service(flow.hass)
    result = await flow.hass.services.async_call(
        "househeating", "generate_dashboard", {"entry_id": entry.entry_id}, blocking=True, return_response=True
    )
    assert result["dashboard"]["views"][0]["type"] == "sections"


@pytest.mark.asyncio
async def test_new_sensors_have_unique_ids_and_correct_real_metadata(tmp_path):
    mgr, coordinator, _ = await operation(tmp_path, statistics=True)
    sensors = [OperationSensor(coordinator, key, *description) for key, description in OPERATION_SENSORS.items()]
    assert len({s.unique_id for s in sensors}) == len(sensors)
    assert next(s for s in sensors if s.key == "compressor_runtime_observed").native_unit_of_measurement == "h"
    assert next(s for s in sensors if s.key == "curve_offset").device_class.value == "temperature_delta"
    assert MONITORING_SENSORS["heating_energy_paired_7d"][2] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,mode,expected", [("floor_setpoint", 3, 340), ("dhw_setpoint", 2, 340), ("cooling_setpoint", 0, 190)]
)
async def test_optional_curve_targets_preserve_operating_mode(tmp_path, target, mode, expected):
    limits = {"water_min": 7, "water_max": 25} if target == "cooling_setpoint" else {}
    mgr, coordinator, unit = await operation(tmp_path, automatic=True, target=target, **limits)
    unit.data[0x304] = mode
    await coordinator.async_refresh()  # evaluation runs after each poll
    await mgr.async_evaluate()
    address = {"floor_setpoint": 0x303, "dhw_setpoint": 0x302, "cooling_setpoint": 0x300}[target]
    assert unit.writes == [(address, expected)]
    assert unit.data[0x304] == mode and unit.data[0x305] == 1


@pytest.mark.asyncio
async def test_unload_prevents_a_pending_curve_write(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    entered = asyncio.Event()
    release = asyncio.Event()
    original = mgr.command_store.async_save

    async def delayed(value):
        entered.set()
        await release.wait()
        await original(value)

    mgr.command_store.async_save = delayed
    mgr.task = asyncio.create_task(mgr.async_evaluate())
    await asyncio.wait_for(entered.wait(), 2)
    closing = asyncio.create_task(mgr.async_close())
    await asyncio.sleep(0)
    release.set()
    await asyncio.wait_for(closing, 2)
    assert mgr.closed and not unit.writes


@pytest.mark.asyncio
async def test_every_existing_entity_identity_is_preserved(tmp_path):
    import importlib
    import json
    from pathlib import Path

    baseline = json.loads(Path(__file__).with_name("entity_keys_v030.json").read_text())
    coordinator, _ = await harness(tmp_path)
    coordinator.entry.runtime_data = coordinator
    monitoring_keys = baseline.pop("monitoring")
    from custom_components.househeating._vendor.househeating_modbus.telemetry import MonitoringConfig
    from custom_components.househeating.sensor import MonitoringSensor

    coordinator.monitoring = monitoring.MonitoringManager(coordinator.hass, coordinator, MonitoringConfig(enabled=True))
    monitoring_entities = [MonitoringSensor(coordinator, key, *desc) for key, desc in MONITORING_SENSORS.items()]
    assert {coordinator.entry.entry_id + "_" + key for key in monitoring_keys} <= {
        e.unique_id for e in monitoring_entities
    }
    for platform, keys in baseline.items():
        module = importlib.import_module("custom_components.househeating." + platform)
        entities = []
        await module.async_setup_entry(
            coordinator.hass, coordinator.entry, lambda values, entities=entities: entities.extend(values)
        )
        actual = {e.unique_id for e in entities}
        assert len(actual) == len(entities)
        assert {coordinator.entry.entry_id + "_" + key for key in keys} <= actual


@pytest.mark.asyncio
async def test_curve_does_not_accept_own_advice_as_outdoor_source(tmp_path, monkeypatch):
    from homeassistant.helpers import entity_registry as er

    flow, entry = await options_flow(tmp_path, monkeypatch)
    item = er.async_get(flow.hass).async_get_or_create(
        "sensor", "househeating", entry.entry_id + "_curve_advised_target", config_entry=entry
    )
    flow.hass.states.async_set(item.entity_id, "35", {"device_class": "temperature", "unit_of_measurement": "°C"})
    data = asdict(CurveConfig(enabled=True, outdoor_entity=item.entity_id))
    data.pop("confirmation_id")
    assert (await flow.async_step_weather_curve(data))["errors"]["base"] == "invalid_curve"


@pytest.mark.asyncio
async def test_dashboard_generation_requires_admin_context(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized

    from custom_components.househeating.dashboard import async_register_dashboard_service

    flow, entry = await options_flow(tmp_path, monkeypatch)
    flow.hass.auth = SimpleNamespace(async_get_user=AsyncMock(return_value=SimpleNamespace(is_admin=False)))
    async_register_dashboard_service(flow.hass)
    with pytest.raises(Unauthorized):
        await flow.hass.services.async_call(
            "househeating",
            "generate_dashboard",
            {"entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
            context=Context(user_id="unprivileged-user"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("statistics", [False, True])
@pytest.mark.parametrize("forward_failure", [False, True])
async def test_real_optional_operation_setup_unload(tmp_path, monkeypatch, statistics, forward_failure):
    from fake_unit import FakeUnit
    from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
    from homeassistant.core import HomeAssistant

    import custom_components.househeating as integration

    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(side_effect=RuntimeError("simulated platform setup failure") if forward_failure else None),
    )
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    unit = FakeUnit()
    monkeypatch.setattr(integration, "async_get_unit", lambda *args: unit)
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="househeating",
        title="Lifecycle",
        data={"name": "Lifecycle", "transport": "tcp", "host": "192.0.2.1", "port": 502, "unit_id": 1},
        options={"operation_statistics": statistics, "weather_curve": {"enabled": True}},
        source="user",
        unique_id="operation-lifecycle",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    if forward_failure:
        with pytest.raises(RuntimeError):
            await integration.async_setup_entry(hass, entry)
        assert entry.runtime_data.operation.closed and not entry.runtime_data.operation.running
        assert not unit.writes
        await entry.runtime_data.async_shutdown()
        return
    assert await integration.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    mgr = entry.runtime_data.operation
    assert mgr.running and mgr.values()["curve_advised_target"] is not None
    if statistics:
        assert await mgr.store.async_load() is not None
    assert await integration.async_unload_entry(hass, entry)
    assert mgr.closed and not unit.writes
    await entry.runtime_data.async_shutdown()


@pytest.mark.asyncio
async def test_statistics_saved_periodically_not_every_poll(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, statistics=True)
    for _ in range(5):
        await coordinator.async_refresh()
    assert mgr.store.saves == 1
    await mgr.async_close()
    assert mgr.store.saves == 2 and mgr.store.saved == mgr.ledger.export()


@pytest.mark.asyncio
async def test_curve_without_needed_change_causes_no_bus_traffic_or_storage(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    await mgr.async_evaluate()
    assert unit.writes == [(0x301, 340)]
    reads, saves = len(unit.reads), mgr.command_store.saves
    for _ in range(5):
        await mgr.async_evaluate()
    assert len(unit.reads) == reads and mgr.command_store.saves == saves
    assert mgr.values()["curve_status"] == "cooldown"


@pytest.mark.asyncio
async def test_curve_transient_failure_before_sending_does_not_latch(tmp_path, monkeypatch):
    from custom_components.househeating import operation as operation_module

    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    unit.fail_addresses.add(0x300)
    await mgr.async_evaluate()
    assert not unit.writes and not mgr.blocked
    assert mgr.values()["curve_status"] == "control_unavailable"
    assert not mgr.command_store.saved["pending"]
    unit.fail_addresses.clear()
    await coordinator.async_refresh()
    clock = operation_module.monotonic() + mgr.max_age + 1
    monkeypatch.setattr(operation_module, "monotonic", lambda: clock)
    await mgr.async_evaluate()
    assert unit.writes == [(0x301, 340)] and not mgr.blocked


@pytest.mark.asyncio
async def test_curve_sensor_fault_rejects_without_latch(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    unit.data[2] = 1 << 7
    await mgr.async_evaluate()
    assert not unit.writes and not mgr.blocked
    assert mgr.values()["curve_status"] == "control_unavailable"


@pytest.mark.asyncio
async def test_curve_reports_unreadable_native_curve(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, automatic=True)
    coordinator.device.config = replace(coordinator.device.config, curves=False)
    await mgr.async_evaluate()
    assert mgr.values()["curve_status"] == "native_curve_unknown" and not unit.writes


@pytest.mark.asyncio
async def test_curve_outdoor_modbus_value_accepted_with_long_poll_interval(tmp_path, monkeypatch):
    from custom_components.househeating import operation as operation_module

    mgr, coordinator, unit = await operation(tmp_path)
    mgr.max_age = 750  # scan interval 300 s
    later = operation_module.time() + 200
    monkeypatch.setattr(operation_module, "time", lambda: later)
    monkeypatch.setattr(
        operation_module, "monotonic", lambda: coordinator.device.snapshot.samples[0x4A].monotonic_end + 200
    )
    await mgr.async_evaluate()
    assert mgr.values()["curve_status"] == "advisory"


@pytest.mark.asyncio
async def test_automatic_curve_requires_readable_native_curves(tmp_path, monkeypatch):
    flow, entry = await options_flow(tmp_path, monkeypatch)
    form = await flow.async_step_weather_curve()
    data = form["data_schema"]({"enabled": True, "automatic": True, "confirm_control": True})
    object.__setattr__(entry, "options", MappingProxyType(dict(entry.options) | {"curves": False}))
    result = await flow.async_step_weather_curve(data)
    assert result["errors"]["base"] == "automatic_needs_native_curve"
    object.__setattr__(
        entry,
        "options",
        MappingProxyType(dict(entry.options) | {"curves": True, "authorized_identity": [404, 0, 1, 129]}),
    )
    result = await flow.async_step_weather_curve(data)
    assert result["errors"]["base"] == "automatic_needs_native_curve"


@pytest.mark.asyncio
async def test_failed_unload_resumes_weather_curve(tmp_path, monkeypatch):
    from fake_unit import FakeUnit
    from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
    from homeassistant.core import HomeAssistant

    import custom_components.househeating as integration

    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False))
    unit = FakeUnit()
    monkeypatch.setattr(integration, "async_get_unit", lambda *args: unit)
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="househeating",
        title="Unload",
        data={"name": "Unload", "transport": "tcp", "host": "192.0.2.1", "port": 502, "unit_id": 1},
        options={"weather_curve": {"enabled": True}},
        source="user",
        unique_id="unload-test",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    assert await integration.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert not await integration.async_unload_entry(hass, entry)
    mgr = entry.runtime_data.operation
    assert mgr.running and not mgr.closed and mgr.unsub
    await mgr.async_close()
    await entry.runtime_data.async_shutdown()


@pytest.mark.asyncio
async def test_corrupt_statistics_storage_disables_only_statistics(tmp_path):
    mgr, coordinator, unit = await operation(tmp_path, statistics=True)
    store = mgr.store
    store.saved = {"version": 1, "starts": -1, "seconds": 0, "completed_cycles": 0, "completed_seconds": 0}
    reloaded = OperationManager(coordinator.hass, coordinator)
    reloaded.store = store
    reloaded.command_store = MemoryStore()
    await reloaded.async_load()
    assert reloaded.storage_invalid and not reloaded.statistics
    await reloaded.async_close()
    assert store.saved["starts"] == -1  # never overwritten
