"""Documented register map; addresses are zero-based wire addresses.

Source: R290 HouseHeating technical manual, PDF pages 163-169 and 184-187.
No definitions or implementation are copied from third-party heat-pump projects.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum


class OperatingMode(IntEnum):
    COOLING = 0
    HEATING = 1
    HOT_WATER = 2
    FLOOR_HEATING = 3
    HOT_WATER_COOLING = 4
    HOT_WATER_HEATING = 5
    HOT_WATER_FLOOR_HEATING = 7


MODE_OPTIONS = {mode.name.lower(): int(mode) for mode in OperatingMode}
PROFILE_OPTIONS = {"standard": 0, "powerful": 1, "silent": 2}
CURVE_OPTIONS = {"off": 0, **{f"high_{n}": n for n in range(1, 9)},
                 **{f"low_{n}": n + 10 for n in range(1, 9)}}
DHW_CURVE_OPTIONS = {"off": 0, **{f"curve_{n}": n for n in range(1, 5)}}


@dataclass(frozen=True, kw_only=True)
class Register:
    key: str
    address: int
    name: str
    page: int
    unit: str | None = None
    device_class: str | None = None
    kind: str = "integer"
    factor: float = 1.0
    minimum: float | None = None
    maximum: float | None = None
    default_enabled: bool = False
    diagnostic: bool = True
    group: str = "core"
    # A known sensor-fault bit suppresses its measurement, not its raw diagnostic.
    fault: tuple[int, int] | None = None


def temp(key: str, address: int, name: str, *, page: int = 167,
         enabled: bool = False, group: str = "core",
         fault: tuple[int, int] | None = None, maximum: float = 150) -> Register:
    return Register(key=key, address=address, name=name, page=page, unit="°C",
                    device_class="temperature", kind="temperature", minimum=-50,
                    maximum=maximum, default_enabled=enabled, diagnostic=False,
                    group=group, fault=fault)


REGISTERS: tuple[Register, ...] = (
    *(Register(key=f"status_{n + 1}", address=n, name=f"Running status {n + 1}",
               page=166, kind="bitfield") for n in range(2)),
    *(Register(key=f"fault_word_{n}", address=n, name=f"Fault word 0x{n:04X}",
               page=166, kind="bitfield") for n in range(2, 10)),
    Register(key="compressor_frequency", address=0x0040, name="Compressor frequency",
             page=167, unit="Hz", device_class="frequency", minimum=0, maximum=150,
             default_enabled=True, diagnostic=False),
    Register(key="fan_raw", address=0x0041, name="Fan speed (raw)", page=167,
             kind="raw"),
    Register(key="eev_steps", address=0x0042, name="Expansion valve steps", page=167),
    Register(key="evi_steps", address=0x0043, name="EVI valve steps", page=167),
    Register(key="ac_voltage", address=0x0044, name="AC input voltage", page=167,
             unit="V", device_class="voltage", minimum=0, maximum=600),
    Register(key="ac_current", address=0x0045, name="AC input current", page=167,
             unit="A", device_class="current", factor=0.1, minimum=0, maximum=200),
    Register(key="compressor_current", address=0x0046, name="Compressor phase current",
             page=167, unit="A", device_class="current", factor=0.1, minimum=0, maximum=200),
    temp("ipm_temperature", 0x0047, "Compressor IPM temperature"),
    temp("high_pressure_saturation_temperature", 0x0048, "High-pressure saturation temperature"),
    temp("low_pressure_saturation_temperature", 0x0049, "Low-pressure saturation temperature"),
    temp("outdoor_temperature", 0x004A, "Outdoor temperature", enabled=True, fault=(2, 9)),
    temp("outdoor_coil_temperature", 0x004B, "Outdoor coil temperature"),
    temp("indoor_coil_temperature", 0x004C, "Indoor coil temperature"),
    temp("suction_temperature", 0x004D, "Suction temperature"),
    temp("discharge_temperature", 0x004E, "Discharge temperature", maximum=180),
    temp("water_inlet_temperature", 0x004F, "Water inlet temperature", enabled=True, fault=(2, 7)),
    temp("water_outlet_temperature", 0x0050, "Water outlet temperature", enabled=True, fault=(2, 13)),
    temp("economizer_inlet_temperature", 0x0051, "Economizer inlet temperature", group="extended"),
    temp("economizer_outlet_temperature", 0x0052, "Economizer outlet temperature", group="extended"),
    temp("dhw_temperature", 0x0054, "Hot-water tank temperature", group="extended", fault=(2, 6)),
    temp("plate_temperature", 0x0055, "Plate heat exchanger temperature", group="extended", fault=(4, 2)),
    Register(key="pump_pwm", address=0x0057, name="Water pump PWM", page=167,
             unit="%", minimum=0, maximum=100, group="extended"),
    # Operating parameter 25 (PDF p160) establishes L/min; Modbus p167 says actual value.
    # Keep the original key so existing entity identities remain stable.
    Register(key="flow_raw", address=0x0058, name="Water flow", page=167,
             group="fast", unit="L/min", device_class="volume_flow_rate", minimum=0, maximum=100),
    temp("dhw_return_temperature", 0x0059, "Hot-water circulation return temperature",
         group="extended", fault=(2, 10)),
    Register(key="unit_voltage", address=0x005A, name="Unit input voltage", page=167,
             unit="V", device_class="voltage", minimum=0, maximum=600, group="extended"),
    Register(key="unit_current", address=0x005B, name="Unit input current", page=167,
             unit="A", device_class="current", factor=0.01, minimum=0, maximum=200,
             group="extended"),
    Register(key="input_power", address=0x005C, name="Reported electrical input power",
             page=167, unit="kW", device_class="power", factor=0.01,
             minimum=0, maximum=30, group="extended"),
    # No total_increasing classification: reset, overflow and accuracy unverified.
    # Monitoring deliberately uses power integration or an explicit external meter,
    # never this unverified counter as its primary energy source.
    Register(key="reported_energy", address=0x005D, name="Reported electrical energy",
             page=167, unit="kWh", device_class="energy", kind="counter", group="extended"),
    temp("solar_temperature", 0x0072, "Solar-water temperature", page=168, group="extended", fault=(4, 6)),
    temp("zone_2_temperature", 0x0073, "Zone 2 temperature", page=168, group="extended"),
    temp("buffer_temperature", 0x0074, "Buffer temperature", page=168, group="extended", fault=(4, 8)),
    temp("total_outlet_temperature", 0x0075, "Total outlet temperature", page=168, group="extended", fault=(4, 9)),
    Register(key="phase_b_voltage", address=0x0076, name="Phase B voltage", page=168,
             unit="V", device_class="voltage", minimum=0, maximum=600, group="extended"),
    Register(key="phase_b_current", address=0x0077, name="Phase B current", page=168,
             unit="A", device_class="current", factor=0.01, minimum=0, maximum=200, group="extended"),
    Register(key="phase_c_voltage", address=0x0078, name="Phase C voltage", page=168,
             unit="V", device_class="voltage", minimum=0, maximum=600, group="extended"),
    Register(key="phase_c_current", address=0x0079, name="Phase C current", page=168,
             unit="A", device_class="current", factor=0.01, minimum=0, maximum=200, group="extended"),
    Register(key="smart_grid_raw", address=0x007A, name="Smart-grid status (raw)", page=168,
             group="extended", kind="raw"),
    Register(key="mixing_valve_zone_2_raw", address=0x007B, name="Zone 2 mixing valve (raw)",
             page=168, group="extended", kind="raw"),
    temp("zone_1_temperature", 0x007C, "Zone 1 mixed temperature", page=168,
         group="extended", fault=(4, 12)),
    Register(key="mixing_valve_zone_1_raw", address=0x007D, name="Zone 1 mixing valve (raw)",
             page=168, group="extended", kind="raw"),
    *(Register(key=f"io_word_{n:04x}", address=n, name=f"I/O word 0x{n:04X}",
               page=166, group="extended", kind="bitfield") for n in range(0x19, 0x21)),
    Register(key="dhw_sensor_enabled", address=0x0130, name="Hot-water sensor enabled", page=177,
             kind="enum", group="config"),
    Register(key="temperature_control_mode", address=0x0174, name="Water temperature control mode", page=179,
             kind="enum", group="config"),
    *(Register(key=key, address=address, name=name, page=184, unit="°C",
               device_class="temperature", kind="setpoint", minimum=lo, maximum=hi,
               default_enabled=True, diagnostic=False)
      for key, address, name, lo, hi in (
          ("cooling_setpoint", 0x0300, "Cooling setpoint", 7, 25),
          ("heating_setpoint", 0x0301, "Heating setpoint", 20, 60),
          ("dhw_setpoint", 0x0302, "Hot-water setpoint", 20, 75),
          ("floor_setpoint", 0x0303, "Floor-heating setpoint", 20, 60))),
    Register(key="operating_mode", address=0x0304, name="Operating mode", page=185,
             kind="enum", default_enabled=True, diagnostic=False),
    Register(key="power", address=0x0305, name="Power command", page=185,
             kind="enum", diagnostic=False),
    Register(key="indoor_setpoint_raw", address=0x0306, name="Indoor setpoint (raw)",
             page=185, kind="raw"),
    Register(key="operating_profile", address=0x0307, name="Operating profile", page=185,
             kind="enum", default_enabled=True, diagnostic=False),
    *(Register(key=key, address=addr, name=name, page=185, kind="enum", group="curves")
      for key, addr, name in (
          ("cooling_curve", 0x0313, "Cooling curve"),
          ("heating_curve", 0x0314, "Heating curve"),
          ("dhw_curve", 0x0315, "Hot-water curve"),
          ("floor_curve", 0x0316, "Floor-heating curve"))),
    *(Register(key=key, address=addr, name=name, page=187, kind="raw")
      for key, addr, name in (
          ("firmware_version", 0x0360, "Firmware version (raw)"),
          ("product_type", 0x0361, "Product type"),
          ("product_type_id", 0x0362, "Product type ID"),
          ("protocol_version", 0x0363, "Protocol version"))),
)
REGISTERS = tuple(replace(r, group="fast") if 0x51 <= r.address <= 0x5D or 0x19 <= r.address <= 0x20
                  else r for r in REGISTERS)
BY_KEY = {r.key: r for r in REGISTERS}
BY_ADDRESS = {r.address: r for r in REGISTERS}
SELECTS = {"operating_mode": MODE_OPTIONS, "operating_profile": PROFILE_OPTIONS,
           "cooling_curve": CURVE_OPTIONS, "heating_curve": CURVE_OPTIONS,
           "dhw_curve": DHW_CURVE_OPTIONS, "floor_curve": CURVE_OPTIONS}
SETPOINT_KEYS = ("cooling_setpoint", "heating_setpoint", "dhw_setpoint", "floor_setpoint")
WRITABLE_KEYS = frozenset((*SETPOINT_KEYS, *SELECTS, "power"))
# These are deliberately disjoint from service/factory command regions.
WRITABLE_ADDRESSES = frozenset(BY_KEY[key].address for key in WRITABLE_KEYS)

# Names are independent transcriptions of the supplied manufacturer's manual.
FAULT_LABELS: dict[int, dict[int, str]] = {
    2: {0: "wrong_phase", 1: "missing_phase", 2: "water_flow_fault",
        3: "communication_fault", 4: "emergency_fault", 5: "use_time_expired",
        6: "dhw_sensor_fault", 7: "inlet_sensor_fault", 8: "indoor_sensor_fault",
        9: "outdoor_sensor_fault", 10: "dhw_return_sensor_fault",
        11: "cooling_outlet_too_low", 12: "water_level_fault",
        13: "outlet_sensor_fault", 14: "heating_outlet_too_high",
        15: "water_temperature_difference_too_high"},
    3: {0: "outdoor_temperature_too_low", 6: "indoor_humidity_sensor_fault",
        11: "phase_dip_switch_fault", 13: "pump_1_fault", 14: "pump_2_fault",
        15: "low_water_flow"},
    4: {0: "phase_sequence_disconnected", 1: "expansion_board_communication_fault",
        2: "plate_sensor_fault", 3: "fan_1_communication_fault",
        4: "fan_2_communication_fault", 5: "cascade_model_mismatch",
        6: "solar_sensor_fault", 7: "auxiliary_heat_sensor_fault",
        8: "buffer_sensor_fault", 9: "total_outlet_sensor_fault",
        12: "zone_1_sensor_fault"},
}

# bit 8 is labelled 'Systeem Bevriezen' in this Dutch translation. The label
# 'defrost' should be checked against the controller during commissioning.
BINARY_FLAGS = {
    "running": (0, 14), "waiting": (0, 15), "alarm": (0, 3),
    "defrost": (0, 8), "antifreeze_stage_1": (0, 1),
    "antifreeze_stage_2": (0, 2), "target_reached": (0, 12),
    "fault_shutdown": (0, 13), "sterilization": (1, 0),
}
