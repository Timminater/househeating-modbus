from dataclasses import asdict, replace
from datetime import datetime, timezone
from math import nan
from zoneinfo import ZoneInfo

import pytest

from househeating_modbus.models import DeviceConfig, ReadWindow, Snapshot
from househeating_modbus.telemetry import (
    MonitoringConfig, Reading, Sample, EnergyLedger, calculate, signed_energy, period_bounds,
)
from fake_unit import FakeUnit, memory
from househeating_modbus import HeatPump

BASE = datetime(2026, 10, 14, 8, tzinfo=timezone.utc).timestamp()


def config(**kwargs):
    return MonitoringConfig(enabled=True, thermal_confirmed=True, **kwargs)


def snapshot(at=BASE, **changes):
    raw = memory()
    raw.update({0x4F: 300, 0x50: 350, 0x58: 20, 0x5C: 257})
    raw.update(changes)
    return Snapshot(raw=raw, timestamp=at,
                    samples={a: ReadWindow(at, at, at) for a in raw})


def sample(at=BASE, q=6, p=2, mode=1, **kw):
    return Sample(at=at, monotonic=at, thermal=q, power=p, mode=mode, **kw)


def test_documented_formula_scaling_and_raw_immutability():
    snap = snapshot()
    result = calculate(snap, DeviceConfig(), config(), BASE, BASE)
    assert result.power == 2.57
    assert result.flow == 20 and result.delta == 5
    assert result.thermal == pytest.approx(6.9666666667)
    corrected = calculate(snap, DeviceConfig(), config(flow_factor=1.1, delta_correction=-1,
                          density=1.05, specific_heat=3.7), BASE, BASE)
    assert corrected.thermal == pytest.approx(22*4*1.05*3.7/60)
    assert snap.raw[0x58] == 20 and snap.value('water_outlet_temperature', DeviceConfig()) == 35


@pytest.mark.parametrize('divisor', [1, 10])
def test_independent_temperature_divisors(divisor):
    snap = snapshot()
    raw = dict(snap.raw) | {0x4F: 30*divisor, 0x50: 35*divisor}
    assert calculate(replace(snap, raw=raw), DeviceConfig(measurement_divisor=divisor),
                     config(), BASE, BASE).delta == 5


def test_confirmation_missing_stale_skew_and_sensor_fault():
    snap = snapshot()
    assert calculate(snap, DeviceConfig(), MonitoringConfig(), BASE, BASE).thermal is None
    for address in (0x4F, 0x50, 0x58):
        stamps = dict(snap.samples)
        del stamps[address]
        assert calculate(replace(snap, samples=stamps), DeviceConfig(), config(), BASE, BASE).thermal is None
    stale = calculate(snap, DeviceConfig(), config(), BASE+100, BASE+100)
    assert stale.power is None and stale.thermal is None
    stamps = dict(snap.samples) | {0x58: ReadWindow(BASE-10, BASE, BASE)}
    assert 'hydraulic_skew' in calculate(replace(snap, samples=stamps), DeviceConfig(), config(), BASE, BASE).reasons
    raw = dict(snap.raw) | {2: 1 << 7}
    assert calculate(replace(snap, raw=raw), DeviceConfig(), config(), BASE, BASE).thermal is None


def test_zero_flow_valid_but_missing_temperature_not_zero():
    snap = snapshot()
    snap = replace(snap, raw=dict(snap.raw) | {0x58: 0})
    assert calculate(snap, DeviceConfig(), config(), BASE, BASE).thermal == 0
    raw = dict(snap.raw)
    del raw[0x4F]
    assert calculate(replace(snap, raw=raw), DeviceConfig(), config(), BASE, BASE).thermal is None


