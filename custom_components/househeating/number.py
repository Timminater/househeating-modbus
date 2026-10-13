"""Documented user temperature setpoints; no service parameters."""
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from ._vendor.househeating_modbus import SETPOINT_KEYS
from .entity import HouseHeatingControlEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(HouseHeatingNumber(entry.runtime_data, key) for key in SETPOINT_KEYS)


class HouseHeatingNumber(HouseHeatingControlEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._attr_native_min_value, self._attr_native_max_value = coordinator.device.config.limits(key)

    @property
    def native_value(self):
        return self.register_value()

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write(self.key, value)
