"""Exact operating modes and protocol-gated native curves."""
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory
from ._vendor.househeating_modbus import SELECTS
from .entity import HouseHeatingControlEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(HouseHeatingSelect(entry.runtime_data, key) for key in SELECTS)


class HouseHeatingSelect(HouseHeatingControlEntity, SelectEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._attr_options = list(SELECTS[key])
        if key.endswith("_curve"):
            self._attr_entity_category = EntityCategory.CONFIG
            self._attr_entity_registry_enabled_default = False

    @property
    def current_option(self):
        raw = self.register_value()
        return next((k for k, v in SELECTS[self.key].items() if raw == v), None)

    @property
    def available(self):
        if self.key.endswith("_curve"):
            device = self.coordinator.device
            identity = device.snapshot.identity
            if not device.config.curves or identity is None or identity.protocol < 130:
                return False
        return super().available and self.current_option is not None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_write(self.key, option)
