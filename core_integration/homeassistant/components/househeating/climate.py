"""Space heating and cooling using the shared, verified control boundary."""
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from househeating_modbus.controls import SPACE_MODES, space_plan
from househeating_modbus.models import WriteRejected
from househeating_modbus.registers import PROFILE_OPTIONS
from .entity import HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HouseHeatingClimate(entry.runtime_data)])


class HouseHeatingClimate(HouseHeatingEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_preset_modes = ["standard", "powerful", "silent", "floor_heating"]
    _attr_target_temperature_step = 1.0
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE
                                | ClimateEntityFeature.PRESET_MODE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)

    def __init__(self, coordinator):
        super().__init__(coordinator, "climate_main")

    @property
    def _setpoint_key(self):
        space = SPACE_MODES.get(self.coordinator.device.snapshot.raw.get(0x304))
        return {"cool": "cooling_setpoint", "floor_heating": "floor_setpoint"}.get(space, "heating_setpoint")

    @property
    def available(self):
        return (super().available and self.coordinator.device.control_ready
                and self.register_value(self._setpoint_key) is not None)

    @property
    def current_temperature(self):
        mode = self.coordinator.device.snapshot.raw.get(0x174)
        if mode not in (0, 1):
            return None
        return self.register_value("water_inlet_temperature" if mode == 0 else "water_outlet_temperature")

    @property
    def target_temperature(self):
        return self.register_value(self._setpoint_key)

    @property
    def min_temp(self):
        return self.coordinator.device.config.limits(self._setpoint_key)[0]

    @property
    def max_temp(self):
        return self.coordinator.device.config.limits(self._setpoint_key)[1]

    @property
    def hvac_mode(self):
        raw = self.coordinator.device.snapshot.raw
        if raw.get(0x305) != 1 or raw.get(0x304) == 2:
            return HVACMode.OFF
        return HVACMode.COOL if raw.get(0x304) in (0, 4) else HVACMode.HEAT

    @property
    def preset_mode(self):
        profile = self.coordinator.device.snapshot.raw.get(0x307)
        if profile in (1, 2):
            return "powerful" if profile == 1 else "silent"
        return "floor_heating" if self.coordinator.device.snapshot.raw.get(0x304) in (3, 7) else "standard"

    async def async_set_hvac_mode(self, hvac_mode):
        def plan(snapshot):
            if hvac_mode not in self.hvac_modes:
                raise WriteRejected("Unsupported HVAC mode")
            requested = str(hvac_mode)
            if hvac_mode == HVACMode.HEAT and snapshot.raw.get(0x304) in (3, 7):
                requested = "floor_heating"
            return space_plan(snapshot.raw, requested)
        await self.coordinator.async_control(plan)

    async def async_turn_on(self):
        def plan(snapshot):
            mode = SPACE_MODES.get(snapshot.raw.get(0x304))
            return space_plan(snapshot.raw, mode or self.coordinator.last_space_mode or "heat")
        await self.coordinator.async_control(plan)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode):
        def plan(snapshot):
            if preset_mode == "floor_heating":
                # Select the space mode without implicitly switching a stopped pump on.
                return [("operating_profile", "standard")] + [
                    item for item in space_plan(snapshot.raw, "floor_heating") if item[0] != "power"]
            if preset_mode not in PROFILE_OPTIONS:
                raise WriteRejected("Unsupported preset")
            commands = [("operating_profile", preset_mode)]
            if preset_mode == "standard" and snapshot.raw.get(0x304) in (3, 7):
                commands += [item for item in space_plan(snapshot.raw, "heat") if item[0] != "power"]
            return commands
        await self.coordinator.async_control(plan)

    async def async_set_temperature(self, **kwargs):
        if ATTR_TEMPERATURE in kwargs:
            await self.coordinator.async_control(lambda snapshot: [(self._setpoint_key, kwargs[ATTR_TEMPERATURE])])