def test_explicit_flow_scaling_does_not_change_the_reported_register_sensor():
    snap=snapshot()
    snap=replace(snap,raw=dict(snap.raw)|{0x58:200})
    assert calculate(snap,DeviceConfig(),config(),BASE,BASE).thermal is None
    result=calculate(snap,DeviceConfig(),config(flow_factor=.1),BASE,BASE)
    assert result.flow==20 and result.thermal==pytest.approx(6.9666666667)
    assert snap.raw[0x58]==200


@pytest.mark.parametrize('kwargs', [{'density':nan}, {'flow_factor':0}, {'specific_heat':-1},
                                   {'source':'guess'}, {'source':'external'}, {'max_age':0},
                                   {'min_power':True}, {'external_energy':'sensor.kwh'}])
def test_reject_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        MonitoringConfig(**kwargs)


def test_signed_zero_crossing_and_net_identity():
    plus, minus = signed_energy(6, -6, 3600)
    assert plus == minus == 1.5
    assert signed_energy(-3, -3, 3600) == (0, 3)


def test_constant_energy_and_cop():
    ledger = EnergyLedger(config(max_age=3600))
    ledger.ingest(sample())
    ledger.ingest(sample(BASE+3600))
    values = ledger.values(BASE+3600)
    assert values['electrical_energy_total'] == 2
    assert values['thermal_energy_delivered'] == 6
    assert values['thermal_energy_net'] == 6
    assert values['cop_day'] == values['cop_month'] == 3
    assert ledger.periods['day'].heat_seconds == 3600


def test_energy_ratio_is_not_average_instant_cop():
    ledger = EnergyLedger(config(max_age=3600))
    ledger.ingest(sample(q=6, p=1))
    ledger.ingest(sample(BASE+600, q=6, p=1))
    ledger.ingest(sample(BASE+1200, q=6, p=3))
    ledger.ingest(sample(BASE+3600, q=6, p=3))
    assert ledger.values(BASE+3600)['cop_day'] == pytest.approx(6/(.1666666667+.3333333333+2))
    assert ledger.values(BASE+3600)['cop_day'] != pytest.approx((6+2)/2)


def test_missing_hydraulics_excludes_both_paired_energies_only():
    ledger = EnergyLedger(config())
    ledger.ingest(sample())
    ledger.ingest(sample(BASE+30, q=None))
    ledger.ingest(sample(BASE+60))
    assert ledger.totals['electric'] == pytest.approx(2/60)
    assert ledger.totals['delivered'] == 0
    assert ledger.periods['day'].heat_electric == 0
    ledger.ingest(sample(BASE+90))
    assert ledger.periods['day'].heat_seconds == 30


@pytest.mark.parametrize('kind', ['long_gap', 'wall_clock_jump', 'monotonic_jump'])
def test_no_gap_or_clock_jump_bridging(kind):
    ledger = EnergyLedger(config())
    ledger.ingest(sample())
    next_sample = sample(BASE+100 if kind=='long_gap' else BASE+30)
    if kind=='wall_clock_jump':
        next_sample = replace(next_sample, monotonic=BASE+10)
    elif kind=='monotonic_jump':
        next_sample = replace(next_sample, monotonic=BASE-1)
    ledger.ingest(next_sample)
    assert ledger.totals == {'electric':0, 'delivered':0, 'extracted':0}


def test_defrost_subtracts_and_low_power_still_accumulates():
    ledger = EnergyLedger(config(max_age=3600))
    ledger.ingest(sample(q=-3, p=.02))
    ledger.ingest(sample(BASE+3600, q=-3, p=.02))
    values = ledger.values(BASE+3600)
    assert values['thermal_energy_net'] == -3
    assert values['electrical_energy_total'] == .02
    assert values['cop_instant'] is None and values['cop_day'] is None


@pytest.mark.parametrize('mode,expected', [(0,'eer_day'), (4,None), (6,None)])
def test_cooling_and_ambiguous_modes(mode, expected):
    ledger = EnergyLedger(config(max_age=3600))
    ledger.ingest(sample(q=-6, mode=mode))
    ledger.ingest(sample(BASE+3600, q=-6, mode=mode))
    values = ledger.values(BASE+3600)
    assert values['thermal_energy_extracted'] == 6
    assert values['cop_day'] is None
    assert values['eer_day'] == (3 if expected else None)


