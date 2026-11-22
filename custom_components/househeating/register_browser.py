"""Serve the read-only HouseHeating register panel to administrators."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import voluptuous as vol
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from ._vendor.househeating_modbus import BINARY_FLAGS, CommunicationError
from ._vendor.househeating_modbus.models import decode
from ._vendor.househeating_modbus.operation import INPUT_FLAGS, RELAY_FLAGS
from ._vendor.househeating_modbus.registers import BY_ADDRESS, FAULT_LABELS, WRITABLE_ADDRESSES
from .const import DOMAIN, REGISTER_PANEL_PATH

SCRIPT_PATH = Path(__file__).with_name("register_browser.js")
CATALOG_KEY = f"{DOMAIN}_register_catalog"
ENTITY_REGISTERS = {
    **{register.key: (address, None) for address, register in BY_ADDRESS.items()},
    **BINARY_FLAGS,
    **RELAY_FLAGS,
    **INPUT_FLAGS,
    **{
        f"fault_{address:04x}_{label}": (address, bit)
        for address, bits in FAULT_LABELS.items()
        for bit, label in bits.items()
    },
}


def _load_assets():
    catalog = json.loads(Path(__file__).with_name("register_catalog.json").read_text(encoding="utf-8"))
    revision = sha256(SCRIPT_PATH.read_bytes()).hexdigest()[:16]
    return catalog, revision


async def async_register_browser(hass):
    catalog, revision = await hass.async_add_executor_job(_load_assets)
    script_url = f"/househeating_static/register_browser-{revision}.js"
    readable = frozenset(address for address, _, bit, *_, allowed in catalog if bit is None and allowed)
    hass.data[CATALOG_KEY] = (catalog, readable)
    await hass.http.async_register_static_paths([StaticPathConfig(script_url, str(SCRIPT_PATH), False)])
    for command in (ws_catalog, ws_snapshot, ws_read):
        websocket_api.async_register_command(hass, command)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=REGISTER_PANEL_PATH,
        webcomponent_name=f"househeating-register-browser-{revision}",
        module_url=script_url,
        require_admin=True,
    )


def _loaded_entry(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED:
        return entry
    return None


def _value(device, address, raw, timestamp, snapshot, *, on_demand=False):
    register = BY_ADDRESS.get(address)
    decoded = None
    if register and register.kind not in ("raw", "bitfield"):
        values = {**snapshot.raw, address: raw} if on_demand else snapshot.raw
        decoded = decode(register, values, device.config)
    return {
        "raw": raw,
        "value": decoded,
        "unit": register.unit if register else None,
        "checked": bool(register and register.kind not in ("raw", "bitfield")),
        "at": timestamp,
        "source": "manual" if on_demand else "poll",
    }


def _register_entities(hass, entry_id):
    registry = er.async_get(hass)
    prefix = f"{entry_id}_"
    result = {}
    for item in er.async_entries_for_config_entry(registry, entry_id):
        if item.platform != DOMAIN or not item.unique_id.startswith(prefix):
            continue
        location = ENTITY_REGISTERS.get(item.unique_id[len(prefix) :])
        if location is None:
            continue
        address, bit = location
        key = str(address) if bit is None else f"{address}:{bit}"
        result.setdefault(key, []).append(
            {"id": item.entity_id, "name": item.name or item.original_name, "enabled": not item.disabled}
        )
    return result


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "househeating/register_browser/catalog"})
@callback
def ws_catalog(hass, connection, msg):
    catalog, _ = hass.data[CATALOG_KEY]
    connection.send_result(msg["id"], {"rows": catalog, "writable": sorted(WRITABLE_ADDRESSES)})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "househeating/register_browser/snapshot", vol.Optional("entry_id"): str}
)
@callback
def ws_snapshot(hass, connection, msg):
    entries = [entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.state is ConfigEntryState.LOADED]
    result = {"devices": [{"id": entry.entry_id, "name": entry.title} for entry in entries], "samples": {}}
    entry_id = msg.get("entry_id", entries[0].entry_id if entries else None)
    entry = next((entry for entry in entries if entry.entry_id == entry_id), None)
    if entry:
        coordinator = entry.runtime_data
        device = coordinator.device
        snapshot = device.snapshot
        result.update(
            entry_id=entry.entry_id,
            online=coordinator.last_update_success and device.unit.connected,
            protocol=snapshot.identity.protocol if snapshot.identity else None,
            samples={
                address: _value(device, address, raw, snapshot.samples[address].end, snapshot)
                for address, raw in snapshot.raw.items()
                if address in snapshot.samples
            },
            has_errors=bool(snapshot.errors),
            entities=_register_entities(hass, entry.entry_id),
        )
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "househeating/register_browser/read",
        vol.Required("entry_id"): str,
        vol.Required("address"): vol.All(int, vol.Range(min=0, max=0xFFFF)),
    }
)
@websocket_api.async_response
async def ws_read(hass, connection, msg):
    entry = _loaded_entry(hass, msg["entry_id"])
    if not entry:
        connection.send_error(msg["id"], "not_loaded", "HouseHeating entry is not loaded")
        return
    address = msg["address"]
    _, readable = hass.data[CATALOG_KEY]
    if type(address) is not int or address not in readable:
        connection.send_error(
            msg["id"], "not_documented", "Address is not an individually documented readable register"
        )
        return
    device = entry.runtime_data.device
    coil = 0x1000 <= address <= 0x10FF
    identity = device.snapshot.identity
    if coil and (identity is None or identity.protocol < 130):
        connection.send_error(msg["id"], "unsupported_protocol", "Reading coils requires protocol 130 or newer")
        return
    try:
        raw, at = await device.async_read_register(address, coil=coil)
    except CommunicationError:
        connection.send_error(msg["id"], "read_failed", "The Modbus read failed or the firmware did not answer")
        return
    connection.send_result(msg["id"], _value(device, address, raw, at, device.snapshot, on_demand=True))
