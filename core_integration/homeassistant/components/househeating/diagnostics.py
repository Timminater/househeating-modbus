"""Redacted diagnostics for field validation."""
from dataclasses import asdict
from househeating_modbus import __version__ as library_version


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    device = coordinator.device
    snapshot = device.snapshot
    result = {
        "library_version": library_version,
        "transport": entry.data["transport"],
        "configuration": asdict(device.config),
        "last_update_success": coordinator.last_update_success,
        "control_enabled": device.control_ready,
        "identity": asdict(snapshot.identity) if snapshot.identity else None,
        "registers": {f"0x{k:04X}": v for k, v in sorted(snapshot.raw.items())},
        "errors": dict(snapshot.errors),
        "last_write": device.last_write,
        "last_sample": snapshot.timestamp,
        "last_optional_sample": snapshot.optional_timestamp,
        "sample_windows": {f"0x{a:04X}": asdict(w) for a, w in snapshot.samples.items()},
    }
    if coordinator.monitoring is not None:
        result["monitoring"] = coordinator.monitoring.diagnostics()
    if coordinator.operation is not None:
        result["operation"] = coordinator.operation.diagnostics()
    secrets = [str(entry.data[k]) for k in ("host", "serial_device") if entry.data.get(k)]

    def redact(value):
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "**REDACTED**")
            return value
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [redact(v) for v in value]
        return value
    return redact(result)
