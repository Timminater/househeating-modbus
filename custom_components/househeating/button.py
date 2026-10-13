"""A read-only refresh command; no reset, defrost or forced-operation commands."""
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HouseHeatingRefresh(entry.runtime_data, "refresh")])


class HouseHeatingRefresh(HouseHeatingEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        # Allow a manual reconnection attempt even if the previous poll failed.
        return True

    async def async_press(self):
        await self.coordinator.async_refresh_all()
