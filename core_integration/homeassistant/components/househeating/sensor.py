"""Measurements and read-only diagnostics."""
from time import time
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.entity import EntityCategory

from househeating_modbus import REGISTERS, SELECTS
from househeating_modbus.registers import WRITABLE_KEYS
from .entity import HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(HouseHeatingSensor(coordinator, r) for r in REGISTERS)
    if coordinator.monitoring is not None:
        async_add_entities(MonitoringSensor(coordinator, key, *description)
                           for key, description in MONITORING_SENSORS.items())
    if coordinator.operation is not None:
        keys=list(OPERATION_SENSORS)[:5] if coordinator.operation.statistics else []
        if coordinator.operation.config.enabled:
            keys.extend(list(OPERATION_SENSORS)[5:])
        async_add_entities(OperationSensor(coordinator,key,*OPERATION_SENSORS[key]) for key in keys)


class HouseHeatingSensor(HouseHeatingEntity, SensorEntity):
    def __init__(self, coordinator, register):
        super().__init__(coordinator, register.key)
        self.register = register
        self._attr_entity_registry_enabled_default = register.default_enabled and register.key not in WRITABLE_KEYS
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
                "optional_sample_time": (snapshot.timestamp if self.register.group == "fast"
                                         else snapshot.optional_timestamp if self.register.group != "core" else None)}


# Device classes and state classes are explicit, independent of protocol registers.
MONITORING_SENSORS = {
    "selected_electrical_power": ("kW", "power", "measurement"),
    "electrical_energy_total": ("kWh", "energy", "total"),
    "water_flow_calibrated": ("L/min", "volume_flow_rate", "measurement"),
    "water_delta_temperature": ("K", "temperature_delta", "measurement"),
    "thermal_power_estimated": ("kW", "power", "measurement"),
    "thermal_power_hydraulic_estimated":("kW","power","measurement"),
    "thermal_power_external_reported":("kW","power","measurement"),
    "thermal_energy_delivered": ("kWh", "energy", "total"),
    "thermal_energy_extracted": ("kWh", "energy", "total"),
    "thermal_energy_net": ("kWh", "energy", "total"),
    "cop_instant": (None, None, "measurement"),
    "eer_instant": (None, None, "measurement"),
    "monitoring_status": (None, "enum", None),
}
for _scope in ("day", "month"):
    for _key in ("electrical_energy", "thermal_energy_net", "heating_energy_paired",
                 "heating_electricity_paired", "cooling_energy_paired", "cooling_electricity_paired"):
        MONITORING_SENSORS[f"{_key}_{_scope}"] = ("kWh", "energy", "total")
    for _kind in ("cop", "eer"):
        MONITORING_SENSORS[f"{_kind}_{_scope}"] = (None, None, "measurement")
        MONITORING_SENSORS[f"{_kind}_coverage_{_scope}"] = ("%", None, "measurement")

for _scope in ("yesterday","7d","30d","365d","overall"):
    for _key in ("heating_energy_paired","heating_electricity_paired","cooling_energy_paired","cooling_electricity_paired"):
        # Sliding windows may shrink when days expire; these are measurements,
        # not resetting energy counters intended for the Energy dashboard.
        MONITORING_SENSORS[f"{_key}_{_scope}"]=("kWh","energy","total" if _scope=="overall" else None)
    for _kind in ("cop","eer"):
        MONITORING_SENSORS[f"{_kind}_{_scope}"]=(None,None,"measurement")
        MONITORING_SENSORS[f"{_kind}_coverage_{_scope}"]=("%",None,"measurement")

OPERATION_SENSORS={
    "compressor_starts_observed":(None,None,"total_increasing"),
    "compressor_runtime_observed":("h","duration","total_increasing"),
    "compressor_starts_day":(None,None,None),
    "compressor_runtime_day":("h","duration",None),
    "compressor_cycle_average":("min","duration","measurement"),
    "curve_base_target":("°C","temperature","measurement"),
    "curve_offset":("K","temperature_delta","measurement"),
    "curve_advised_target":("°C","temperature","measurement"),
    "curve_status":(None,"enum",None),
}


