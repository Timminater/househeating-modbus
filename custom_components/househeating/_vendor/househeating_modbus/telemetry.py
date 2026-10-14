"""Read-only thermal estimates and paired energy accounting. No HA or device I/O."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from .models import DeviceConfig, Snapshot

HEATING_MODES = frozenset((1, 2, 3, 5, 7))


@dataclass(frozen=True)
class MonitoringConfig:
    enabled: bool = False
    thermal_confirmed: bool = False
    source: str = "modbus"
    external_power: str = ""
    external_energy: str = ""
    thermal_source: str = "hydraulic"
    external_heat_power: str = ""
    max_age: float = 90.0
    max_skew: float = 5.0
    flow_factor: float = 1.0
    delta_correction: float = 0.0
    density: float = 1.0
    specific_heat: float = 4.18
    fluid_reference: str = "Water approximation"
    min_power: float = 0.05
    energy_resolution: float = 0.001
    max_power: float = 30.0

    def __post_init__(self):
        if not all(isinstance(getattr(self, key), str) for key in
                   ("source", "external_power", "external_energy", "thermal_source", "external_heat_power", "fluid_reference")):
            raise ValueError("Source identifiers and fluid reference must be text")
        if type(self.enabled) is not bool or type(self.thermal_confirmed) is not bool:
            raise ValueError("Confirmation and enable flags must be boolean")
        if self.source not in ("modbus", "external"):
            raise ValueError("Unknown electrical source")
        if self.thermal_source not in ("hydraulic", "external"):
            raise ValueError("Unknown thermal source")
        if self.thermal_source == "external" and not self.external_heat_power.startswith("sensor."):
            raise ValueError("An external signed thermal power sensor is required")
        if self.source == "external" and not self.external_power.startswith("sensor."):
            raise ValueError("An external power sensor is required")
        if self.external_energy and not self.external_energy.startswith("sensor."):
            raise ValueError("External energy must be a sensor")
        if self.source != "external" and self.external_energy:
            raise ValueError("An external counter requires the external source")
        for name, low, high in (("max_age", 1, 3600), ("max_skew", .1, 120),
                                ("flow_factor", .01, 100), ("delta_correction", -20, 20),
                                ("density", .1, 2), ("specific_heat", .1, 10),
                                ("min_power", .001, 10), ("energy_resolution", .000001, 100),
                                ("max_power", .1, 100)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid {name}")

    @classmethod
    def from_options(cls, options):
        data = dict(options.get("monitoring", {}))
        data.setdefault("max_age", max(90.0, 2.5 * options.get("scan_interval", 30)))
        return cls(**data)

    @property
    def counter_mode(self):
        return self.source == "external" and bool(self.external_energy)


@dataclass(frozen=True)
class Reading:
    value: float
    reported_at: float
    restored: bool = False


@dataclass(frozen=True)
class Sample:
    at: float
    monotonic: float
    power: float | None = None
    thermal: float | None = None
    flow: float | None = None
    delta: float | None = None
    mode: int | None = None
    reasons: tuple[str, ...] = ()
    hydraulic_thermal: float | None = None
    external_thermal: float | None = None

    @property
    def category(self):
        return "heat" if self.mode in HEATING_MODES else "cool" if self.mode == 0 else None


def valid_reading(reading, now, max_age):
    return (reading is not None and not reading.restored and isfinite(reading.value)
            and isfinite(reading.reported_at) and 0 <= now - reading.reported_at <= max_age)


def calculate(snapshot: Snapshot | None, device_config: DeviceConfig,
              config: MonitoringConfig, now: float, monotonic: float,
              external_power: Reading | None = None, external_heat: Reading | None = None) -> Sample:
    reasons = []
    def measurement(key, address, *, raw_value=False):
        if snapshot is None:
            return None
        window = snapshot.samples.get(address)
        if window is None or not 0 <= now - window.end <= config.max_age:
            return None
        if not 0 <= monotonic - window.monotonic_end <= config.max_age:
            return None
        value = snapshot.raw.get(address) if raw_value else snapshot.value(key, device_config)
        return value if value is not None and isfinite(value) else None

    if config.source == "external":
        power = external_power.value if valid_reading(external_power, now, config.max_age) else None
    else:
        power = measurement("input_power", 0x5C)
    if power is not None and not 0 <= power <= config.max_power:
        power = None
    if power is None:
        reasons.append("electrical_unavailable")
    flow = delta = thermal = None
    def hydraulic_problem(reason):
        if config.thermal_source == "hydraulic":
            reasons.append(reason)
    if not config.thermal_confirmed:
        hydraulic_problem("thermal_unconfirmed")
    else:
        inlet = measurement("water_inlet_temperature", 0x4F)
        outlet = measurement("water_outlet_temperature", 0x50)
        raw_flow = measurement("flow_raw", 0x58, raw_value=True)
        if inlet is None or outlet is None or raw_flow is None:
            hydraulic_problem("hydraulic_unavailable")
        else:
            windows = [snapshot.samples[a] for a in (0x4F, 0x50, 0x58)]
            if max(w.end for w in windows) - min(w.start for w in windows) > config.max_skew:
                hydraulic_problem("hydraulic_skew")
            else:
                flow = raw_flow * config.flow_factor
                delta = outlet - inlet + config.delta_correction
                thermal = flow * config.density * config.specific_heat * delta / 60
                if not all(isfinite(v) for v in (flow, delta, thermal)) or not 0 <= flow <= 100:
                    flow = delta = thermal = None
                    hydraulic_problem("hydraulic_invalid")
    hydraulic_thermal=thermal
    reported_thermal=None
    if config.thermal_source == "external":
        reported_thermal=external_heat.value if valid_reading(external_heat,now,config.max_age) else None
        if reported_thermal is not None and abs(reported_thermal)>100:
            reported_thermal=None
        thermal=reported_thermal
        if thermal is None:
            reasons.append("external_heat_unavailable")
    mode = None
    if snapshot is not None:
        window = snapshot.samples.get(0x304)
        if window and 0 <= now - window.end <= config.max_age and 0 <= monotonic - window.monotonic_end <= config.max_age:
            mode = snapshot.raw.get(0x304)
    if mode not in HEATING_MODES and mode != 0:
        reasons.append("mode_ambiguous")
    return Sample(now, monotonic, power, thermal, flow, delta, mode, tuple(reasons),hydraulic_thermal,reported_thermal)


def signed_energy(a, b, seconds):
    """Positive and negative magnitudes of a linear kW segment, in kWh."""
    if a * b < 0:
        first = seconds * abs(a) / (abs(a) + abs(b))
        p1, n1 = signed_energy(a, 0, first)
        p2, n2 = signed_energy(0, b, seconds - first)
        return p1 + p2, n1 + n2
    energy = (a + b) * .5 * seconds / 3600
    return max(energy, 0), max(-energy, 0)


def period_bounds(at, scope, zone):
    local = datetime.fromtimestamp(at, zone)
    if scope == "day":
        start = datetime(local.year, local.month, local.day, tzinfo=zone)
        end = start + timedelta(days=1)
    else:
        start = datetime(local.year, local.month, 1, tzinfo=zone)
        year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
        end = datetime(year, month, 1, tzinfo=zone)
    return start.timestamp(), end.timestamp()


@dataclass
class Bucket:
    start: float
    end: float
    electric: float = 0.0
    delivered: float = 0.0
    extracted: float = 0.0
    heat_electric: float = 0.0
    heat_net: float = 0.0
    cool_electric: float = 0.0
    cool_output: float = 0.0
    heat_seconds: float = 0.0
    cool_seconds: float = 0.0
    excluded: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


class EnergyLedger:
    """A per-config-entry ledger. Persist via the caller before publishing."""
    def __init__(self, config: MonitoringConfig, timezone_name="Europe/Amsterdam", state=None):
        self.config = config
        self.zone = ZoneInfo(timezone_name)
        self.totals = {"electric": 0.0, "delivered": 0.0, "extracted": 0.0}
        self.periods = {}
        self.previous_periods = {}
        self.history = {}
        self.overall = Bucket(0,1)
        self.counter = None
        self.counter_candidate = None
        self.last_reported = None
        self.previous: Sample | None = None
        self.segments = []
        self.last_sample: Sample | None = None
        self.incidents = {}
        self.counter_valid = False
        if state:
            if state.get("version") != 1:
                raise ValueError("Unsupported monitoring storage version")
            self.totals.update(state["totals"])
            self.periods = {k: Bucket(**v) for k, v in state.get("periods", {}).items()}
            self.previous_periods = {k: Bucket(**v) for k, v in state.get("previous_periods", {}).items()}
            self.history = {k:Bucket(**v) for k,v in state.get("history",{}).items()}
            if state.get("overall"):
                self.overall = Bucket(**state["overall"])
            self.incidents = dict(state.get("incidents", {}))
            for bucket in self.periods.values():
                if "restart_gap" not in bucket.flags:
                    bucket.flags.append("restart_gap")
            # Counter baseline may recover real offline electricity; never restore a
            # thermal integration anchor or presume offline heat production.
            if asdict(MonitoringConfig(**state.get("config",{}))) == asdict(config) and state.get("timezone") == timezone_name:
                self.counter = state.get("counter")
                self.last_reported = state.get("last_reported")
            else:
                self.incident("configuration_changed")
                for bucket in self.periods.values():
                    bucket.flags.append("configuration_changed")
            if not all(isfinite(v) and v >= 0 for v in self.totals.values()):
                raise ValueError("Invalid persisted energy totals")
            for b in (*self.periods.values(), *self.previous_periods.values(), *self.history.values(), self.overall):
                fields = asdict(b)
                numeric = {k:v for k,v in fields.items() if k not in ("excluded", "flags")}
                if not all(isinstance(v, (int,float)) and isfinite(v) for v in numeric.values()) or b.end <= b.start:
                    raise ValueError("Invalid persisted period")
                if any(numeric[k] < 0 for k in ("electric", "delivered", "extracted", "heat_electric", "cool_electric", "heat_seconds", "cool_seconds")):
                    raise ValueError("Invalid persisted period totals")
                if not all(isfinite(v) and v >= 0 for v in b.excluded.values()):
                    raise ValueError("Invalid persisted coverage")
            if self.counter is not None and (len(self.counter) != 2 or not all(isfinite(v) and v >= 0 for v in self.counter)):
                raise ValueError("Invalid persisted counter baseline")
            if self.last_reported is not None and not isfinite(self.last_reported):
                raise ValueError("Invalid persisted counter timestamp")

    def incident(self, reason):
        self.incidents[reason] = self.incidents.get(reason, 0) + 1

    def export(self):
        return {"version": 1, "timezone": str(self.zone), "config": asdict(self.config),
                "totals": dict(self.totals), "periods": {k: asdict(v) for k, v in self.periods.items()},
                "previous_periods": {k: asdict(v) for k, v in self.previous_periods.items()},
                "history": {k:asdict(v) for k,v in self.history.items()}, "overall":asdict(self.overall),
                "counter": self.counter, "last_reported": self.last_reported,
                "incidents": dict(self.incidents)}

    def bucket(self, at, scope):
        start, end = period_bounds(at, scope, self.zone)
        old = self.periods.get(scope)
        if old is None or start > old.start:
            if old:
                self.previous_periods[scope] = old
                if scope == "day":
                    self.history[str(old.start)] = old
                    self.history = dict(sorted(self.history.items(),key=lambda item:item[1].start)[-370:])
            self.periods[scope] = Bucket(start, end)
            if at > start:
                self.periods[scope].flags.append("partial_period")
        return self.periods.get(scope) if self.periods[scope].start == start else None

    def cuts(self, a, b, scope):
        while a < b:
            _, boundary = period_bounds(a, scope, self.zone)
            end = min(b, boundary)
            yield a, end
            a = end

    def ingest(self, sample: Sample, counter: Reading | None = None):
        if self.overall.start == 0:
            self.overall.start=sample.at
        self.overall.end=max(sample.at,self.overall.start+1)
        old = self.previous
        if old is not None and sample.at < old.at:
            self.incident("out_of_order")
            return
        self.last_sample = sample
        if old is not None and sample.at > old.at:
            dt = sample.at - old.at
            dm = sample.monotonic - old.monotonic
            continuous = 0 < dm <= self.config.max_age and abs(dm - dt) <= 2
            thermal_ok = continuous and old.thermal is not None and sample.thermal is not None
            power_ok = continuous and old.power is not None and sample.power is not None
            category = sample.category if sample.mode == old.mode else None
            if not continuous:
                self.incident("measurement_gap")
            if thermal_ok:
                plus, minus = signed_energy(old.thermal, sample.thermal, dt)
                self.totals["delivered"] += plus
                self.totals["extracted"] += minus
            if power_ok and not self.config.counter_mode:
                self.totals["electric"] += (old.power + sample.power) * .5 * dt / 3600
            self.segments.append((old.at, sample.at, old.thermal if thermal_ok else None,
                                  sample.thermal if thermal_ok else None, category))
            # Keep only a bounded fresh history for asynchronous external counters.
            self.segments = [s for s in self.segments[-4096:] if s[1] >= sample.at - self.config.max_age * 2]
            for scope in ("day", "month"):
                for start, end in self.cuts(old.at, sample.at, scope):
                    bucket = self.bucket(start, scope)
                    if bucket is None:
                        continue
                    f0, f1 = (start-old.at)/dt, (end-old.at)/dt
                    plus = minus = electric = 0.0
                    if thermal_ok:
                        qa = old.thermal + (sample.thermal-old.thermal)*f0
                        qb = old.thermal + (sample.thermal-old.thermal)*f1
                        plus, minus = signed_energy(qa, qb, end-start)
                        bucket.delivered += plus
                        bucket.extracted += minus
                    if power_ok and not self.config.counter_mode:
                        pa = old.power + (sample.power-old.power)*f0
                        pb = old.power + (sample.power-old.power)*f1
                        electric = (pa+pb)*.5*(end-start)/3600
                        bucket.electric += electric
                    if not self.config.counter_mode:
                        if thermal_ok and power_ok and category:
                            self.pair(bucket, category, plus, minus, electric, end-start)
                        else:
                            reason = "measurement_gap" if not continuous else "mode_ambiguous" if not category else "missing_input"
                            bucket.excluded[reason] = bucket.excluded.get(reason, 0) + end-start
        self.previous = sample
        # Handle counter intervals before rolling a period at an exact boundary.
        if self.config.counter_mode:
            self.accept_counter(counter, sample.at)
        for scope in ("day", "month"):
            self.bucket(sample.at, scope)

    def pair(self, bucket, category, plus, minus, electric, seconds):
        if category == "heat":
            bucket.heat_net += plus-minus
            bucket.heat_electric += electric
            bucket.heat_seconds += seconds
        elif category == "cool":
            bucket.cool_output += minus-plus
            bucket.cool_electric += electric
            bucket.cool_seconds += seconds
        if bucket.end-bucket.start <= 25*3600 and bucket is not self.overall:
            self.pair(self.overall,category,plus,minus,electric,seconds)

    def covered(self, start, end):
        cursor, plus, minus, category = start, 0.0, 0.0, None
        for a, b, qa, qb, cat in self.segments:
            if b <= start or a >= end:
                continue
            if a > cursor + .001 or qa is None or qb is None or cat is None:
                return None
            if category is not None and category != cat:
                return None
            category = cat
            left, right = max(start, a), min(end, b)
            x = qa + (qb-qa)*(left-a)/(b-a)
            y = qa + (qb-qa)*(right-a)/(b-a)
            p, n = signed_energy(x, y, right-left)
            plus += p
            minus += n
            cursor = right
        return (plus, minus, category) if cursor >= end-.001 and category else None

    def accept_counter(self, reading, now):
        self.counter_valid = valid_reading(reading, now, self.config.max_age) and reading.value >= 0
        if not self.counter_valid:
            return
        if self.last_reported is not None and reading.reported_at <= self.last_reported:
            return
        self.last_reported = reading.reported_at
        value = reading.value
        end = reading.reported_at
        if self.counter is None:
            self.counter = [value, end]
            self.segments = [s for s in self.segments if s[1] > end]
            return
        previous, start = self.counter
        if value < previous:
            if self.counter_candidate is not None and value >= self.counter_candidate:
                self.counter = [value, end]
                self.counter_candidate = None
                self.incident("counter_reset")
            else:
                self.counter_candidate = value
                self.incident("counter_decrease")
            self.counter_valid = False
            self.segments = [s for s in self.segments if s[1] > end]
            return
        self.counter_candidate = None
        delta = value-previous
        if end <= start or delta > self.config.max_power*(end-start)/3600 + 2*self.config.energy_resolution:
            self.counter_valid = False
            self.incident("counter_jump")
            self.segments = []
            return
        self.totals["electric"] += delta
        covered = self.covered(start, end)
        for scope in ("day", "month"):
            start_period = period_bounds(start, scope, self.zone)[0]
            end_period = period_bounds(end-1e-6, scope, self.zone)[0]
            bucket = self.bucket(max(start, end-1e-6), scope)
            if bucket is None:
                previous_bucket = self.previous_periods.get(scope)
                if previous_bucket and previous_bucket.start == end_period:
                    bucket = previous_bucket
            if bucket is None:
                continue
            if start_period == end_period:
                bucket.electric += delta
                if covered:
                    plus, minus, category = covered
                    self.pair(bucket, category, plus, minus, delta, end-start)
                else:
                    bucket.excluded["counter_unpaired"] = bucket.excluded.get("counter_unpaired", 0) + end-start
            else:
                # Entire delta stays in the lifetime total. Do not invent its
                # distribution between calendar periods or their COP denominators.
                for left, right in self.cuts(start, end, scope):
                    excluded_bucket = self.bucket(left, scope)
                    if excluded_bucket is None:
                        previous_bucket = self.previous_periods.get(scope)
                        if previous_bucket and previous_bucket.start == period_bounds(left, scope, self.zone)[0]:
                            excluded_bucket = previous_bucket
                    if excluded_bucket is not None:
                        if "counter_boundary_unallocated" not in excluded_bucket.flags:
                            excluded_bucket.flags.append("counter_boundary_unallocated")
                        excluded_bucket.excluded["counter_boundary_unallocated"] = excluded_bucket.excluded.get("counter_boundary_unallocated", 0) + right-left
                self.incident("counter_boundary_unallocated")
        self.counter = [value, end]
        self.segments = [s for s in self.segments if s[1] > end]

    def values(self, now):
        result = {"electrical_energy_total": self.totals["electric"],
                  "thermal_energy_delivered": self.totals["delivered"],
                  "thermal_energy_extracted": self.totals["extracted"],
                  "thermal_energy_net": self.totals["delivered"]-self.totals["extracted"]}
        sample = self.last_sample
        fresh = sample is not None and 0 <= now-sample.at <= self.config.max_age
        result.update(selected_electrical_power=sample.power if fresh else None,
                      water_flow_calibrated=sample.flow if fresh else None,
                      water_delta_temperature=sample.delta if fresh else None,
                      thermal_power_estimated=sample.thermal if fresh else None,
                      thermal_power_hydraulic_estimated=sample.hydraulic_thermal if fresh else None,
                      thermal_power_external_reported=sample.external_thermal if fresh else None,
                      cop_instant=None, eer_instant=None)
        if fresh and sample.power is not None and sample.power >= self.config.min_power and sample.thermal is not None:
            if sample.category == "heat" and sample.thermal > 0:
                result["cop_instant"] = sample.thermal/sample.power
            if sample.category == "cool" and sample.thermal < 0:
                result["eer_instant"] = -sample.thermal/sample.power
        threshold = max(.01, 10*self.config.energy_resolution) if self.config.counter_mode else .01
        for scope, b in self.periods.items():
            elapsed = max(0, min(now, b.end)-b.start)
            result.update({f"electrical_energy_{scope}": b.electric,
                           f"thermal_energy_net_{scope}": b.delivered-b.extracted,
                           f"heating_energy_paired_{scope}": b.heat_net,
                           f"heating_electricity_paired_{scope}": b.heat_electric,
                           f"cooling_energy_paired_{scope}": b.cool_output,
                           f"cooling_electricity_paired_{scope}": b.cool_electric,
                           f"cop_{scope}": b.heat_net/b.heat_electric if b.heat_electric >= threshold and b.heat_net > 0 else None,
                           f"eer_{scope}": b.cool_output/b.cool_electric if b.cool_electric >= threshold and b.cool_output > 0 else None,
                           f"cop_coverage_{scope}": 100*b.heat_seconds/elapsed if elapsed else 0.0,
                           f"eer_coverage_{scope}": 100*b.cool_seconds/elapsed if elapsed else 0.0})
        if not fresh:
            status = "unavailable"
        elif self.config.thermal_source == "hydraulic" and not self.config.thermal_confirmed:
            status = "awaiting_confirmation"
        elif sample.reasons or (self.config.counter_mode and not self.counter_valid):
            status = "partial"
        else:
            status = "valid"
        result["monitoring_status"] = status
        for scope in ("yesterday","7d","30d","365d","overall"):
            b,elapsed=self.aggregate(scope,now)
            result.update({f"heating_energy_paired_{scope}":b.heat_net,
                f"heating_electricity_paired_{scope}":b.heat_electric,
                f"cooling_energy_paired_{scope}":b.cool_output,
                f"cooling_electricity_paired_{scope}":b.cool_electric,
                f"cop_{scope}":b.heat_net/b.heat_electric if b.heat_electric>=threshold and b.heat_net>0 else None,
                f"eer_{scope}":b.cool_output/b.cool_electric if b.cool_electric>=threshold and b.cool_output>0 else None,
                f"cop_coverage_{scope}":100*b.heat_seconds/elapsed if elapsed else 0,
                f"eer_coverage_{scope}":100*b.cool_seconds/elapsed if elapsed else 0})
        return result

    def aggregate(self,scope,now):
        if scope=="overall":
            return self.overall,max(0,now-self.overall.start) if self.overall.start else 0
        local=datetime.fromtimestamp(now,self.zone)
        today=datetime(local.year,local.month,local.day,tzinfo=self.zone)
        if scope=="yesterday":
            start=(today-timedelta(days=1)).timestamp()
            end=today.timestamp()
        else:
            start=(today-timedelta(days=int(scope[:-1])-1)).timestamp()
            end=now
        aggregate=Bucket(start,max(start+1,end))
        buckets=dict(self.history)
        for b in (self.previous_periods.get("day"),self.periods.get("day")):
            if b:
                buckets[str(b.start)]=b
        for b in buckets.values():
            if start<=b.start<end:
                for key in ("heat_net","heat_electric","cool_output","cool_electric","heat_seconds","cool_seconds"):
                    setattr(aggregate,key,getattr(aggregate,key)+getattr(b,key))
        return aggregate,max(0,end-start)
