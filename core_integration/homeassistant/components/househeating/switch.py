"""Normal controller on/off command (never a mains disconnect) and floor-heating choice."""

from homeassistant.components.switch import SwitchEntity

from househeating_modbus.controls import floor_plan
from .entity import HouseHeatingControlEntity, HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HouseHeatingPower(entry.runtime_data, "power"), HouseHeatingFloorHeating(entry.runtime_data)])


class HouseHeatingPower(HouseHeatingControlEntity, SwitchEntity):
    @property
    def is_on(self):
        value = self.register_value()
        return value == 1 if value in (0, 1) else None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_write("power", True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_write("power", False)


class HouseHeatingFloorHeating(HouseHeatingEntity, SwitchEntity):
    """Floor heating instead of normal heating; keeps power, hot water and profile.

    Only selectable while the space mode is heating. It never starts a stopped
    unit and never switches from cooling or hot-water-only to heating.
    """

    def __init__(self, coordinator):
        super().__init__(coordinator, "floor_heating")

    @property
    def available(self):
        return (
            super().available
            and self.coordinator.device.control_ready
            and self.coordinator.device.snapshot.layout_valid
        )

    @property
    def is_on(self):
        mode = self.coordinator.device.snapshot.raw.get(0x304)
        return None if mode is None else mode in (3, 7)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_control(lambda snapshot: floor_plan(snapshot.raw, True))

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_control(lambda snapshot: floor_plan(snapshot.raw, False))
