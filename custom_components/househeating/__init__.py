"""HouseHeating heat pumps using Home Assistant's shared Modbus connection."""
from __future__ import annotations

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed

from ._vendor.househeating_modbus import HeatPump
from .connection import connection_params, device_config
from .const import DEFAULT_OPTIONS, DOMAIN
from .coordinator import HouseHeatingConfigEntry, HouseHeatingCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER,
             Platform.SELECT, Platform.SWITCH, Platform.BUTTON, Platform.CLIMATE, Platform.WATER_HEATER]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: HouseHeatingConfigEntry) -> bool:
    options = DEFAULT_OPTIONS | dict(entry.options)
    unit = async_get_unit(hass, entry, connection_params(dict(entry.data)), entry.data["unit_id"])
    fingerprint = tuple(options["authorized_identity"])
    authorization = fingerprint if options["allow_control"] and len(fingerprint) == 4 else None
    device = HeatPump(unit, device_config(options), authorized_identity=authorization)
    coordinator = HouseHeatingCoordinator(hass, entry, device, int(options["scan_interval"]))
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()

    @callback
    def connection_lost() -> None:
        device.invalidate_optional()
        coordinator.async_set_update_error(UpdateFailed("Modbus connection lost"))

    entry.async_on_unload(unit.on_connection_lost(connection_lost))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HouseHeatingConfigEntry) -> bool:
    # async_get_unit registered the shared connection's release callback itself.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
