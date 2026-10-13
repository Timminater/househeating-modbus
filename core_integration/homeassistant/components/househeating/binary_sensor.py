"""Documented state bits and the commissioning lock."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from househeating_modbus import BINARY_FLAGS
from .entity import HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([*(HouseHeatingBinary(entry.runtime_data, key) for key in BINARY_FLAGS),
                        HouseHeatingBinary(entry.runtime_data, "control_enabled")])


class HouseHeatingBinary(HouseHeatingEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._attr_entity_registry_enabled_default = key in ("running", "alarm", "defrost", "control_enabled")
        if key in ("alarm", "fault_shutdown"):
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        if key == "control_enabled":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self):
        if self.key == "control_enabled":
            return self.coordinator.device.control_ready
        address, bit = BINARY_FLAGS[self.key]
        value = self.coordinator.device.snapshot.raw.get(address)
        return bool(value & (1 << bit)) if value is not None else None

    @property
    def extra_state_attributes(self):
        if self.key == "alarm":
            return {"active_fault_or_diagnostic_bits": self.coordinator.device.snapshot.faults}
        return None
