"""Normal controller on/off command, never a mains disconnect."""
from homeassistant.components.switch import SwitchEntity
from .entity import HouseHeatingControlEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HouseHeatingPower(entry.runtime_data, "power")])


class HouseHeatingPower(HouseHeatingControlEntity, SwitchEntity):
    @property
    def is_on(self):
        value = self.register_value()
        return value == 1 if value in (0, 1) else None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_write("power", True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_write("power", False)
