"""Generate a dashboard from the entity registry without altering user dashboards."""
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
import probatio as vol

from .const import DOMAIN


def dashboard_config(hass,entry):
    registry=er.async_get(hass)
    prefix=entry.entry_id+"_"
    entities={item.unique_id[len(prefix):]:item.entity_id for item in
              er.async_entries_for_config_entry(registry,entry.entry_id)
              if item.platform==DOMAIN and item.unique_id.startswith(prefix) and not item.disabled}
    groups=[("Bediening",("climate_main","dhw_water_heater","control_enabled","curve_status","curve_advised_target")),
            ("Temperaturen en debiet",("outdoor_temperature","water_inlet_temperature","water_outlet_temperature",
                "water_flow_calibrated","water_delta_temperature","dhw_temperature")),
            ("Vermogen en energie",("selected_electrical_power","thermal_power_estimated","electrical_energy_total",
                "thermal_power_hydraulic_estimated","thermal_power_external_reported",
                "thermal_energy_delivered","thermal_energy_extracted","thermal_energy_net")),
            ("Rendement en meetdekking",("monitoring_status","cop_instant","cop_day","cop_month","cop_7d","cop_365d",
                "cop_coverage_day","cop_coverage_month","eer_day","eer_coverage_day")),
            ("Compressor en storingen",("compressor_active","compressor_frequency","compressor_starts_day",
                "compressor_runtime_day","compressor_cycle_average","alarm","defrost","circulation_pump_active"))]
    sections=[]
    for title,keys in groups:
        cards=[{"type":"heading","heading":title}]
        cards.extend({"type":"tile","entity":entities[key]} for key in keys if key in entities)
        if len(cards)>1:
            sections.append({"type":"grid","cards":cards})
    history=[entities[k] for k in ("water_inlet_temperature","water_outlet_temperature","selected_electrical_power",
                                  "thermal_power_estimated","compressor_frequency") if k in entities]
    if history:
        sections.append({"type":"grid","cards":[{"type":"history-graph","title":"Verloop laatste 24 uur",
                          "hours_to_show":24,"entities":history}]})
    return {"title":entry.title,"views":[{"title":"HouseHeating","path":"overzicht","type":"sections",
                                          "max_columns":3,"sections":sections}]}


def async_register_dashboard_service(hass):
    async def generate(call):
        entry=hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain!=DOMAIN:
            raise ServiceValidationError("Select a HouseHeating config entry")
        # Return a fresh document for a user-created dashboard. No direct storage
        # mutation, internal Lovelace collection access or overwrite of custom work.
        return {"dashboard":dashboard_config(hass,entry)}
    async_register_admin_service(hass,DOMAIN,"generate_dashboard",generate,
        vol.Schema({vol.Required("entry_id"):str}),supports_response=SupportsResponse.ONLY)