class MonitoringSensor(HouseHeatingEntity, SensorEntity):
    def __init__(self, coordinator, key, unit, device_class, state_class):
        super().__init__(coordinator, key)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = SensorDeviceClass(device_class) if device_class else None
        self._attr_state_class = SensorStateClass(state_class) if state_class else None
        self._attr_suggested_display_precision = 3 if unit == "kWh" else 2
        if key == "monitoring_status":
            self._attr_options = ["valid", "awaiting_confirmation", "partial", "unavailable", "storage_error"]
            self._attr_suggested_display_precision = None

    @property
    def native_value(self):
        return self.coordinator.monitoring.values().get(self.key)

    @property
    def available(self):
        # Stored cumulative totals remain readable when the device is offline;
        # instantaneous values are invalidated by the manager and its watchdog.
        return self.coordinator.monitoring is not None and self.native_value is not None

    @property
    def last_reset(self):
        if self._attr_state_class != SensorStateClass.TOTAL:
            return None
        from datetime import datetime, timezone
        for scope in ("day", "month"):
            if self.key.endswith("_" + scope):
                bucket = self.coordinator.monitoring.ledger.periods.get(scope)
                return datetime.fromtimestamp(bucket.start, timezone.utc) if bucket else None
        return None

    @property
    def extra_state_attributes(self):
        manager = self.coordinator.monitoring
        result = {"measurement_origin": "calculated" if self.key != "monitoring_status" else "diagnostic",
                  "electrical_source": manager.config.source,
                  "external_power_entity": manager.config.external_power or None,
                  "external_energy_entity": manager.config.external_energy or None,
                  "thermal_estimate": manager.config.thermal_source=="hydraulic" and not self.key.startswith(("electrical_", "selected_electrical_")),
                  "thermal_source":manager.config.thermal_source,
                  "external_heat_power_entity":manager.config.external_heat_power or None,
                  "fluid_reference": manager.config.fluid_reference,
                  "quality": manager.values()["monitoring_status"]}
        if self.key=="thermal_power_hydraulic_estimated":
            result["thermal_estimate"]=True
        if self.key=="thermal_power_external_reported" or (self.key=="thermal_power_estimated" and manager.config.thermal_source=="external"):
            result["measurement_origin"]="external_meter_reported_power"
            result["thermal_estimate"]=False
        for scope in ("yesterday","7d","30d","365d","overall"):
            if self.key.endswith("_"+scope):
                bucket,elapsed=manager.ledger.aggregate(scope,time())
                kind="cooling" if self.key.startswith(("eer","cooling")) else "heating"
                result.update(paired_electrical_kwh=bucket.cool_electric if kind=="cooling" else bucket.heat_electric,
                              paired_thermal_kwh=bucket.cool_output if kind=="cooling" else bucket.heat_net,
                              elapsed_seconds=elapsed,heating_seconds=bucket.heat_seconds,cooling_seconds=bucket.cool_seconds,
                              excluded_seconds=max(0,elapsed-bucket.heat_seconds-bucket.cool_seconds))
        for scope in ("day", "month"):
            bucket = manager.ledger.periods.get(scope)
            if self.key.endswith("_" + scope) and bucket:
                elapsed = max(0, min(time(), bucket.end) - bucket.start)
                result.update(elapsed_seconds=elapsed,
                              heating_seconds=bucket.heat_seconds,
                              cooling_seconds=bucket.cool_seconds,
                              excluded_seconds=max(0, elapsed-bucket.heat_seconds-bucket.cool_seconds),
                              exclusion_reasons=dict(bucket.excluded),
                              period_flags=list(bucket.flags))
            if self.key in (f"cop_{scope}", f"eer_{scope}"):
                values = manager.values()
                kind = "heating" if self.key.startswith("cop") else "cooling"
                result.update(paired_electrical_kwh=values.get(f"{kind}_electricity_paired_{scope}"),
                              paired_thermal_kwh=values.get(f"{kind}_energy_paired_{scope}"),
                              coverage_percent=values.get(f"{self.key.split('_')[0]}_coverage_{scope}"))
                previous = manager.ledger.previous_periods.get(scope)
                if previous:
                    from dataclasses import asdict
                    result["previous_period"] = asdict(previous)
        return result


class OperationSensor(HouseHeatingEntity,SensorEntity):
    def __init__(self,coordinator,key,unit,device_class,state_class):
        super().__init__(coordinator,key)
        self._attr_native_unit_of_measurement=unit
        self._attr_device_class=SensorDeviceClass(device_class) if device_class else None
        self._attr_state_class=SensorStateClass(state_class) if state_class else None
        self._attr_suggested_display_precision=0 if key.startswith('compressor_starts') else 2
        if key=="curve_status":
            self._attr_options=["disabled","advisory","source_unavailable","control_locked","inactive_mode",
                                "native_curve_active","cooldown","unchanged","controlling","manual_override","write_error"]
            self._attr_suggested_display_precision=None

    @property
    def native_value(self):
        return self.coordinator.operation.values().get(self.key)

    @property
    def available(self):
        return self.native_value is not None

    @property
    def extra_state_attributes(self):
        manager=self.coordinator.operation
        return {"measurement_origin":"observed_since_enable" if self.key.startswith("compressor_") else "calculated",
                "statistics_storage_error":manager.storage_error,
                "control_target":manager.config.target,"automatic":manager.config.automatic,
                "latched_stop":manager.blocked}