@pytest.mark.parametrize('date,hours', [(datetime(2026,3,29,12,tzinfo=timezone.utc),23),
                                       (datetime(2026,10,25,12,tzinfo=timezone.utc),25)])
def test_dst_calendar_days(date, hours):
    a,b = period_bounds(date.timestamp(), 'day', ZoneInfo('Europe/Amsterdam'))
    assert b-a == hours*3600


def test_power_interval_splits_midnight_and_preserves_previous():
    midnight = datetime(2026,11,1,tzinfo=ZoneInfo('Europe/Amsterdam')).timestamp()
    ledger = EnergyLedger(config())
    ledger.ingest(sample(midnight-30))
    ledger.ingest(sample(midnight+30))
    assert ledger.previous_periods['day'].electric == pytest.approx(2/120)
    assert ledger.periods['day'].electric == pytest.approx(2/120)
    assert ledger.previous_periods['month'].heat_net == pytest.approx(6/120)
    assert ledger.periods['month'].heat_net == pytest.approx(6/120)


def counter_config(**kwargs):
    return config(source='external', external_power='sensor.power', external_energy='sensor.energy', **kwargs)


def test_external_counter_pairing_dedup_and_restore():
    ledger = EnergyLedger(counter_config())
    ledger.ingest(sample(), Reading(100, BASE))
    ledger.ingest(sample(BASE+30), Reading(100+2/120, BASE+30))
    assert ledger.totals['electric'] == pytest.approx(2/120)
    assert ledger.values(BASE+30)['cop_day'] == pytest.approx(3)
    ledger.ingest(sample(BASE+60), Reading(100+2/120, BASE+30))
    assert ledger.totals['electric'] == pytest.approx(2/120)
    restored = EnergyLedger(counter_config(), state=ledger.export())
    restored.ingest(sample(BASE+3600), Reading(102, BASE+3600))
    assert restored.totals['electric'] == pytest.approx(2)
    assert restored.periods['day'].heat_electric == pytest.approx(2/120)


def test_counter_hole_excludes_heat_and_electric_from_ratio():
    ledger = EnergyLedger(counter_config())
    ledger.ingest(sample(), Reading(0,BASE))
    ledger.ingest(sample(BASE+10,q=None), Reading(0,BASE))
    ledger.ingest(sample(BASE+20), Reading(.01,BASE+20))
    assert ledger.totals['electric'] == .01
    assert ledger.periods['day'].heat_electric == 0
    assert ledger.periods['day'].heat_net == 0


def test_counter_reset_requires_two_consistent_samples():
    ledger = EnergyLedger(counter_config())
    ledger.ingest(sample(), Reading(100,BASE))
    ledger.ingest(sample(BASE+30), Reading(0,BASE+30))
    ledger.ingest(sample(BASE+60), Reading(.01,BASE+60))
    assert ledger.totals['electric'] == 0
    assert ledger.counter[0] == .01
    ledger.ingest(sample(BASE+90), Reading(.03,BASE+90))
    assert ledger.totals['electric'] == pytest.approx(.02)
    assert ledger.incidents['counter_reset'] == 1


def test_counter_bad_sample_or_jump_never_adds_phantom_energy():
    ledger = EnergyLedger(counter_config())
    ledger.ingest(sample(), Reading(100,BASE))
    ledger.ingest(sample(BASE+30), Reading(999,BASE+30))
    assert ledger.counter[0] == 100 and ledger.totals['electric'] == 0
    ledger.ingest(sample(BASE+60), Reading(100.01,BASE+60))
    assert ledger.totals['electric'] == pytest.approx(.01)
    assert ledger.periods['day'].heat_electric == 0


