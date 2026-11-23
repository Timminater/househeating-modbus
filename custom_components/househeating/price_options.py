"""Configuration form for integrated price-based heating."""

from datetime import UTC, datetime
from uuid import uuid4

import probatio as vol
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig, SelectSelector, SelectSelectorConfig
from homeassistant.util import dt as dt_util

from .price_plan import read_tariffs

DEFAULTS = {
    "mode": "off",
    "forecast_attribute": "forecast",
    "start_field": "start_date",
    "end_field": "",
    "price_field": "",
    "price_scale": 1.0,
    "interval_minutes": 60,
    "buffer": False,
    "hold_during_peak": False,
    "allow_defer": False,
    "water_boost": 0.0,
    "buffer_min": 30.0,
    "preheat_offset": 0.3,
    "comfort_margin": 0.2,
    "max_hours": "1",
    "pump_overrun": 10,
    "minimum_spread": 0.05,
    "extra_energy": 10.0,
}
ENTITIES = {
    "price_entity": ["sensor"],
    "climate_entity": ["climate"],
    "comfort_entities": ["climate"],
    "demand_entities": ["climate", "sensor", "binary_sensor", "switch", "number", "input_boolean"],
    "buffer_entity": ["sensor"],
    "floor_pump": ["switch", "binary_sensor"],
    "pump_start": ["switch", "button"],
    "pump_stop": ["button"],
    "pump_feedback": ["switch", "sensor", "binary_sensor"],
    "power_entity": ["sensor"],
}
MULTIPLE = ("comfort_entities", "demand_entities")
LIMITS = {
    "price_scale": (0.000001, 1e12),
    "interval_minutes": (1, 60),
    "buffer_min": (0, 75),
    "preheat_offset": (0, 3),
    "comfort_margin": (0, 3),
    "pump_overrun": (0, 60),
    "minimum_spread": (0, 10),
    "extra_energy": (0, 100),
    "water_boost": (0, 5),
}


async def price_options(flow, user_input):
    options = dict(flow.config_entry.options)
    saved = options.get("price_control", {})
    defaults = DEFAULTS | saved
    errors = {}
    if user_input is not None:
        config = DEFAULTS | dict(user_input)
        defaults.update(config)
        if config["mode"] == "off":
            options["price_control"] = config
            return flow.async_create_entry(title="", data=options)
        if config["hold_during_peak"] and (
            not config["buffer"] or not config.get("climate_entity") or config["comfort_margin"] <= 0.1
        ):
            errors["hold_during_peak"] = "price_hold_requirements"
        if config["mode"] == "automatic":
            if config["water_boost"] and (
                options.get("weather_curve", {}).get("automatic")
                or not options.get("curves", True)
                or len(options.get("authorized_identity", [])) != 4
                or options["authorized_identity"][3] < 130
            ):
                errors["water_boost"] = "price_water_requirements"
            if (
                not options.get("allow_control")
                or len(options.get("authorized_identity", [])) != 4
                or not config.get("demand_entities")
                or not config.get("confirm_control")
                or not (config.get("comfort_entities") or config.get("climate_entity"))
            ):
                errors["base"] = "price_control_requirements"
            start = config.get("pump_start", "")
            if (
                config["buffer"]
                and start
                and (
                    (
                        start.startswith("button.")
                        and (
                            not config.get("pump_stop")
                            or not config.get("pump_feedback")
                            or start == config["pump_stop"]
                        )
                    )
                    or start == config.get("floor_pump")
                    or start in config["demand_entities"]
                    or config.get("pump_feedback") == config.get("floor_pump")
                    and config.get("floor_pump")
                    or config.get("pump_feedback") in config["demand_entities"]
                )
            ):
                errors["base"] = "price_pump_configuration"
        if not errors:
            try:
                source = flow.hass.states.get(config.get("price_entity", ""))
                if source is None or source.state in ("unknown", "unavailable"):
                    raise ValueError("No price source")
                rows = read_tariffs(source.attributes, config)
                now = dt_util.utcnow().timestamp()
                row = next(value for value in rows if value.start <= now < value.end)
            except (ArithmeticError, KeyError, TypeError, ValueError, StopIteration):
                errors["price_entity"] = "invalid_price_forecast"
            else:
                flow._price_candidate = config
                flow._price_preview = {
                    "start": dt_util.as_local(datetime.fromtimestamp(row.start, UTC)).isoformat(),
                    "end": dt_util.as_local(datetime.fromtimestamp(row.end, UTC)).isoformat(),
                    "price": f"{row.price:.5f}",
                }
                return await price_confirm(flow, None)
    schema = {}
    for key, value in DEFAULTS.items():
        marker = vol.Required(key, default=defaults.get(key, value))
        if key == "mode":
            schema[marker] = SelectSelector(
                SelectSelectorConfig(options=["off", "advice", "automatic"], translation_key="price_mode")
            )
        elif key == "max_hours":
            schema[marker] = SelectSelector(SelectSelectorConfig(options=["0.5", "1", "1.5", "2", "2.5", "3"]))
        elif key in LIMITS:
            low, high = LIMITS[key]
            schema[marker] = vol.All(vol.Coerce(float), vol.Range(min=low, max=high))
        else:
            schema[marker] = type(value)
    for key, domains in ENTITIES.items():
        marker = vol.Optional(key, default=defaults[key]) if defaults.get(key) else vol.Optional(key)
        schema[marker] = EntitySelector(
            EntitySelectorConfig(
                filter={"domain": domains},
                multiple=key in MULTIPLE,
            )
        )
    schema[vol.Required("confirm_control", default=False)] = bool
    return flow.async_show_form(step_id="price_control", data_schema=vol.Schema(schema), errors=errors)


async def price_confirm(flow, user_input):
    config = getattr(flow, "_price_candidate", None)
    if config is None:
        return await price_options(flow, None)
    if user_input is not None and user_input.get("confirm"):
        config["authorization"] = uuid4().hex
        options = dict(flow.config_entry.options)
        options["price_control"] = config
        return flow.async_create_entry(title="", data=options)
    return flow.async_show_form(
        step_id="price_confirm",
        data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        description_placeholders=flow._price_preview,
    )
