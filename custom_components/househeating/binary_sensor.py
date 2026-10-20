"""Documented state bits and the commissioning lock."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from ._vendor.househeating_modbus import BINARY_FLAGS
from ._vendor.househeating_modbus.operation import RELAY_FLAGS
from ._vendor.househeating_modbus.registers import FAULT_LABELS
from .entity import HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([*(HouseHeatingBinary(entry.runtime_data, key) for key in BINARY_FLAGS),
                        HouseHeatingBinary(entry.runtime_data, "control_enabled")])
    async_add_entities(RelayBinary(entry.runtime_data,key) for key in RELAY_FLAGS)
    async_add_entities(FaultBinary(entry.runtime_data,address,bit,label)
                       for address,bits in FAULT_LABELS.items() for bit,label in bits.items())


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


class RelayBinary(HouseHeatingEntity,BinarySensorEntity):
    _attr_entity_registry_enabled_default=False
    _attr_entity_category=EntityCategory.DIAGNOSTIC

    @property
    def is_on(self):
        from ._vendor.househeating_modbus.operation import relay_value
        return relay_value(self.coordinator.device.snapshot,self.key,
                           max(90,2.5*self.coordinator.update_interval.total_seconds()))

    @property
    def available(self):
        return super().available and self.is_on is not None

    @property
    def extra_state_attributes(self):
        address,bit=RELAY_FLAGS[self.key]
        return {"register":f"0x{address:04X}","bit":bit,"manual_pdf_pages":[173,174],
                "measurement_origin":"reported_relay_status"}


class FaultBinary(HouseHeatingEntity,BinarySensorEntity):
    _attr_entity_registry_enabled_default=False
    _attr_entity_category=EntityCategory.DIAGNOSTIC
    _attr_device_class=BinarySensorDeviceClass.PROBLEM

    def __init__(self,coordinator,address,bit,label):
        super().__init__(coordinator,f"fault_{address:04x}_{label}")
        self.address,self.bit=address,bit

    @property
    def is_on(self):
        value=self.coordinator.device.snapshot.raw.get(self.address)
        return bool(value&(1<<self.bit)) if value is not None else None

    @property
    def available(self):
        return super().available and self.is_on is not None

    @property
    def extra_state_attributes(self):
        return {"register":f"0x{self.address:04X}","bit":self.bit,
                "manual_pdf_pages": [169] if self.address < 5 else [170, 171],
                "measurement_origin":"reported_fault_bit"}
