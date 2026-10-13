"""Read-only command-line probe. No command-line write facility is provided."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from . import DeviceConfig, HeatPump


async def run(args) -> None:
    from modbus_connection import ModbusSerialParams, ModbusTcpParams
    from modbus_connection.tmodbus import ModbusConnection

    if args.transport == "serial":
        if not args.device:
            raise ValueError("--device is required for serial")
        params = ModbusSerialParams(device=args.device, baudrate=9600, bytesize=8,
                                    parity="N", stopbits=1, framer="rtu")
    else:
        if not args.host:
            raise ValueError("--host is required for a network connection")
        if args.transport == "tcp":
            params = ModbusTcpParams(host=args.host, port=args.port)
        else:
            host = args.host.strip("[]")
            host = f"[{host}]" if ":" in host else host
            params = ModbusSerialParams(device=f"socket://{host}:{args.port}", baudrate=115200)
    if not 1 <= args.unit <= 247:
        raise ValueError("Unit ID must be 1..247")
    connection = ModbusConnection(params)
    try:
        config = DeviceConfig(measurement_divisor=args.measurement_divisor,
                              setpoint_divisor=args.setpoint_divisor, extended=args.extended)
        device = HeatPump(connection.for_unit(args.unit), config)
        snapshot = await device.async_update()
        result = {"identity": asdict(snapshot.identity) if snapshot.identity else None,
                  "layout_valid": snapshot.layout_valid,
                  "raw": {f"0x{k:04X}": v for k, v in sorted(snapshot.raw.items())},
                  "errors": dict(snapshot.errors)}
        print(json.dumps(result, indent=2))
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("tcp", "rtu_tcp", "serial"), default="rtu_tcp")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--device")
    parser.add_argument("--unit", type=int, default=1)
    parser.add_argument("--measurement-divisor", type=int, choices=(1, 10), default=10)
    parser.add_argument("--setpoint-divisor", type=int, choices=(1, 10), default=10)
    parser.add_argument("--extended", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as err:
        parser.exit(1, f"Probe failed: {err}\n")


if __name__ == "__main__":
    main()
