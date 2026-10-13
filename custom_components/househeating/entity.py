"""Common entity identity and availability."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import HouseHeatingCoordinator


class HouseHeatingEntity(CoordinatorEntity[HouseHeatingCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HouseHeatingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key

    @property
    def device_info(self) -> DeviceInfo:
        identity = self.coordinator.device.snapshot.identity
        return DeviceInfo(identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
                          name=self.coordinator.entry.data["name"], manufacturer="HouseHeating",
                          model="HH-C3-12", sw_version=identity.firmware_text if identity else None)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.device.unit.connected

    def register_value(self, key: str | None = None):
        return self.coordinator.device.snapshot.value(key or self.key, self.coordinator.device.config)


class HouseHeatingControlEntity(HouseHeatingEntity):
    @property
    def available(self) -> bool:
        return (super().available and self.coordinator.device.control_ready
                and self.register_value() is not None)
