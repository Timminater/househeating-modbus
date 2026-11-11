"""Pure plans for shared space-heating and hot-water modes (no I/O)."""

from .models import WriteRejected
from .registers import OperatingMode

DHW_MODES = frozenset((2, 4, 5, 7))
SPACE_MODES = {0: "cool", 1: "heat", 3: "floor_heating", 4: "cool", 5: "heat", 7: "floor_heating"}
SPACE_VALUES = {"cool": (0, 4), "heat": (1, 5), "floor_heating": (3, 7)}
HEATING_FAMILY = {1: 3, 5: 7, 3: 1, 7: 5}


def mode_command(mode):
    return ("operating_mode", OperatingMode(mode).name.lower())


def space_plan(raw, requested):
    """Retain ACTIVE hot water when changing the space mode; switch power on last.

    While the whole unit is off, hot water only remembered in the mode register
    is not active. Starting space heating/cooling then starts only that function.
    """
    mode, power = raw[0x304], raw[0x305]
    if requested == "off":
        if not power:
            return []
        return [mode_command(2)] if mode in DHW_MODES and mode != 2 else [] if mode == 2 else [("power", False)]
    if requested not in SPACE_VALUES:
        raise WriteRejected("Unsupported space-heating mode")
    target = SPACE_VALUES[requested][int(bool(power) and mode in DHW_MODES)]
    return ([mode_command(target)] if mode != target else []) + ([] if power else [("power", True)])


def dhw_plan(raw, enabled):
    """Retain ACTIVE space heating/cooling; never change the global power profile.

    While the whole unit is off, a space mode only remembered in the mode register
    is not active. Starting hot water then starts hot water only (mode 2).
    """
    mode, power = raw[0x304], raw[0x305]
    if not enabled:
        if mode == 2:
            return [("power", False)] if power else []
        target = {4: 0, 5: 1, 7: 3}.get(mode, mode)
        return [mode_command(target)] if mode != target else []
    target = {0: 4, 1: 5, 3: 7}.get(mode, mode) if power else 2
    return ([mode_command(target)] if mode != target else []) + ([] if power else [("power", True)])


def floor_plan(raw, enabled):
    """Choose floor heating or normal heating; keep power, hot water and profile."""
    mode = raw[0x304]
    if mode not in HEATING_FAMILY:
        raise WriteRejected("Floor heating can only be selected while the space mode is heating")
    floor = mode in (3, 7)
    if floor == enabled:
        return []
    return [mode_command(HEATING_FAMILY[mode])]
