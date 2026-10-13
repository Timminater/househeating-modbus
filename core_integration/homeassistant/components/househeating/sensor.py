"""Measurements and read-only diagnostics."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.entity import EntityCategory

from househeating_modbus import REGISTERS, SELECTS
from .entity import HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(HouseHeatingSensor(coordinator, r) for r in REGISTERS)


class HouseHeatingSensor(HouseHeatingEntity, SensorEntity):
    def __init__(self, coordinator, register):
        super().__init__(coordinator, register.key)
        self.register = register
        self._attr_entity_registry_enabled_default = register.default_enabled
        self._attr_entity_category = EntityCategory.DIAGNOSTIC if register.diagnostic else None
        self._attr_native_unit_of_measurement = register.unit
        self._attr_device_class = SensorDeviceClass(register.device_class) if register.device_class else None
        self._attr_suggested_display_precision = 1 if register.kind in ("temperature", "setpoint") else (2 if register.factor < 1 else 0)
        if register.kind not in ("bitfield", "raw", "enum", "counter"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if register.key in SELECTS:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(SELECTS[register.key])
            self._attr_suggested_display_precision = None
        elif register.key == "power":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["off", "on"]
            self._attr_suggested_display_precision = None

    @property
    def native_value(self):
        value = self.register_value()
        if self.key in SELECTS:
            return next((k for k, v in SELECTS[self.key].items() if v == value), None)
        if self.key == "power":
            return {0: "off", 1: "on"}.get(value)
        return value

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self):
        snapshot = self.coordinator.device.snapshot
        return {"register": f"0x{self.register.address:04X}",
                "raw_value": snapshot.raw.get(self.register.address),
                "manual_pdf_page": self.register.page,
                "register_group": self.register.group,
                "optional_sample_time": snapshot.optional_timestamp if self.register.group != "core" else None}
