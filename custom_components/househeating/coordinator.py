"""Coordinated polling and verified user commands."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ._vendor.househeating_modbus import HeatPump, HeatPumpError, Snapshot
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HouseHeatingCoordinator(DataUpdateCoordinator[Snapshot]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device: HeatPump,
                 interval: int) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=interval))
        self.entry = entry
        self.device = device
        self.force_optional = False

    async def _async_update_data(self) -> Snapshot:
        try:
            snapshot = await self.device.async_update(force_optional=self.force_optional)
        except HeatPumpError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self.force_optional = False
        if not snapshot.layout_valid:
            raise UpdateFailed("The returned mode/profile/power registers do not match the documented layout")
        return snapshot

    async def async_write(self, key: str, value: Any) -> None:
        if not self.last_update_success:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_unavailable")
        if not self.device.control_ready:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="control_locked")
        try:
            await self.device.async_write(key, value)
        except HeatPumpError as err:
            # Never present an unconfirmed write as success. Refresh without resending.
            await self.async_refresh()
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="command_failed",
                                     translation_placeholders={"error": str(err)}) from err
        await self.async_refresh()

    async def async_refresh_all(self) -> None:
        self.force_optional = True
        await self.async_request_refresh()


HouseHeatingConfigEntry = ConfigEntry[HouseHeatingCoordinator]
