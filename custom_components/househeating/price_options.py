"""Configuration form for integrated price-based heating."""

from datetime import UTC, datetime
from uuid import uuid4

import probatio as vol
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig, SelectSelector, SelectSelectorConfig
from homeassistant.util import dt as dt_util

from .price_plan import read_tariffs

DEFAULTS = {
    "mode": "off",
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
    "execution_entity": ["binary_sensor", "input_boolean", "switch"],
}
GROUPS = {
    "comfort": ("comfort_entities", "climate_entity", "preheat_offset", "comfort_margin", "water_boost", "allow_defer"),
    "heating": ("demand_entities", "confirm_control"),
    "hydraulics": (
        "buffer_entity",
        "buffer_min",
        "hold_during_peak",
        "floor_pump",
        "pump_start",
        "pump_stop",
        "pump_feedback",
        "pump_overrun",
    ),
    "economics": ("minimum_spread", "extra_energy", "power_entity", "execution_entity"),
}
TARIFF_SUFFIXES = ("_current_electricity_tariff", "_current_quarter_hourly_electricity_tariff")


def is_zonneplan_tariff(entry):
    return (
        entry is not None
        and entry.domain == "sensor"
        and entry.platform == "zonneplan_one"
        and entry.unique_id.endswith(TARIFF_SUFFIXES)
    )


BASIC = ("mode", "price_entity", "max_hours", "buffer")
PUMP_FIELDS = {"floor_pump", "pump_start", "pump_stop", "pump_feedback", "pump_overrun"}

MULTIPLE = ("comfort_entities", "demand_entities")
LIMITS = {
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
    defaults = DEFAULTS | options.get("price_control", {})
    if user_input is not None:
        config = defaults | user_input
        if not user_input.get("price_entity"):
            config.pop("price_entity", None)
        if config["mode"] == "off":
            options["price_control"] = config
            return flow.async_create_entry(title="", data=options)
        try:
            preview = price_preview(flow, config)
        except (ArithmeticError, KeyError, TypeError, ValueError, StopIteration):
            errors = {"price_entity": "invalid_price_forecast"}
            defaults = config
        else:
            flow._price_basics = config
            flow._price_preview = preview
            return await price_settings(flow, None)
    else:
        errors = {}
    fields = schema_fields(flow, defaults)
    return flow.async_show_form(
        step_id="price_control", data_schema=vol.Schema(dict(fields[key] for key in BASIC)), errors=errors
    )


def price_preview(flow, config):
    source = flow.hass.states.get(config.get("price_entity", ""))
    if (
        source is None
        or source.state in ("unknown", "unavailable")
        or not is_zonneplan_tariff(er.async_get(flow.hass).async_get(source.entity_id))
    ):
        raise ValueError("No price source")
    now = dt_util.utcnow().timestamp()
    row = next(value for value in read_tariffs(source.attributes) if value.start <= now < value.end)
    return {
        "start": dt_util.as_local(datetime.fromtimestamp(row.start, UTC)).strftime("%d-%m-%Y %H:%M"),
        "end": dt_util.as_local(datetime.fromtimestamp(row.end, UTC)).strftime("%d-%m-%Y %H:%M"),
        "price": f"{row.price:.5f}",
    }


async def price_settings(flow, user_input):
    if not (defaults := getattr(flow, "_price_basics", None)):
        return await price_options(flow, None)
    options = flow.config_entry.options
    automatic = defaults["mode"] == "automatic"
    groups = {
        group: tuple(
            key
            for key in keys
            if (automatic or key not in PUMP_FIELDS) and (not automatic or key != "execution_entity")
        )
        for group, keys in GROUPS.items()
        if (group != "heating" or automatic) and (group != "hydraulics" or defaults["buffer"])
    }
    errors = {}
    if user_input is not None:
        config = dict(defaults)
        for group, keys in groups.items():
            if group not in user_input:
                continue
            submitted = user_input[group]
            for key in keys:
                if key in submitted:
                    config[key] = submitted[key]
                elif key in ENTITIES:
                    config.pop(key, None)
        if not config["buffer"]:
            config["hold_during_peak"] = False
        config = {key: value for key, value in config.items() if key in DEFAULTS or key in ENTITIES}
        defaults = config
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
                flow._price_preview = price_preview(flow, config)
            except (ArithmeticError, KeyError, TypeError, ValueError, StopIteration):
                return await price_options(flow, {key: config[key] for key in BASIC if key in config})
            flow._price_candidate = config
            return await price_confirm(flow, None)
    fields = schema_fields(flow, defaults, nested=True)
    form = {}
    for group, keys in groups.items():
        form[vol.Optional(group)] = section(
            vol.Schema(dict(fields[key] for key in keys)),
            {"collapsed": group != "heating" and not any(key in errors for key in keys) and "base" not in errors},
        )
    return flow.async_show_form(step_id="price_settings", data_schema=vol.Schema(form), errors=errors)


def schema_fields(flow, defaults, *, nested=False):
    schema = {}
    for key, value in DEFAULTS.items():
        initial = defaults.get(key, value)
        marker = vol.Required(key, default=initial, description={"suggested_value": initial} if nested else None)
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
        initial = defaults.get(key)
        if nested:
            marker = vol.Optional(key, description={"suggested_value": initial} if initial else None)
        else:
            marker = vol.Optional(key, default=initial) if initial else vol.Optional(key)
        if key == "price_entity":
            registry = er.async_get(flow.hass)
            candidates = [
                entry.entity_id
                for entry in registry.entities.values()
                if is_zonneplan_tariff(entry) and entry.disabled_by is None
            ]
            schema[marker] = EntitySelector(
                EntitySelectorConfig(
                    filter={"domain": "sensor", "integration": "zonneplan_one"},
                    include_entities=candidates
                    or [
                        "sensor.zonneplan_current_electricity_tariff",
                        "sensor.zonneplan_current_quarter_hourly_electricity_tariff",
                    ],
                )
            )
            continue
        schema[marker] = EntitySelector(
            EntitySelectorConfig(
                filter={"domain": domains},
                multiple=key in MULTIPLE,
            )
        )
    schema[vol.Required("confirm_control", default=False)] = bool
    return {marker.schema: (marker, validator) for marker, validator in schema.items()}


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