def test_counter_delta_crossing_period_not_arbitrarily_distributed():
    midnight = datetime(2026,11,1,tzinfo=ZoneInfo('Europe/Amsterdam')).timestamp()
    ledger = EnergyLedger(counter_config())
    ledger.ingest(sample(midnight-30), Reading(0,midnight-30))
    ledger.ingest(sample(midnight+30), Reading(.03,midnight+30))
    assert ledger.totals['electric'] == .03
    assert ledger.periods['day'].heat_electric == ledger.periods['month'].heat_electric == 0
    assert 'counter_boundary_unallocated' in ledger.periods['day'].flags
    assert ledger.previous_periods['day'].excluded['counter_boundary_unallocated'] == 30
    assert ledger.periods['day'].excluded['counter_boundary_unallocated'] == 30


def test_counter_resolution_minimum_and_restored_reading():
    ledger = EnergyLedger(counter_config(energy_resolution=.1))
    ledger.ingest(sample(), Reading(1,BASE,restored=True))
    assert ledger.counter is None
    ledger.ingest(sample(BASE+30), Reading(1,BASE+30))
    ledger.ingest(sample(BASE+60), Reading(1.1,BASE+60))
    assert ledger.values(BASE+60)['cop_day'] is None


def test_config_change_retains_totals_without_an_integration_anchor():
    ledger = EnergyLedger(config())
    ledger.ingest(sample())
    ledger.ingest(sample(BASE+30))
    changed = EnergyLedger(config(flow_factor=1.1), state=ledger.export())
    assert changed.totals == ledger.totals and changed.previous is None
    assert 'configuration_changed' in changed.periods['day'].flags
    changed.ingest(sample(BASE+300))
    assert changed.totals == ledger.totals


def test_delayed_counter_uses_actual_report_times_and_retains_tail_coverage():
    ledger = EnergyLedger(counter_config())
    ledger.ingest(sample(BASE-1))
    ledger.ingest(sample(BASE+.1), Reading(100,BASE))
    ledger.ingest(sample(BASE+30+.1), Reading(100+2/120,BASE+30))
    ledger.ingest(sample(BASE+60+.1), Reading(100+4/120,BASE+60))
    assert ledger.counter[1] == BASE+60
    assert ledger.periods['day'].heat_seconds == pytest.approx(60)
    assert ledger.values(BASE+60.1)['cop_day'] == pytest.approx(3)


@pytest.mark.parametrize('field', ['totals', 'period', 'counter'])
def test_corrupt_storage_refused_instead_of_resetting_totals(field):
    ledger = EnergyLedger(counter_config())
    ledger.ingest(sample(),Reading(100,BASE))
    state = ledger.export()
    if field == 'totals':
        state['totals']['electric'] = nan
    elif field == 'period':
        state['periods']['day']['heat_net'] = nan
    else:
        state['counter'][0] = nan
    with pytest.raises(ValueError):
        EnergyLedger(counter_config(), state=state)


@pytest.mark.asyncio
async def test_monitoring_reads_share_unit_when_extras_disabled_and_no_writes():
    unit = FakeUnit()
    pump = HeatPump(unit, DeviceConfig(extended=False, curves=False))
    snap = await pump.async_update(telemetry_enabled=True)
    assert all(a in snap.samples for a in (0x4F,0x50,0x58,0x5C,0x5D,0x304))
    assert snap.value('input_power', pump.config) == 2.57
    assert not unit.writes
    assert all(count <= 16 for _,count in unit.reads)
    unit.fail_addresses.add(0x5C)
    failed = await pump.async_update(telemetry_enabled=True)
    assert 0x5C not in failed.raw and 0x5C not in failed.samples
    assert 0x58 in failed.raw


@pytest.mark.asyncio
async def test_slow_sample_times_not_relabelled_fresh():
    pump = HeatPump(FakeUnit())
    first = await pump.async_update()
    second = await pump.async_update()
    assert first.samples[0x130] == second.samples[0x130]
    assert second.samples[0x58].end >= first.samples[0x58].end
