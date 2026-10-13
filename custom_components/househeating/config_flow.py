"""UI setup, reconfiguration and explicit commissioning authorization."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import probatio as vol

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from ._vendor.househeating_modbus import BY_KEY, HeatPump, HeatPumpError
from .connection import connection_params, device_config, normalize_connection
from .const import DEFAULT_NAME, DEFAULT_OPTIONS, DOMAIN


def connection_schema(defaults: dict[str, Any]):
    return vol.Schema({
        vol.Required("name", default=defaults.get("name", DEFAULT_NAME)): str,
        vol.Required("transport", default=defaults.get("transport", "rtu_tcp")): SelectSelector(
            SelectSelectorConfig(options=["rtu_tcp", "tcp", "serial"],
                                 mode=SelectSelectorMode.DROPDOWN, translation_key="transport")),
        vol.Optional("host", default=defaults.get("host", "")): str,
        vol.Optional("port", default=defaults.get("port", 502)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional("serial_device", default=defaults.get("serial_device", "")): str,
        vol.Required("unit_id", default=defaults.get("unit_id", 1)): vol.All(vol.Coerce(int), vol.Range(min=1, max=247)),
    })


def options_schema(options):
    return vol.Schema({
        vol.Required("scan_interval", default=options["scan_interval"]): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
        vol.Required("slow_interval", default=options["slow_interval"]): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
        vol.Required("measurement_divisor", default=str(options["measurement_divisor"])): SelectSelector(
            SelectSelectorConfig(options=["10", "1"], translation_key="temperature_divisor")),
        vol.Required("setpoint_divisor", default=str(options["setpoint_divisor"])): SelectSelector(
            SelectSelectorConfig(options=["10", "1"], translation_key="temperature_divisor")),
        vol.Required("max_read", default=options["max_read"]): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Required("spacing_ms", default=options["spacing_ms"]): vol.All(vol.Coerce(int), vol.Range(min=100, max=5000)),
        vol.Required("timeout", default=options["timeout"]): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
        vol.Required("extended", default=options["extended"]): bool,
        vol.Required("curves", default=options["curves"]): bool,
        vol.Required("max_heating", default=options["max_heating"]): vol.All(vol.Coerce(int), vol.Range(min=20, max=60)),
        vol.Required("max_floor", default=options["max_floor"]): vol.All(vol.Coerce(int), vol.Range(min=20, max=60)),
        vol.Required("max_dhw", default=options["max_dhw"]): vol.All(vol.Coerce(int), vol.Range(min=20, max=65)),
        vol.Required("allow_control", default=options["allow_control"]): bool,
    })


async def probe(hass, data, options):
    """Use a temporary SHARED unit; never write anything during a probe."""
    config = replace(device_config(options), extended=False, curves=False)
    async with async_get_temporary_unit(hass, connection_params(data), data["unit_id"]) as unit:
        device = HeatPump(unit, config)
        await device.async_update()
        if not device.snapshot.layout_valid:
            raise ValueError("Mode/profile/on-off registers do not match the documented layout")
        return device


class HouseHeatingConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HouseHeatingOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                data = normalize_connection(user_input)
                await self.async_set_unique_id(data["connection_key"])
                self._abort_if_unique_id_configured()
                await probe(self.hass, data, DEFAULT_OPTIONS)
            except ValueError:
                errors["base"] = "invalid_connection"
            except (HeatPumpError, HomeAssistantError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=data["name"], data=data,
                                               options=dict(DEFAULT_OPTIONS))
        return self.async_show_form(step_id="user", data_schema=connection_schema(user_input or {}), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            try:
                data = normalize_connection(user_input)
                if any(e.entry_id != entry.entry_id and e.data.get("connection_key") == data["connection_key"]
                       for e in self._async_current_entries()):
                    return self.async_abort(reason="already_configured")
                await probe(self.hass, data, dict(entry.options))
            except ValueError:
                errors["base"] = "invalid_connection"
            except (HeatPumpError, HomeAssistantError):
                errors["base"] = "cannot_connect"
            else:
                options = dict(entry.options) | {"allow_control": False, "authorized_identity": []}
                # Entity and device identities use entry_id, so an address change
                # retains their history. No separate update listener is registered.
                self.hass.config_entries.async_update_entry(entry, data=data, options=options,
                                                           title=data["name"], unique_id=data["connection_key"])
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(step_id="reconfigure",
                                    data_schema=connection_schema(user_input or dict(entry.data)), errors=errors)


class HouseHeatingOptionsFlow(OptionsFlowWithReload):
    """Always re-confirm before enabling control; do not write test setpoints."""

    def __init__(self):
        self._pending = None
        self._fingerprint = None
        self._preview = ""

    async def async_step_init(self, user_input=None):
        errors = {}
        options = DEFAULT_OPTIONS | dict(self.config_entry.options)
        if user_input is not None:
            pending = dict(options) | user_input
            pending["measurement_divisor"] = int(pending["measurement_divisor"])
            pending["setpoint_divisor"] = int(pending["setpoint_divisor"])
            pending["authorized_identity"] = []
            try:
                device_config(pending)
                if pending["allow_control"]:
                    device = await probe(self.hass, dict(self.config_entry.data), pending)
                    identity = device.validate_for_control()
                    self._fingerprint = identity.fingerprint
                    rows = []
                    for key in ("outdoor_temperature", "water_inlet_temperature", "water_outlet_temperature",
                                "cooling_setpoint", "heating_setpoint", "dhw_setpoint", "floor_setpoint"):
                        reg = BY_KEY[key]
                        value = device.snapshot.value(key, device.config)
                        raw = device.snapshot.raw[reg.address]
                        rows.append(f"- {reg.name}: **{value:g} °C** (0x{reg.address:04X}: {raw})")
                    rows.append(f"- Firmware: {identity.firmware_text}; protocol: {identity.protocol}")
                    self._preview = "\n".join(rows)
            except ValueError:
                errors["base"] = "invalid_options"
            except (HeatPumpError, HomeAssistantError):
                errors["base"] = "commissioning_failed"
            else:
                self._pending = pending
                if pending["allow_control"]:
                    return await self.async_step_confirm_control()
                return self.async_create_entry(title="", data=pending)
            options = pending
        return self.async_show_form(step_id="init", data_schema=options_schema(options), errors=errors)

    async def async_step_confirm_control(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get("confirm_values") is not True:
                errors["base"] = "confirmation_required"
            else:
                # A second read catches a changed device/firmware while the form was open.
                try:
                    device = await probe(self.hass, dict(self.config_entry.data), self._pending)
                    identity = device.validate_for_control()
                    if identity.fingerprint != self._fingerprint:
                        raise ValueError("Identity changed during confirmation")
                except (ValueError, HeatPumpError, HomeAssistantError):
                    errors["base"] = "commissioning_failed"
                else:
                    pending = dict(self._pending)
                    pending["authorized_identity"] = list(identity.fingerprint)
                    return self.async_create_entry(title="", data=pending)
        return self.async_show_form(step_id="confirm_control",
                                    data_schema=vol.Schema({vol.Required("confirm_values", default=False): bool}),
                                    description_placeholders={"readings": self._preview}, errors=errors)
