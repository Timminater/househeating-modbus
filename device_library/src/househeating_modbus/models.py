"""Typed snapshots and validation, independent of any application or backend."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Mapping

from .registers import BY_KEY, FAULT_LABELS, MODE_OPTIONS, PROFILE_OPTIONS, Register


class HeatPumpError(Exception):
    """Base error for device operations."""


class CommunicationError(HeatPumpError):
    """A request failed or returned an invalid register payload."""


class WriteRejected(HeatPumpError):
    """A command was refused before transmission."""


class VerificationError(HeatPumpError):
    """A command was sent but could not be confirmed by readback."""


@dataclass(frozen=True)
class DeviceConfig:
    measurement_divisor: int = 10
    setpoint_divisor: int = 10
    max_read: int = 16
    spacing: float = 0.12
    timeout: float = 5.0
    extended: bool = True
    curves: bool = True
    slow_interval: float = 120.0
    max_heating: float = 60.0
    max_floor: float = 45.0
    max_dhw: float = 65.0
    verify_delay: float = 0.2

    def __post_init__(self) -> None:
        if (type(self.measurement_divisor) is not int or type(self.setpoint_divisor) is not int
                or self.measurement_divisor not in (1, 10) or self.setpoint_divisor not in (1, 10)):
            raise ValueError("Temperature divisors must be 1 or 10")
        if type(self.max_read) is not int or not 1 <= self.max_read <= 100:
            raise ValueError("max_read must be between 1 and 100")
        for name, lo, hi in (("spacing", .1, 5), ("timeout", 1, 30),
                             ("slow_interval", 10, 3600), ("max_heating", 20, 60),
                             ("max_floor", 20, 60), ("max_dhw", 20, 75),
                             ("verify_delay", 0, 5)):
            value = getattr(self, name)
            if not isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"{name} must be within {lo}..{hi}")

    def limits(self, key: str) -> tuple[float, float]:
        r = BY_KEY[key]
        assert r.minimum is not None and r.maximum is not None
        cap = {"heating_setpoint": self.max_heating, "floor_setpoint": self.max_floor,
               "dhw_setpoint": self.max_dhw}.get(key, r.maximum)
        return r.minimum, min(r.maximum, cap)


def signed16(value: int) -> int:
    return value - 65536 if value >= 32768 else value


def decode(register: Register, raw: Mapping[int, int], config: DeviceConfig) -> float | int | None:
    if register.address not in raw:
        return None
    if register.fault:
        address, bit = register.fault
        if raw.get(address, 0) & (1 << bit):
            return None
    value = raw[register.address]
    if register.kind in ("temperature", "setpoint"):
        # Do not treat 0xFFFF as missing: it can represent -0.1 °C.
        divisor = config.measurement_divisor if register.kind == "temperature" else config.setpoint_divisor
        result = signed16(value) / divisor
    else:
        result = value * register.factor
    if register.minimum is not None and result < register.minimum:
        return None
    if register.maximum is not None and result > register.maximum:
        return None
    if register.kind in ("integer", "raw", "bitfield", "enum", "counter") and register.factor == 1:
        return int(result)
    return round(float(result), 3)


@dataclass(frozen=True)
class Identity:
    firmware: int
    product_type: int
    product_type_id: int
    protocol: int

    @classmethod
    def from_raw(cls, raw: Mapping[int, int]) -> Identity | None:
        values = tuple(raw.get(a) for a in range(0x0360, 0x0364))
        if any(v is None or v == 65535 for v in values):
            return None
        firmware, product_type, product_type_id, protocol = values
        if not firmware or not 100 <= protocol <= 9999:
            return None
        return cls(firmware, product_type, product_type_id, protocol)

    @property
    def fingerprint(self) -> tuple[int, int, int, int]:
        return (self.firmware, self.product_type, self.product_type_id, self.protocol)

    @property
    def firmware_text(self) -> str:
        return f"{self.firmware // 100}.{self.firmware % 100:02d}"


@dataclass(frozen=True)
class ReadWindow:
    """Actual successful read interval; cached values retain their original time."""
    start: float
    end: float
    monotonic_end: float


@dataclass(frozen=True)
class Snapshot:
    raw: Mapping[int, int] = field(default_factory=dict)
    errors: Mapping[str, str] = field(default_factory=dict)
    timestamp: float = 0.0
    optional_timestamp: float = 0.0
    samples: Mapping[int, ReadWindow] = field(default_factory=dict)

    @property
    def identity(self) -> Identity | None:
        return Identity.from_raw(self.raw)

    def value(self, key: str, config: DeviceConfig) -> float | int | None:
        return decode(BY_KEY[key], self.raw, config)

    @property
    def layout_valid(self) -> bool:
        # A compatibility check, NOT a manufacturer or serial-number identity.
        return (self.raw.get(0x0304) in MODE_OPTIONS.values()
                and self.raw.get(0x0305) in (0, 1)
                and self.raw.get(0x0307) in PROFILE_OPTIONS.values())

    @property
    def faults(self) -> list[str]:
        output = []
        for address in range(2, 10):
            value = self.raw.get(address, 0)
            for bit in range(16):
                if value & (1 << bit):
                    output.append(FAULT_LABELS.get(address, {}).get(bit, f"word_{address:04x}_bit_{bit}"))
        return output
