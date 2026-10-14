"""HouseHeating/SolarEast register protocol over a supplied ModbusUnit.

The caller owns the connection. This module never opens or closes a transport,
never writes at startup, and never sends service/factory commands.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from math import isfinite
from time import monotonic, time
from typing import TYPE_CHECKING

from .models import CommunicationError, DeviceConfig, Identity, ReadWindow, Snapshot, VerificationError, WriteRejected
from .registers import BY_KEY, SELECTS, SETPOINT_KEYS, WRITABLE_KEYS

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

CORE_BLOCKS = ((0x0000, 10), (0x0040, 17), (0x0300, 8))
FAST_OPTIONAL_BLOCKS = (("extra", 0x0051, 13), ("io", 0x0019, 8))
EXTENDED_BLOCKS = (("zones", 0x0072, 12), ("dhw_config", 0x0130, 1),
                   ("temperature_control", 0x0174, 1))
IDENTITY_BLOCK = (0x0360, 4)
CURVE_BLOCK = (0x0313, 4)


class HeatPump:
    """Device-specific protocol and safety boundary, using backend-neutral I/O."""

    def __init__(self, unit: ModbusUnit, config: DeviceConfig | None = None,
                 *, authorized_identity: tuple[int, int, int, int] | None = None) -> None:
        self.unit = unit
        self.config = config or DeviceConfig()
        self.authorized_identity = authorized_identity
        self.snapshot = Snapshot()
        self._lock = asyncio.Lock()
        self._slow_at = 0.0
        self._slow_raw: dict[int, int] = {}
        self._slow_errors: dict[str, str] = {}
        self._slow_samples: dict[int, ReadWindow] = {}
        self.last_write: dict[str, str | int | float] | None = None
        # These requirements participate in the SHARED connection's arbitration.
        unit.set_message_spacing(self.config.spacing)
        unit.require_timeout(self.config.timeout)

    @property
    def control_ready(self) -> bool:
        identity = self.snapshot.identity
        return (self.authorized_identity is not None and identity is not None
                and identity.fingerprint == self.authorized_identity
                and self.snapshot.layout_valid)

    def invalidate_optional(self) -> None:
        """Force fresh optional data after a lost connection."""
        self._slow_at = 0
        self._slow_raw = {}
        self._slow_errors = {}
        self._slow_samples = {}

    async def _read(self, address: int, count: int) -> dict[int, int]:
        result: dict[int, int] = {}
        for offset in range(0, count, self.config.max_read):
            length = min(self.config.max_read, count - offset)
            try:
                values = await self.unit.read_holding_registers(address + offset, length)
            except Exception as err:
                # Normalize errors at this external-I/O boundary only.
                # CancelledError inherits BaseException and is intentionally not swallowed.
                raise CommunicationError(f"Read 0x{address + offset:04X}, count {length}: {err}") from err
            if (not isinstance(values, (list, tuple)) or len(values) != length
                    or any(type(v) is not int or not 0 <= v <= 65535 for v in values)):
                raise CommunicationError(f"Invalid response for 0x{address + offset:04X}")
            result.update({address + offset + i: value for i, value in enumerate(values)})
        return result

    async def async_update(self, *, force_optional: bool = False, telemetry_enabled: bool = False,
                           diagnostics_enabled: bool = False) -> Snapshot:
        """Read mandatory data atomically; optional failures never reuse old values."""
        async with self._lock:
            raw: dict[int, int] = {}
            samples: dict[int, ReadWindow] = {}
            async def read(address, count, sample_target=samples):
                start = time()
                values = await self._read(address, count)
                window = ReadWindow(start, time(), monotonic())
                sample_target.update({a: window for a in values})
                return values
            try:
                for address, count in CORE_BLOCKS:
                    raw.update(await read(address, count))
            except CommunicationError:
                self.invalidate_optional()
                raise
            errors: dict[str, str] = {}
            try:
                raw.update(await read(*IDENTITY_BLOCK))
            except CommunicationError as err:
                errors["identity"] = str(err)
            identity = Identity.from_raw(raw)
            if self.snapshot.identity != identity:
                self.invalidate_optional()
            due = force_optional or not self._slow_at or monotonic() - self._slow_at >= self.config.slow_interval
            if due:
                optional: dict[int, int] = {}
                optional_errors: dict[str, str] = {}
                optional_samples: dict[int, ReadWindow] = {}
                blocks = list(EXTENDED_BLOCKS) if self.config.extended else []
                if self.config.curves and identity is not None and identity.protocol >= 130:
                    blocks.append(("curves", *CURVE_BLOCK))
                for name, address, count in blocks:
                    try:
                        optional.update(await read(address, count, optional_samples))
                    except CommunicationError as err:
                        optional_errors[name] = str(err)
                self._slow_raw, self._slow_errors = optional, optional_errors
                self._slow_samples = optional_samples
                self._slow_at = monotonic()
                optional_timestamp = time()
            else:
                optional_timestamp = self.snapshot.optional_timestamp
            raw.update(self._slow_raw)
            samples.update(self._slow_samples)
            errors.update(self._slow_errors)
            # Read frequently changing optional measurements on every scan, without
            # making unsupported extras fatal to the mandatory polling cycle.
            if self.config.extended:
                for name, address, count in FAST_OPTIONAL_BLOCKS:
                    try:
                        raw.update(await read(address, count))
                    except CommunicationError as err:
                        errors[name] = str(err)
            if telemetry_enabled:
                for address in (0x58, 0x5C, 0x5D):
                    if address not in raw:
                        try:
                            raw.update(await read(address, 1))
                        except CommunicationError as err:
                            errors[f"telemetry_{address:04x}"] = str(err)
            if diagnostics_enabled:
                for address in (0x19,0x1A):
                    if address not in raw:
                        try:
                            raw.update(await read(address,1))
                        except CommunicationError as err:
                            errors[f"diagnostics_{address:04x}"]=str(err)
            self.snapshot = Snapshot(raw, errors, time(), optional_timestamp, samples)
            return self.snapshot

    def validate_for_control(self, snapshot: Snapshot | None = None) -> Identity:
        """Check the documented layout and setpoint scaling before authorizing writes."""
        snapshot = snapshot or self.snapshot
        if not snapshot.layout_valid:
            raise WriteRejected("Unrecognized mode, on/off or profile register values")
        identity = snapshot.identity
        if identity is None:
            raise WriteRejected("A valid firmware/protocol identity is required for control")
        for key in SETPOINT_KEYS:
            if snapshot.value(key, self.config) is None:
                raise WriteRejected(f"{key} is outside the documented range; verify the temperature divisor")
        for key in ("water_inlet_temperature", "water_outlet_temperature", "outdoor_temperature"):
            if snapshot.value(key, self.config) is None:
                raise WriteRejected(f"{key} is invalid or its sensor has a fault")
        return identity

    def _encode(self, key: str, value: float | int | str | bool) -> int:
        if key not in WRITABLE_KEYS:
            raise WriteRejected(f"Register is not in the control allowlist: {key}")
        if key == "power":
            if isinstance(value, bool):
                return int(value)
            if type(value) is int and value in (0, 1):
                return value
            raise WriteRejected("Power must be a boolean or integer 0/1")
        if key in SELECTS:
            if not isinstance(value, str) or value not in SELECTS[key]:
                raise WriteRejected(f"Unsupported option for {key}: {value}")
            return SELECTS[key][value]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
            raise WriteRejected("A finite numeric temperature is required")
        low, high = self.config.limits(key)
        if not low <= value <= high:
            raise WriteRejected(f"{key} must be within {low}..{high} °C")
        if abs(value - round(value)) > 1e-6:
            raise WriteRejected("This version accepts whole-degree setpoints only")
        return int(round(value * self.config.setpoint_divisor))

    async def async_write(self, key: str, value: float | int | str | bool) -> None:
        """Validate, write ONCE using FC06, then verify without retrying the write."""
        encoded = self._encode(key, value)
        if key.endswith("_curve") and not self.config.curves:
            raise WriteRejected("Curve control is disabled in this configuration")
        if self.authorized_identity is None:
            raise WriteRejected("Control is locked; complete the commissioning confirmation first")
        async with self._lock:
            fresh_identity = Identity.from_raw(await self._read(*IDENTITY_BLOCK))
            if fresh_identity is None or fresh_identity.fingerprint != self.authorized_identity:
                self.authorized_identity = None
                raise WriteRejected("Firmware/protocol identity changed; control has been locked")
            if key.endswith("_curve") and fresh_identity.protocol < 130:
                raise WriteRejected("Individual curve registers require protocol version 130 or later")
            address = BY_KEY[key].address
            current = (await self._read(address, 1))[address]
            # A fresh setpoint sanity check blocks a wrong scaling factor even after setup.
            if key in SETPOINT_KEYS:
                if Snapshot({address: current}).value(key, self.config) is None:
                    raise WriteRejected("Current setpoint does not match the configured scaling")
            if key in SELECTS and current not in SELECTS[key].values():
                raise WriteRejected("Current selector value is not documented; refusing to overwrite it")
            if key == "power" and current not in (0, 1):
                raise WriteRejected("Current power register is not a documented 0/1 value")
            if current == encoded:
                self._accept_readback(address, current)
                self.last_write = {"key": key, "raw": encoded, "result": "unchanged", "time": time()}
                return
            self.last_write = {"key": key, "raw": encoded, "result": "unconfirmed", "time": time()}
            try:
                await self.unit.write_register(address, encoded)
            except Exception as err:
                raise VerificationError("Write acknowledgement failed; command may have reached the device. Read its state before retrying.") from err
            actual: int | None = None
            for _ in range(3):
                await asyncio.sleep(self.config.verify_delay)
                try:
                    actual = (await self._read(address, 1))[address]
                except CommunicationError:
                    continue
                if actual == encoded:
                    self._accept_readback(address, actual)
                    self.last_write["result"] = "verified"
                    return
            raise VerificationError(f"Readback mismatch for {key}: requested {encoded}, received {actual}; no automatic rewrite performed")

    def _accept_readback(self, address: int, actual: int) -> None:
        """Adopt an observed value, including an externally changed idempotent target."""
        updated = dict(self.snapshot.raw)
        updated[address] = actual
        self.snapshot = replace(self.snapshot, raw=updated)
        if address in self._slow_raw:
            self._slow_raw[address] = actual
