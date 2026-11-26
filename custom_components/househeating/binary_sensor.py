"""Documented state bits and the commissioning lock."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from ._vendor.househeating_modbus import BINARY_FLAGS
from ._vendor.househeating_modbus.operation import INPUT_FLAGS, RELAY_FLAGS, io_bit_value
from ._vendor.househeating_modbus.registers import FAULT_LABELS
from .entity import CatalogEntity, HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    if coordinator.price_control is not None:
        async_add_entities(PriceBlockBinary(coordinator, block) for block in ("charge", "pause"))
    async_add_entities(
        CatalogBinarySensor(coordinator, register)
        for register in coordinator.catalog_registers.values()
        if register.is_binary
    )
    async_add_entities(
        [
            *(HouseHeatingBinary(entry.runtime_data, key) for key in BINARY_FLAGS),
            HouseHeatingBinary(entry.runtime_data, "control_enabled"),
        ]
    )
    async_add_entities(
        IOBinary(entry.runtime_data, key, address, bit) for key, (address, bit) in (RELAY_FLAGS | INPUT_FLAGS).items()
    )
    async_add_entities(
        FaultBinary(entry.runtime_data, address, bit, label)
        for address, bits in FAULT_LABELS.items()
        for bit, label in bits.items()
    )


class PriceBlockBinary(HouseHeatingEntity, BinarySensorEntity):
    def __init__(self, coordinator, block):
        super().__init__(coordinator, f"price_{block}_active")
        self.block = block

    @property
    def available(self):
        return self.coordinator.price_control.price_checked_at is not None

    @property
    def is_on(self):
        return self.coordinator.price_control.block_active(self.block)


class CatalogBinarySensor(CatalogEntity, BinarySensorEntity):
    @property
    def is_on(self):
        value = self.raw_value
        return None if value is None else bool(value & (1 << (self.register.row.bit or 0)))


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


class IOBinary(HouseHeatingEntity, BinarySensorEntity):
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key, address, bit):
        super().__init__(coordinator, key)
        self.address, self.bit = address, bit

    @property
    def is_on(self):
        return io_bit_value(
            self.coordinator.device.snapshot,
            self.address,
            self.bit,
            max(90, 2.5 * self.coordinator.update_interval.total_seconds()),
        )

    @property
    def available(self):
        return super().available and self.is_on is not None

    @property
    def extra_state_attributes(self):
        is_input = self.key in INPUT_FLAGS
        return {
            "register": f"0x{self.address:04X}",
            "bit": self.bit,
            "manual_pdf_pages": [175] if is_input else [173, 174],
            "measurement_origin": "reported_input_status" if is_input else "reported_relay_status",
        }


class FaultBinary(HouseHeatingEntity, BinarySensorEntity):
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, address, bit, label):
        super().__init__(coordinator, f"fault_{address:04x}_{label}")
        self.address, self.bit = address, bit

    @property
    def is_on(self):
        value = self.coordinator.device.snapshot.raw.get(self.address)
        return bool(value & (1 << self.bit)) if value is not None else None

    @property
    def available(self):
        return super().available and self.is_on is not None

    @property
    def extra_state_attributes(self):
        return {
            "register": f"0x{self.address:04X}",
            "bit": self.bit,
            "manual_pdf_pages": [169] if self.address < 5 else [170, 171],
            "measurement_origin": "reported_fault_bit",
        }
