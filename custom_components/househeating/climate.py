"""Space heating and cooling using the shared, verified control boundary."""

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from ._vendor.househeating_modbus.controls import SPACE_MODES, space_plan
from ._vendor.househeating_modbus.models import WriteRejected
from ._vendor.househeating_modbus.registers import MODE_OPTIONS, PROFILE_OPTIONS
from .entity import HouseHeatingEntity

SETPOINTS = {"cool": "cooling_setpoint", "heat": "heating_setpoint", "floor_heating": "floor_setpoint"}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HouseHeatingClimate(entry.runtime_data)])


def _resulting_mode(raw, commands):
    mode = raw.get(0x304)
    for key, value in commands:
        if key == "operating_mode":
            mode = MODE_OPTIONS[value]
    return mode


class HouseHeatingClimate(HouseHeatingEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    # Presets are the global operating profile only. Floor heating is a separate
    # switch: one preset list for two independent settings hid mode changes.
    _attr_preset_modes = list(PROFILE_OPTIONS)
    _attr_target_temperature_step = 1.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator):
        super().__init__(coordinator, "climate_main")

    def _space_mode(self, mode=None):
        if mode is None:
            mode = self.coordinator.device.snapshot.raw.get(0x304)
        return SPACE_MODES.get(mode)

    @property
    def _setpoint_key(self):
        return SETPOINTS.get(self._space_mode(), "heating_setpoint")

    @property
    def available(self):
        return (
            super().available
            and self.coordinator.device.control_ready
            and self.register_value(self._setpoint_key) is not None
        )

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
    def hvac_action(self):
        """Reported compressor status; no prediction of the manufacturer's regulation."""
        raw = self.coordinator.device.snapshot.raw
        status, mode = raw.get(0), raw.get(0x304)
        if status is None or mode is None:
            return None
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if not status & (1 << 14):
            return HVACAction.IDLE
        if mode == 0:
            return HVACAction.COOLING
        if mode in (1, 3, 5, 7):
            return HVACAction.HEATING
        # Mode 4: the running compressor may serve hot water or cooling.
        return None

    @property
    def preset_mode(self):
        profile = self.coordinator.device.snapshot.raw.get(0x307)
        return next((name for name, value in PROFILE_OPTIONS.items() if value == profile), None)

    @property
    def extra_state_attributes(self):
        return {"floor_heating": self._space_mode() == "floor_heating"}

    def _hvac_commands(self, snapshot, hvac_mode):
        if hvac_mode not in self.hvac_modes:
            raise WriteRejected("Unsupported HVAC mode")
        requested = str(hvac_mode)
        if hvac_mode == HVACMode.HEAT and snapshot.raw.get(0x304) in (3, 7):
            requested = "floor_heating"
        return space_plan(snapshot.raw, requested)

    async def async_set_hvac_mode(self, hvac_mode):
        await self.coordinator.async_control(lambda snapshot: self._hvac_commands(snapshot, hvac_mode))

    async def async_turn_on(self):
        def plan(snapshot):
            mode = SPACE_MODES.get(snapshot.raw.get(0x304))
            return space_plan(snapshot.raw, mode or self.coordinator.last_space_mode or "heat")

        await self.coordinator.async_control(plan)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode):
        def plan(snapshot):
            if preset_mode not in PROFILE_OPTIONS:
                raise WriteRejected("Unsupported preset")
            return [("operating_profile", preset_mode)]

        await self.coordinator.async_control(plan)

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get(ATTR_TEMPERATURE)
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if temperature is None and hvac_mode is None:
            return

        def plan(snapshot):
            commands = self._hvac_commands(snapshot, hvac_mode) if hvac_mode is not None else []
            if temperature is None:
                return commands
            # The setpoint belongs to the space mode that results from this
            # command; switching off keeps the setpoint of the current space mode.
            space = (
                self._space_mode(_resulting_mode(snapshot.raw, commands))
                or self._space_mode(snapshot.raw.get(0x304))
                or self.coordinator.last_space_mode
                or "heat"
            )
            power_on = [c for c in commands if c == ("power", True)]
            others = [c for c in commands if c != ("power", True)]
            # Set the temperature before switching the unit on.
            return others + [(SETPOINTS[space], temperature)] + power_on

        await self.coordinator.async_control(plan)
