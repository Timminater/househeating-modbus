"""Connection parameters only; Home Assistant owns and shares the transport."""
from __future__ import annotations

from typing import Any
from modbus_connection import ModbusSerialParams, ModbusTcpParams

from househeating_modbus import DeviceConfig
from .const import DEFAULT_OPTIONS


def normalize_connection(data: dict[str, Any]) -> dict[str, Any]:
    transport = data["transport"]
    if transport not in ("tcp", "rtu_tcp", "serial"):
        raise ValueError("Unknown transport")
    unit_id = int(data["unit_id"])
    if isinstance(data["unit_id"], bool) or float(data["unit_id"]) != unit_id or not 1 <= unit_id <= 247:
        raise ValueError("Unit ID must be between 1 and 247 (no broadcast)")
    result = {"name": str(data.get("name", "HouseHeating")).strip() or "HouseHeating",
              "transport": transport, "unit_id": unit_id}
    if transport == "serial":
        device = str(data.get("serial_device", "")).strip()
        if not device.startswith("/dev/"):
            raise ValueError("A /dev/ serial path is required")
        result["serial_device"] = device
    else:
        host = str(data.get("host", "")).strip().strip("[]")
        if not host or any(char.isspace() for char in host) or "/" in host:
            raise ValueError("Enter a hostname or IP address without a URL scheme")
        # Keep an IPv6 scope identifier case-sensitive, as modbus-connection does.
        address, separator, scope = host.partition("%")
        result["host"] = address.lower() + separator + scope
        port = int(data.get("port", 502))
        if isinstance(data.get("port"), bool) or float(data.get("port", 502)) != port or not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        result["port"] = port
    params = connection_params(result)
    result["connection_key"] = repr((*params.endpoint, unit_id))
    return result


def connection_params(data: dict[str, Any]) -> ModbusTcpParams | ModbusSerialParams:
    if data["transport"] == "tcp":
        return ModbusTcpParams(host=data["host"], port=data["port"])
    if data["transport"] == "rtu_tcp":
        host = data["host"]
        host = f"[{host}]" if ":" in host else host
        # An RTU frame carried over TCP is a serial socket transport, not MBAP.
        # Match Home Assistant's canonical RTU-over-TCP spelling.
        return ModbusSerialParams(device=f"socket://{host}:{data['port']}",
                                  baudrate=115200, framer="rtu")
    return ModbusSerialParams(device=data["serial_device"], baudrate=9600,
                              bytesize=8, parity="N", stopbits=1, framer="rtu")


def device_config(options: dict[str, Any]) -> DeviceConfig:
    o = DEFAULT_OPTIONS | dict(options)
    return DeviceConfig(measurement_divisor=int(o["measurement_divisor"]),
                        setpoint_divisor=int(o["setpoint_divisor"]),
                        max_read=int(o["max_read"]), spacing=float(o["spacing_ms"]) / 1000,
                        timeout=float(o["timeout"]), extended=bool(o["extended"]),
                        curves=bool(o["curves"]),
                        slow_interval=max(float(o["scan_interval"]), float(o["slow_interval"])),
                        max_heating=float(o["max_heating"]), max_floor=float(o["max_floor"]),
                        max_dhw=float(o["max_dhw"]))
