"""Hot-water entity that retains the shared space-heating mode."""
from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP, STATE_OFF, WaterHeaterEntity, WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from ._vendor.househeating_modbus.controls import DHW_MODES, dhw_plan
from ._vendor.househeating_modbus.models import WriteRejected
from .entity import HouseHeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    # Register once so recovery from a missing optional register needs no reload.
    async_add_entities([HouseHeatingWaterHeater(entry.runtime_data)])


class HouseHeatingWaterHeater(HouseHeatingEntity, WaterHeaterEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = [STATE_OFF, STATE_HEAT_PUMP]
    _attr_target_temperature_step = 1.0
    _attr_supported_features = (WaterHeaterEntityFeature.TARGET_TEMPERATURE
                                | WaterHeaterEntityFeature.OPERATION_MODE
                                | WaterHeaterEntityFeature.ON_OFF)

    def __init__(self, coordinator):
        super().__init__(coordinator, "dhw_water_heater")

    @property
    def available(self):
        raw = self.coordinator.device.snapshot.raw
        supported = raw.get(0x130) == 1 or raw.get(0x304) in DHW_MODES
        return (super().available and self.coordinator.device.control_ready and supported
                and self.register_value("dhw_temperature") is not None
                and self.register_value("dhw_setpoint") is not None)

    @property
    def current_temperature(self):
        return self.register_value("dhw_temperature")

    @property
    def target_temperature(self):
        return self.register_value("dhw_setpoint")

    @property
    def min_temp(self):
        return self.coordinator.device.config.limits("dhw_setpoint")[0]

    @property
    def max_temp(self):
        return self.coordinator.device.config.limits("dhw_setpoint")[1]

    @property
    def current_operation(self):
        raw = self.coordinator.device.snapshot.raw
        return STATE_HEAT_PUMP if raw.get(0x305) == 1 and raw.get(0x304) in DHW_MODES else STATE_OFF

    async def async_set_operation_mode(self, operation_mode):
        def plan(snapshot):
            if operation_mode not in self.operation_list:
                raise WriteRejected("Unsupported hot-water operation")
            if not (snapshot.raw.get(0x130) == 1 or snapshot.raw.get(0x304) in DHW_MODES):
                raise WriteRejected("Hot-water support is not confirmed")
            if self.register_value("dhw_temperature") is None:
                raise WriteRejected("A valid hot-water temperature is required")
            return dhw_plan(snapshot.raw, operation_mode == STATE_HEAT_PUMP)
        await self.coordinator.async_control(plan)

    async def async_turn_on(self, **kwargs):
        await self.async_set_operation_mode(STATE_HEAT_PUMP)

    async def async_turn_off(self, **kwargs):
        await self.async_set_operation_mode(STATE_OFF)

    async def async_set_temperature(self, **kwargs):
        if ATTR_TEMPERATURE in kwargs:
            def plan(snapshot):
                if not (snapshot.raw.get(0x130) == 1 or snapshot.raw.get(0x304) in DHW_MODES):
                    raise WriteRejected("Hot-water support is not confirmed")
                if self.register_value("dhw_temperature") is None:
                    raise WriteRejected("A valid hot-water temperature is required")
                return [("dhw_setpoint", kwargs[ATTR_TEMPERATURE])]
            await self.coordinator.async_control(plan)
