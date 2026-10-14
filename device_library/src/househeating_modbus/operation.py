"""Independent observed-operation accounting and optional weather compensation.

Derived from the HouseHeating manual and elementary interpolation; no third-party code.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from math import ceil, exp, floor, isfinite
from zoneinfo import ZoneInfo
from time import time, monotonic

from .telemetry import period_bounds

# PDF p173-174: 0x0019/0x001A relay outputs. Relay status is not proof of heat production.
RELAY_FLAGS = {
    "compressor_active": (0x1A, 0), "fan_active": (0x1A, 5),
    "circulation_pump_active": (0x19, 6), "dhw_heater_active": (0x19, 0),
    "space_heater_active": (0x19, 4), "floor_heater_active": (0x19, 5),
    "crankcase_heater_active": (0x19, 9), "chassis_heater_active": (0x19, 10),
    "return_pump_valve_active": (0x19, 11), "space_three_way_valve_active": (0x19, 14),
    "floor_three_way_valve_active": (0x19, 15), "four_way_valve_active": (0x1A, 3),
    "auxiliary_pump_active": (0x1A, 8),
}


def relay_value(snapshot,key,max_age=90):
    if snapshot is None:
        return None
    address,bit=RELAY_FLAGS[key]
    window=snapshot.samples.get(address)
    if window is None or not 0<=time()-window.end<=max_age or not 0<=monotonic()-window.monotonic_end<=max_age:
        return None
    value=snapshot.raw.get(address)
    return bool(value&(1<<bit)) if value is not None else None


class OperationLedger:
    """Only observed OFF->ON transitions and fully observed ON intervals count."""
    def __init__(self, timezone_name, max_age, state=None):
        self.zone = ZoneInfo(timezone_name)
        self.max_age = max_age
        self.starts = 0
        self.seconds = 0.0
        self.days = {}
        self.completed_cycles = 0
        self.completed_seconds = 0.0
        self.previous = None
        self.cycle_seconds = None
        if state:
            if state.get("version") != 1:
                raise ValueError("Unsupported operation ledger")
            for key in ("starts", "seconds", "completed_cycles", "completed_seconds"):
                value = state[key]
                if not isinstance(value, (int,float)) or not isfinite(value) or value < 0:
                    raise ValueError("Invalid observed-operation totals")
                setattr(self, key, value)
            self.days = state.get("days", {})

    def ingest(self, at, clock, running):
        old = self.previous
        continuous = old is not None and 0 < clock-old[1] <= self.max_age and abs((at-old[0])-(clock-old[1])) < 2
        if not continuous or running is None or old[2] is None:
            self.cycle_seconds = None
        if continuous and running is not None and old[2] is not None:
            if running and not old[2]:
                self.starts += 1
                self.days.setdefault(datetime.fromtimestamp(at,self.zone).date().isoformat(),[0,0.0])[0] += 1
                self.cycle_seconds = 0.0
            if old[2] and running:
                dt = at-old[0]
                self.seconds += dt
                if self.cycle_seconds is not None:
                    self.cycle_seconds += dt
                cursor = old[0]
                while cursor < at:
                    end = min(at,period_bounds(cursor,"day",self.zone)[1])
                    key = datetime.fromtimestamp(cursor,self.zone).date().isoformat()
                    self.days.setdefault(key,[0,0.0])[1] += end-cursor
                    cursor = end
            if old[2] and not running and self.cycle_seconds is not None:
                self.completed_cycles += 1
                self.completed_seconds += self.cycle_seconds
                self.cycle_seconds = None
        self.previous = (at,clock,running)
        self.days = dict(sorted(self.days.items())[-370:])

    def export(self):
        return {"version":1, "starts":self.starts, "seconds":self.seconds, "days":self.days,
                "completed_cycles":self.completed_cycles,"completed_seconds":self.completed_seconds}

    def values(self, at):
        today = self.days.get(datetime.fromtimestamp(at,self.zone).date().isoformat(),[0,0.0])
        return {"compressor_starts_observed":self.starts,"compressor_runtime_observed":self.seconds/3600,
                "compressor_starts_day":today[0],"compressor_runtime_day":today[1]/3600,
                "compressor_cycle_average":self.completed_seconds/self.completed_cycles/60 if self.completed_cycles else None}


@dataclass(frozen=True)
class CurveConfig:
    enabled: bool = False
    automatic: bool = False
    confirm_control: bool = False
    confirmation_id: str = ""
    target: str = "heating_setpoint"
    outdoor_entity: str = ""
    outdoor_min: float = -15
    outdoor_max: float = 20
    water_min: float = 25
    water_max: float = 50
    inertia_minutes: float = 30
    cooldown_seconds: float = 900
    step_degrees: float = 1
    max_age: float = 120
    pv_entity: str = ""
    pv_threshold_kw: float = 2
    pv_hysteresis_kw: float = .25
    pv_offset: float = 3
    battery_entity: str = ""
    battery_min_soc: float = 80
    battery_hysteresis: float = 5
    battery_low_offset: float = -3
    hold_seconds: float = 300

    def __post_init__(self):
        if self.target not in ("heating_setpoint","floor_setpoint","dhw_setpoint","cooling_setpoint"):
            raise ValueError("Unsupported curve target")
        for key in ("enabled","automatic","confirm_control"):
            if type(getattr(self,key)) is not bool:
                raise ValueError("Flags must be boolean")
        if not isinstance(self.confirmation_id,str):
            raise ValueError("Invalid confirmation identifier")
        if self.automatic and (not self.enabled or not self.confirm_control or not self.confirmation_id):
            raise ValueError("Automatic control requires explicit confirmation")
        for key in ("outdoor_entity","pv_entity","battery_entity"):
            value=getattr(self,key)
            if not isinstance(value,str) or (value and not value.startswith("sensor.")):
                raise ValueError("Select sensor entities")
        for key, low, high in (("outdoor_min",-50,50),("outdoor_max",-50,60),
            ("water_min",7,75),("water_max",7,75),("inertia_minutes",0,1440),
            ("cooldown_seconds",60,86400),("step_degrees",1,10),("max_age",5,3600),
            ("pv_threshold_kw",0,100),("pv_hysteresis_kw",0,20),("pv_offset",-10,10),
            ("battery_min_soc",0,100),("battery_hysteresis",0,50),("battery_low_offset",-10,0),
            ("hold_seconds",0,86400)):
            value=getattr(self,key)
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not isfinite(value) or not low<=value<=high:
                raise ValueError(f"Invalid {key}")
        if self.outdoor_min>=self.outdoor_max or self.water_min>self.water_max or self.pv_hysteresis_kw>self.pv_threshold_kw:
            raise ValueError("Invalid curve endpoints or hysteresis")

    @classmethod
    def from_options(cls, options):
        return cls(**dict(options.get("weather_curve",{})))


class CurveModel:
    def __init__(self,config):
        self.config=config
        self.last=None
        self.pv_active=False
        self.battery_low=False
        self.pending=None
        self.active_offset=0.0

    def reset(self):
        self.last=None
        self.pending=None
        self.active_offset=0.0
        self.pv_active=False
        self.battery_low=False

    def calculate(self,outdoor,pv_kw,battery_soc,clock,limits):
        c=self.config
        if not isfinite(outdoor) or not -50<=outdoor<=60:
            raise ValueError("Invalid outdoor temperature")
        ratio=max(0,min(1,(outdoor-c.outdoor_min)/(c.outdoor_max-c.outdoor_min)))
        # Cooling needs warmer supply at colder outdoor temperatures.
        base=c.water_min+(c.water_max-c.water_min)*ratio if c.target=="cooling_setpoint" else c.water_max-(c.water_max-c.water_min)*ratio
        if self.last and c.inertia_minutes:
            dt=max(0,clock-self.last[0])
            base=self.last[1]+(1-exp(-dt/(60*c.inertia_minutes)))*(base-self.last[1])
        self.last=(clock,base)
        if c.pv_entity:
            if pv_kw is None or not isfinite(pv_kw):
                raise ValueError("PV source unavailable")
            self.pv_active=pv_kw>=c.pv_threshold_kw-(c.pv_hysteresis_kw if self.pv_active else 0)
        if c.battery_entity:
            if battery_soc is None or not isfinite(battery_soc) or not 0<=battery_soc<=100:
                raise ValueError("Battery source unavailable")
            self.battery_low=battery_soc<=c.battery_min_soc+(c.battery_hysteresis if self.battery_low else 0)
        # Battery reserve wins over PV boost; no arbitrary absolute-value competition.
        offset=c.battery_low_offset if self.battery_low else c.pv_offset if self.pv_active else 0
        if c.target=="cooling_setpoint":
            offset=-offset
        if self.pending is None or self.pending[0]!=offset:
            self.pending=(offset,clock)
        if clock-self.pending[1]>=c.hold_seconds:
            self.active_offset=offset
        low=ceil(max(limits[0],c.water_min))
        high=floor(min(limits[1],c.water_max))
        if low>high:
            raise ValueError("Curve outside commissioned limits")
        return {"curve_base_target":base,"curve_offset":self.active_offset,
                "curve_advised_target":float(round(max(low,min(high,base+self.active_offset)))),
                "curve_pending_offset":offset}
