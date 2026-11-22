"""Descriptions and stable identifiers for optional register diagnostics."""

from dataclasses import dataclass
from typing import NamedTuple

from ._vendor.househeating_modbus import BINARY_FLAGS
from ._vendor.househeating_modbus.operation import INPUT_FLAGS, RELAY_FLAGS
from ._vendor.househeating_modbus.registers import BY_ADDRESS, FAULT_LABELS
from .const import DOMAIN

CATALOG_KEY = f"{DOMAIN}_register_catalog"
CATALOG_SCALES = {0x62: ("V", 1), 0x63: ("A", 10), 0x64: ("A", 10)}

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


class CatalogRow(NamedTuple):
    address: int
    end: int
    bit: int | None
    group: str
    name: str
    access: str
    page: int
    detail: str
    readable: bool


@dataclass(frozen=True)
class CatalogRegister:
    row: CatalogRow
    subdevice: str
    unit: str | None = None
    divisor: int = 1

    @property
    def key(self) -> str:
        prefix = f"catalog_{self.row.address:04x}"
        return prefix if self.row.bit is None else f"{prefix}_bit_{self.row.bit}"

    @property
    def is_binary(self) -> bool:
        return self.row.bit is not None or 0x1000 <= self.row.address <= 0x10FF


def _subdevice(row: CatalogRow) -> str:
    address = row.address
    name = row.name.casefold()
    if 0x19 <= address <= 0x20:
        return "io"
    if address in (0x62, 0x63):
        return "energy"
    if address in (0x27, 0x28) or 0x5E <= address <= 0x6D:
        return "compressor"
    if "foutstatus" in name or 0x02 <= address <= 0x18 or 0x360 <= address <= 0x363:
        return "register_diagnostics"
    if any(term in name for term in ("sterilisati", "warmwater", "warm water", "dhw", "boiler", "tapwater")):
        return "domestic_hot_water"
    if any(term in name for term in ("pwm", "waterstroom", "waterpomp", "mengklep", "vloerverwarming", "buffervat")):
        return "water_circuit"
    if any(term in name for term in ("compressor", "koudemiddel", "systeemolieretour", "ontdooien")):
        return "compressor"
    return "register_diagnostics"


def catalog_registers(rows: list[CatalogRow]) -> dict[str, CatalogRegister]:
    existing = set(ENTITY_REGISTERS.values())
    registers = {}
    for row in rows:
        if not row.readable or row.address != row.end or (row.address, row.bit) in existing:
            continue
        unit, divisor = CATALOG_SCALES.get(row.address, (None, 1)) if row.bit is None else (None, 1)
        register = CatalogRegister(row, _subdevice(row), unit, divisor)
        registers[register.key] = register
    return registers
