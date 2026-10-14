from dataclasses import replace
from datetime import datetime, timedelta
from math import nan
from zoneinfo import ZoneInfo
import pytest

from househeating_modbus.operation import CurveConfig, CurveModel, OperationLedger
from househeating_modbus.telemetry import MonitoringConfig, EnergyLedger, Reading, calculate
from househeating_modbus import DeviceConfig
from test_telemetry import BASE, sample, snapshot


def test_observed_starts_runtime_cycles_and_no_invented_startup():
    ledger=OperationLedger('Europe/Amsterdam',90)
    ledger.ingest(BASE,0,True)
    ledger.ingest(BASE+30,30,True)
    assert ledger.starts==0 and ledger.seconds==30
    ledger.ingest(BASE+60,60,False)
    assert ledger.completed_cycles==0  # partial first cycle is not a full observed cycle
    ledger.ingest(BASE+90,90,True)
    ledger.ingest(BASE+120,120,True)
    ledger.ingest(BASE+150,150,False)
    assert ledger.starts==1 and ledger.completed_cycles==1
    assert ledger.values(BASE+150)['compressor_cycle_average']==.5
    restored=OperationLedger('Europe/Amsterdam',90,ledger.export())
    restored.ingest(BASE+1000,1000,True)
    assert restored.starts==1 and restored.seconds==60


@pytest.mark.parametrize('invalid',[None,False])
def test_gap_or_unavailable_never_creates_start_or_offline_runtime(invalid):
    ledger=OperationLedger('Europe/Amsterdam',90)
    ledger.ingest(BASE,0,False)
    ledger.ingest(BASE+10,10,invalid)
    ledger.ingest(BASE+1000,1000,True)
    assert ledger.starts==0 and ledger.seconds==0


def test_operation_midnight_split_and_restart_totals():
    at=datetime(2026,10,25,tzinfo=ZoneInfo('Europe/Amsterdam')).timestamp()
    ledger=OperationLedger('Europe/Amsterdam',90)
    ledger.ingest(at-30,0,True)
    ledger.ingest(at+30,60,True)
    assert sorted(v[1] for v in ledger.days.values())==[30,30]
    assert OperationLedger('Europe/Amsterdam',90,ledger.export()).seconds==60


@pytest.mark.parametrize('field',['starts','seconds','completed_cycles','completed_seconds'])
def test_corrupt_operation_storage_does_not_reset_totals(field):
    state=OperationLedger('Europe/Amsterdam',90).export()
    state[field]=nan
    with pytest.raises(ValueError):
        OperationLedger('Europe/Amsterdam',90,state)


def test_weather_curve_endpoints_interpolation_and_no_automatic_default():
    cfg=CurveConfig(inertia_minutes=0)
    model=CurveModel(cfg)
    assert not cfg.enabled and not cfg.automatic
    assert model.calculate(-20,None,None,0,(20,60))['curve_advised_target']==50
    assert model.calculate(25,None,None,30,(20,60))['curve_advised_target']==25
    assert model.calculate(2.5,None,None,60,(20,60))['curve_advised_target']==38


def test_pv_hold_hysteresis_and_battery_reserve_priority():
    cfg=CurveConfig(pv_entity='sensor.pv',battery_entity='sensor.battery',hold_seconds=60,inertia_minutes=0)
    model=CurveModel(cfg)
    assert model.calculate(0,3,90,0,(20,60))['curve_offset']==0
    assert model.calculate(0,3,90,60,(20,60))['curve_offset']==3
    assert model.calculate(0,1.9,90,90,(20,60))['curve_offset']==3
    assert model.calculate(0,3,70,120,(20,60))['curve_offset']==3
    assert model.calculate(0,3,70,180,(20,60))['curve_offset']==-3
    assert model.calculate(0,3,83,240,(20,60))['curve_offset']==-3
    assert model.calculate(0,3,90,300,(20,60))['curve_offset']==-3
    assert model.calculate(0,3,90,360,(20,60))['curve_offset']==3


