"""HouseHeating heat pumps using Home Assistant's shared Modbus connection."""

from __future__ import annotations

import logging

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed

from ._vendor.househeating_modbus import HeatPump
from .connection import connection_params, device_config
from .const import DEFAULT_OPTIONS, DOMAIN
from .coordinator import HouseHeatingConfigEntry, HouseHeatingCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.WATER_HEATER,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    from .dashboard import async_register_dashboard_service

    async_register_dashboard_service(hass)
    return True


@callback
def _async_storage_issue(hass: HomeAssistant, entry: HouseHeatingConfigEntry, kind: str) -> None:
    """Report unreadable stored totals instead of failing the whole integration.

    The stored file is left untouched so it can be inspected or restored.
    """
    from homeassistant.helpers import issue_registry as ir

    ir.async_create_issue(
        hass,
        DOMAIN,
        f"storage_invalid_{kind}_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=f"storage_invalid_{kind}",
        translation_placeholders={"title": entry.title, "file": f".storage/househeating.{kind}.{entry.entry_id}"},
    )


async def async_setup_entry(hass: HomeAssistant, entry: HouseHeatingConfigEntry) -> bool:
    options = DEFAULT_OPTIONS | dict(entry.options)
    unit = async_get_unit(hass, entry, connection_params(dict(entry.data)), entry.data["unit_id"])
    fingerprint = tuple(options["authorized_identity"])
    authorization = fingerprint if options["allow_control"] and len(fingerprint) == 4 else None
    device = HeatPump(unit, device_config(options), authorized_identity=authorization)
    coordinator = HouseHeatingCoordinator(hass, entry, device, int(options["scan_interval"]))
    entry.runtime_data = coordinator
    from ._vendor.househeating_modbus.telemetry import MonitoringConfig

    monitoring_config = MonitoringConfig.from_options(options)
    if monitoring_config.enabled:
        from .monitoring import MonitoringManager

        monitoring = MonitoringManager(hass, coordinator, monitoring_config)
        try:
            await monitoring.async_load()
        except (ValueError, TypeError, KeyError):
            _LOGGER.exception("Stored HouseHeating monitoring totals are invalid; monitoring disabled")
            _async_storage_issue(hass, entry, "monitoring")
        else:
            coordinator.monitoring = monitoring
    if options.get("operation_statistics", False) or options.get("weather_curve", {}).get("enabled", False):
        from .operation import OperationManager

        coordinator.operation = OperationManager(hass, coordinator)
        await coordinator.operation.async_load()
        if coordinator.operation.storage_invalid:
            _async_storage_issue(hass, entry, "operation")
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await _async_close_managers(coordinator)
        raise

    @callback
    def connection_lost() -> None:
        device.invalidate_optional()
        coordinator.async_set_update_error(UpdateFailed("Modbus connection lost"))
        if coordinator.monitoring is not None:
            coordinator.monitoring.connection_lost()
        if coordinator.operation is not None:
            hass.async_create_task(coordinator.operation.async_snapshot(None), "HouseHeating operation disconnect")

    entry.async_on_unload(unit.on_connection_lost(connection_lost))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await _async_close_managers(coordinator)
        raise
    entry.async_on_unload(coordinator.async_add_listener(_firmware_listener(hass, entry, coordinator)))
    if coordinator.monitoring is not None:
        coordinator.monitoring.start()
    if coordinator.operation is not None:
        coordinator.operation.start()
    return True


def _firmware_listener(hass: HomeAssistant, entry: HouseHeatingConfigEntry, coordinator: HouseHeatingCoordinator):
    """Keep the device registry's firmware version in step with the unit."""
    identity = coordinator.device.snapshot.identity
    known = {"version": identity.firmware_text if identity else None}

    @callback
    def update() -> None:
        identity = coordinator.device.snapshot.identity
        if identity is None or identity.firmware_text == known["version"]:
            return
        known["version"] = identity.firmware_text
        from homeassistant.helpers import device_registry as dr

        registry = dr.async_get(hass)
        device_entry = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
        if device_entry is not None and device_entry.sw_version != identity.firmware_text:
            registry.async_update_device(device_entry.id, sw_version=identity.firmware_text)

    return update


async def _async_close_managers(coordinator: HouseHeatingCoordinator) -> None:
    if coordinator.monitoring is not None:
        await coordinator.monitoring.async_close()
    if coordinator.operation is not None:
        await coordinator.operation.async_close()


async def async_unload_entry(hass: HomeAssistant, entry: HouseHeatingConfigEntry) -> bool:
    # async_get_unit registered the shared connection's release callback itself.
    coordinator = entry.runtime_data
    # Stop automatic curve commands before the entities disappear.
    if coordinator.operation is not None:
        await coordinator.operation.async_close()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        # The entry stays loaded: resume statistics and the weather curve.
        if coordinator.operation is not None:
            coordinator.operation.reopen()
        return False
    if coordinator.monitoring is not None:
        await coordinator.monitoring.async_close()
    return True
