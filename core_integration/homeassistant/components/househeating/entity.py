"""Common entity identity and availability."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from househeating_modbus.controls import DHW_MODES
from househeating_modbus.operation import INPUT_FLAGS, RELAY_FLAGS
from .const import DOMAIN
from .coordinator import HouseHeatingCoordinator

SUBDEVICE_KEYS = {
    "water_circuit": {
        "flow_raw",
        "water_flow_calibrated",
        "water_delta_temperature",
        "pump_pwm",
        "plate_temperature",
        "buffer_temperature",
        "total_outlet_temperature",
        "zone_1_temperature",
        "zone_2_temperature",
        "mixing_valve_zone_1_raw",
        "mixing_valve_zone_2_raw",
    },
    "compressor": {
        "compressor_active",
        "compressor_frequency",
        "compressor_current",
        "defrost",
        "fan_raw",
        "eev_steps",
        "evi_steps",
        "ipm_temperature",
        "outdoor_coil_temperature",
        "indoor_coil_temperature",
        "high_pressure_saturation_temperature",
        "low_pressure_saturation_temperature",
        "suction_temperature",
        "discharge_temperature",
        "economizer_inlet_temperature",
        "economizer_outlet_temperature",
    },
    "energy": {
        "ac_voltage",
        "ac_current",
        "unit_voltage",
        "unit_current",
        "input_power",
        "reported_energy",
        "phase_b_voltage",
        "phase_b_current",
        "phase_c_voltage",
        "phase_c_current",
    },
    "domestic_hot_water": {
        "dhw_water_heater",
        "dhw_temperature",
        "dhw_return_temperature",
        "dhw_setpoint",
        "dhw_hysteresis",
        "dhw_curve",
        "dhw_sensor_enabled",
        "sterilization",
    },
    "io": (RELAY_FLAGS.keys() - {"compressor_active"}) | INPUT_FLAGS.keys() | {"smart_grid_raw"},
}
SUBDEVICE_BY_KEY = {key: group for group, keys in SUBDEVICE_KEYS.items() for key in keys}


class HouseHeatingEntity(CoordinatorEntity[HouseHeatingCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HouseHeatingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._subdevice = SUBDEVICE_BY_KEY.get(key)
        if key.startswith("io_word_"):
            self._subdevice = "io"
        elif key.startswith(("compressor_starts_", "compressor_runtime_")) or key == "compressor_cycle_average":
            self._subdevice = "compressor"

    @property
    def device_info(self) -> dr.DeviceInfo | dr.ChildDeviceInfo:
        entry = self.coordinator.entry
        snapshot = self.coordinator.device.snapshot
        identity = snapshot.identity
        parent_identifier = (DOMAIN, entry.entry_id)
        parent_info = {
            "identifiers": {parent_identifier},
            "name": entry.data["name"],
            "manufacturer": "HouseHeating",
            "model": "HH-C3-12",
            "sw_version": identity.firmware_text if identity else None,
        }
        if self._subdevice is None:
            return dr.DeviceInfo(**parent_info)

        registry = dr.async_get(self.coordinator.hass)
        identifier = (DOMAIN, f"{entry.entry_id}_{self._subdevice}")
        if (
            self._subdevice == "domestic_hot_water"
            and snapshot.raw.get(0x130) != 1
            and snapshot.raw.get(0x304) not in DHW_MODES
            and registry.async_get_child_device_by_identifier(identifier, entry.entry_id) is None
        ):
            return dr.DeviceInfo(**parent_info)

        parent = registry.async_get_device_by_identifier(parent_identifier, entry.entry_id)
        if parent is None:
            # Platforms may add their first entity in any order.
            parent = registry.async_get_or_create(config_entry_id=entry.entry_id, **parent_info)
        return dr.ChildDeviceInfo(
            identifiers={identifier},
            parent_device_id=parent.id,
            translation_key=self._subdevice,
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.device.unit.connected

    def register_value(self, key: str | None = None):
        return self.coordinator.device.snapshot.value(key or self.key, self.coordinator.device.config)


class HouseHeatingControlEntity(HouseHeatingEntity):
    @property
    def available(self) -> bool:
        return super().available and self.coordinator.device.control_ready and self.register_value() is not None