def test_curve_inertia_final_clamp_and_cooling_direction():
    model=CurveModel(CurveConfig(inertia_minutes=60,pv_entity='sensor.pv',pv_offset=10,hold_seconds=0))
    assert model.calculate(-15,3,None,0,(20,45))['curve_advised_target']==45
    assert model.calculate(20,3,None,60,(20,45))['curve_base_target']>49
    cooling=CurveModel(CurveConfig(target='cooling_setpoint',water_min=7,water_max=25,
                                  pv_entity='sensor.pv',hold_seconds=0,inertia_minutes=0))
    result=cooling.calculate(20,3,None,0,(7,25))
    assert result['curve_offset']==-3 and result['curve_advised_target']==22


@pytest.mark.parametrize('changes',[{'automatic':True},{'target':'power'}, {'outdoor_max':-20},
    {'water_min':60,'water_max':25},{'max_age':nan},{'pv_offset':20},{'battery_min_soc':120},
    {'cooldown_seconds':0},{'step_degrees':0},{'pv_hysteresis_kw':3}])
def test_invalid_curve_options_rejected(changes):
    with pytest.raises(ValueError):
        CurveConfig(**changes)


def test_missing_source_and_reset_drop_previous_corrections():
    model=CurveModel(CurveConfig(pv_entity='sensor.pv',hold_seconds=0))
    assert model.calculate(0,3,None,0,(20,60))['curve_offset']==3
    with pytest.raises(ValueError):
        model.calculate(0,None,None,30,(20,60))
    model.reset()
    assert model.active_offset==0 and model.last is None


def test_external_heat_source_does_not_require_hydraulic_confirmation():
    cfg=MonitoringConfig(enabled=True,thermal_source='external',external_heat_power='sensor.heat')
    snap=snapshot()
    snap=replace(snap,raw={k:v for k,v in snap.raw.items() if k not in (0x4F,0x50,0x58)})
    result=calculate(snap,DeviceConfig(),cfg,BASE,BASE,external_heat=Reading(6,BASE))
    assert result.thermal==6 and result.flow is None
    assert 'thermal_unconfirmed' not in result.reasons
    assert calculate(snap,DeviceConfig(),cfg,BASE+100,BASE+100,external_heat=Reading(6,BASE)).thermal is None


def test_external_heat_and_hydraulic_estimate_can_be_compared_without_mixing():
    cfg=MonitoringConfig(enabled=True,thermal_confirmed=True,thermal_source='external',external_heat_power='sensor.heat')
    result=calculate(snapshot(),DeviceConfig(),cfg,BASE,BASE,external_heat=Reading(6,BASE))
    assert result.thermal==result.external_thermal==6
    assert result.flow==20 and result.hydraulic_thermal==pytest.approx(6.9666666667)
    ledger=EnergyLedger(cfg)
    ledger.ingest(result)
    ledger.ingest(replace(result,at=BASE+30,monotonic=BASE+30))
    assert ledger.totals['delivered']==pytest.approx(.05)


def test_long_periods_use_summed_paired_energy_and_keep_true_overall():
    zone=ZoneInfo('Europe/Amsterdam')
    start=datetime(2025,1,1,tzinfo=zone).timestamp()
    ledger=EnergyLedger(MonitoringConfig())
    ledger.ingest(sample(start))
    for day in range(400):
        at=(datetime(2025,1,1,tzinfo=zone)+timedelta(days=day)).timestamp()
        b=ledger.bucket(at,'day')
        ledger.pair(b,'heat',6 if day%2 else 4,0,2,3600)
    now=(datetime(2025,1,1,tzinfo=zone)+timedelta(days=399,hours=2)).timestamp()
    values=ledger.values(now)
    assert values['heating_electricity_paired_overall']==800
    assert values['cop_overall']==2.5
    assert values['heating_electricity_paired_365d']==730
    assert values['cop_yesterday']==2
    assert len(ledger.history)<=370
    restored=EnergyLedger(ledger.config,state=ledger.export())
    assert restored.values(now)['cop_overall']==2.5
    assert restored.values(now)['cop_7d']==pytest.approx(values['cop_7d'])


@pytest.mark.asyncio
async def test_diagnostics_fallback_uses_shared_unit_without_writes():
    from fake_unit import FakeUnit
    from househeating_modbus import HeatPump
    unit=FakeUnit()
    pump=HeatPump(unit,DeviceConfig(extended=False,curves=False))
    result=await pump.async_update(diagnostics_enabled=True)
    assert 0x19 in result.samples and 0x1A in result.samples
    assert not unit.writes
