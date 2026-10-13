"""Coordinated polling and verified user commands."""
from __future__ import annotations

from datetime import timedelta
import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from househeating_modbus import HeatPump, HeatPumpError, Snapshot
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
        self._command_lock = asyncio.Lock()

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
        await self.async_control(lambda snapshot: [(key, value)])

    async def async_control(self, plan) -> None:
        """Serialize a whole UI command and build it against a fresh snapshot.

        Each write is verified before proceeding; a failed step aborts the plan.
        No rollback or automatic repeat is safe after an uncertain acknowledgement.
        """
        async with self._command_lock:
            await self.async_refresh()
            await self._async_control_locked(plan)

    async def _async_control_locked(self, plan) -> None:
        if not self.last_update_success:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_unavailable")
        if not self.device.control_ready:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="control_locked")
        try:
            self.device.validate_for_control()
            for key, value in plan(self.device.snapshot):
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
