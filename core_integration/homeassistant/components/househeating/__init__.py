"""HouseHeating heat pumps using Home Assistant's shared Modbus connection."""
from __future__ import annotations

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed

from househeating_modbus import HeatPump
from .connection import connection_params, device_config
from .const import DEFAULT_OPTIONS, DOMAIN
from .coordinator import HouseHeatingConfigEntry, HouseHeatingCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER,
             Platform.SELECT, Platform.SWITCH, Platform.BUTTON, Platform.CLIMATE, Platform.WATER_HEATER]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    from .dashboard import async_register_dashboard_service
    async_register_dashboard_service(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HouseHeatingConfigEntry) -> bool:
    options = DEFAULT_OPTIONS | dict(entry.options)
    unit = async_get_unit(hass, entry, connection_params(dict(entry.data)), entry.data["unit_id"])
    fingerprint = tuple(options["authorized_identity"])
    authorization = fingerprint if options["allow_control"] and len(fingerprint) == 4 else None
    device = HeatPump(unit, device_config(options), authorized_identity=authorization)
    coordinator = HouseHeatingCoordinator(hass, entry, device, int(options["scan_interval"]))
    entry.runtime_data = coordinator
    from househeating_modbus.telemetry import MonitoringConfig
    monitoring_config = MonitoringConfig.from_options(options)
    if monitoring_config.enabled:
        from .monitoring import MonitoringManager
        coordinator.monitoring = MonitoringManager(hass, coordinator, monitoring_config)
        await coordinator.monitoring.async_load()
    if options.get("operation_statistics",False) or options.get("weather_curve",{}).get("enabled",False):
        from .operation import OperationManager
        coordinator.operation=OperationManager(hass,coordinator)
        await coordinator.operation.async_load()
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        if coordinator.monitoring is not None:
            await coordinator.monitoring.async_close()
        if coordinator.operation is not None:
            await coordinator.operation.async_close()
        raise
    @callback
    def connection_lost() -> None:
        device.invalidate_optional()
        coordinator.async_set_update_error(UpdateFailed("Modbus connection lost"))
        if coordinator.monitoring is not None:
            coordinator.monitoring.connection_lost()
        if coordinator.operation is not None:
            hass.async_create_task(coordinator.operation.async_snapshot(None),"HouseHeating operation disconnect")

    entry.async_on_unload(unit.on_connection_lost(connection_lost))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        if coordinator.monitoring is not None:
            await coordinator.monitoring.async_close()
        if coordinator.operation is not None:
            await coordinator.operation.async_close()
        raise
    if coordinator.monitoring is not None:
        coordinator.monitoring.start()
    if coordinator.operation is not None:
        coordinator.operation.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HouseHeatingConfigEntry) -> bool:
    # async_get_unit registered the shared connection's release callback itself.
    if entry.runtime_data.operation is not None:
        await entry.runtime_data.operation.async_close()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data.monitoring is not None:
        await entry.runtime_data.monitoring.async_close()
    return unloaded
