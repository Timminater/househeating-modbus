# househeating-modbus 0.4.0

Backend-neutral protocol library for the HouseHeating HH-C3-12 / related SolarEast R290 family. This is an experimental, document-based implementation, not a manufacturer-certified driver. Physical-device validation is pending.

## Design

A caller supplies a `modbus_connection.ModbusUnit`. The library owns device-specific register knowledge and nothing about the transport lifetime. It neither creates nor closes the caller's connection. It requests bus quiet time through `set_message_spacing()` and a request timeout through `require_timeout()`.

`registers.py` contains declarative register descriptions; `models.py` contains typed configuration, identity and snapshot models; `device.py` handles grouped reads and verified writes. This version uses the public raw-register `ModbusUnit` API with its own explicit data models, not the optional `modbus_connection.model.Component` descriptor engine. This allows independent measurement and setpoint scaling and a narrow, auditable write allowlist. No backend-specific client appears in the device implementation.

The register source is the supplied **R290 HouseHeating technical manual**, PDF pages 163–169 and 184–187. The manufacturer PDF is not distributed here. The model name identifies the documentation target; the generic version registers do not prove the manufacturer or uniquely identify a physical unit.

## Install and read

This package has not been published to PyPI. Install from this directory:

```sh
python -m pip install '.[cli]'
househeating-read --transport rtu_tcp --host 192.0.2.10 --port 502 --unit 1
```

Use `--transport tcp` for MBAP/Modbus TCP, or `--transport serial --device /dev/serial/by-id/...` for a local RS485 adapter. The device side is 9600 baud, 8N1, RTU. For a transparent gateway, UART settings must be configured on the gateway; the serial socket's internal baud-rate setting does not configure the remote UART. Do not run this probe concurrently with an independent master on the same device bus.

The CLI is deliberately read-only. The example IP is a documentation address, not a real device address.

## Programmatic use

```python
from househeating_modbus import DeviceConfig, HeatPump

# unit is a ModbusUnit supplied by your application.
device = HeatPump(unit, DeviceConfig())
snapshot = await device.async_update()
print(snapshot.value("water_outlet_temperature", device.config))
```

Default temperature encoding is signed 16-bit / 10. Measurement and setpoint divisors can independently be 1 or 10 after physical verification. A plausible value alone is not sufficient to establish correct scaling.

After an operator checks the measurements, setpoints, installation, and identity, an application can pass the verified fingerprint as `authorized_identity` when constructing the driver. `validate_for_control()` checks plausibility; it does **not** replace the operator's physical comparison. Writes check the current version registers, enforce the documented allowlist and configured ceilings, issue one FC06 request, and read back up to three times. An acknowledgement failure or mismatch is not automatically resent.

## Scope

Read-only state, fault words, temperatures, compressor frequency, selected electrical measurements, optional extended register groups and version registers. Controls are on/off, exact operating mode, standard/powerful/silent profile, four temperature setpoints and native curves for protocol >= 130.

No service commands, reset, forced compressor operation, forced defrost, raw-write API, virtual sensor injection, or external optimization loop. The device energy counter is not declared a validated monotonic total. Optional read-only telemetry calculates thermal estimates and paired energy ratios after explicit hydraulic scale confirmation; see [ENERGIEMONITORING.md](../ENERGIEMONITORING.md). Water flow is documented in L/min, with firmware scaling still requiring physical confirmation.

## Tests

```sh
python -m pip install '.[test]'
python -m pytest -q tests
```

Tests use an in-memory unit double and exercise the driver's logic. They do not test UART electrical behavior, Modbus wire framing, gateway firmware or actual heat-pump operation.
