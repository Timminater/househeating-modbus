"""Real HA schema, source events, sensor metadata and durable publication tests."""
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.helpers.storage import Store
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from test_real_runtime import harness
from custom_components.househeating import config_flow, monitoring
from custom_components.househeating.sensor import MonitoringSensor, MONITORING_SENSORS, HouseHeatingSensor
from custom_components.househeating._vendor.househeating_modbus.telemetry import MonitoringConfig, EnergyLedger, Sample
from custom_components.househeating._vendor.househeating_modbus import BY_KEY


class MemoryStore:
    def __init__(self):
        self.saved = None
        self.fail = False
    async def async_load(self):
        return deepcopy(self.saved)
    async def async_save(self, value):
        if self.fail:
            raise OSError('simulated disk failure')
        self.saved = deepcopy(value)


async def manager(tmp_path, monkeypatch, **kwargs):
    coordinator, unit = await harness(tmp_path, authorized=False)
    unit.data[0x58] = 20
    config = MonitoringConfig(enabled=True, thermal_confirmed=True, **kwargs)
    mgr = monitoring.MonitoringManager(coordinator.hass, coordinator, config)
    mgr.store = MemoryStore()
    mgr._schedule = lambda: None
    coordinator.monitoring = mgr
    return mgr, coordinator, unit


@pytest.mark.asyncio
async def test_monitoring_runs_locked_without_modbus_writes(tmp_path, monkeypatch):
    mgr, coordinator, unit = await manager(tmp_path, monkeypatch)
    await coordinator.async_refresh()
    assert not coordinator.device.control_ready
    assert mgr.values()['thermal_power_estimated'] is not None
    assert mgr.store.saved is not None and not unit.writes


@pytest.mark.asyncio
async def test_storage_failure_never_publishes_candidate_and_recovers(tmp_path, monkeypatch):
    mgr, coordinator, _ = await manager(tmp_path, monkeypatch)
    clock = [datetime.now(timezone.utc).timestamp()]
    monkeypatch.setattr(monitoring, 'time', lambda: clock[0])
    monkeypatch.setattr(monitoring, 'monotonic', lambda: clock[0])
    # Normalize the real device samples to the deterministic test clock.
    snapshot = coordinator.device.snapshot
    windows = {a: replace(w, start=clock[0], end=clock[0], monotonic_end=clock[0])
               for a,w in snapshot.samples.items()}
    mgr.snapshot = replace(snapshot, samples=windows)
    await mgr.async_process()
    first = deepcopy(mgr.ledger.export())
    clock[0] += 30
    mgr.store.fail = True
    await mgr.async_process()
    assert mgr.ledger.export() == first
    assert mgr.values()['monitoring_status'] == 'storage_error'
    assert mgr.values()['cop_instant'] is None
    mgr.store.fail = False
    clock[0] += 30
    await mgr.async_process()
    assert mgr.ledger.totals['electric'] == 0  # no bridge across the failed publication
    assert not mgr.storage_error


@pytest.mark.asyncio
async def test_real_store_roundtrip_no_offline_thermal_bridge(tmp_path, monkeypatch):
    mgr, coordinator, _ = await manager(tmp_path, monkeypatch)
    mgr.store = Store(coordinator.hass, 1, 'househeating.test-monitoring')
    now = datetime.now(timezone.utc).timestamp()
    mgr.ledger.ingest(Sample(now-30,100,power=2,thermal=6,mode=1))
    mgr.ledger.ingest(Sample(now,130,power=2,thermal=6,mode=1))
    await mgr.store.async_save(mgr.ledger.export())
    restored = monitoring.MonitoringManager(coordinator.hass,coordinator,mgr.config)
    restored.store = mgr.store
    await restored.async_load()
    assert restored.ledger.totals == mgr.ledger.totals
    assert restored.ledger.previous is None
    await restored.async_close()


@pytest.mark.asyncio
async def test_monitoring_metadata_and_existing_identities(tmp_path, monkeypatch):
    mgr, coordinator, _ = await manager(tmp_path, monkeypatch)
    await coordinator.async_refresh()
    originals = {r.key: HouseHeatingSensor(coordinator,r).unique_id for r in BY_KEY.values()}
    for key, description in MONITORING_SENSORS.items():
        entity = MonitoringSensor(coordinator,key,*description)
        assert entity.unique_id == coordinator.entry.entry_id + '_' + key
        if description[2] == 'total':
            assert entity.state_class == SensorStateClass.TOTAL
            assert entity.device_class == SensorDeviceClass.ENERGY
        if key.endswith(('_day','_month')) and description[2] == 'total':
            assert entity.last_reset.tzinfo is not None
    assert HouseHeatingSensor(coordinator,BY_KEY['reported_energy']).state_class is None
    assert {r.key: HouseHeatingSensor(coordinator,r).unique_id for r in BY_KEY.values()} == originals


@pytest.mark.asyncio
async def test_cumulative_totals_readable_offline_current_values_invalid(tmp_path, monkeypatch):
    mgr, coordinator, unit = await manager(tmp_path,monkeypatch)
    await coordinator.async_refresh()
    unit.connected = False
    await mgr.async_failure()
    cumulative = MonitoringSensor(coordinator,'electrical_energy_total',*MONITORING_SENSORS['electrical_energy_total'])
    instant = MonitoringSensor(coordinator,'thermal_power_estimated',*MONITORING_SENSORS['thermal_power_estimated'])
    assert cumulative.available and not instant.available


@pytest.mark.asyncio
async def test_source_events_include_unchanged_reports_and_cleanup(tmp_path,monkeypatch):
    coordinator,_ = await harness(tmp_path,authorized=False)
    cfg = MonitoringConfig(enabled=True,source='external', external_power='sensor.meter_power')
    mgr = monitoring.MonitoringManager(coordinator.hass,coordinator,cfg)
    mgr.store = MemoryStore()
    coordinator.monitoring = mgr
    mgr.start()
    hass = coordinator.hass
    attrs = {'device_class':'power','unit_of_measurement':'W'}
    hass.states.async_set('sensor.meter_power','2000',attrs)
    await hass.async_block_till_done()
    assert mgr.values()['selected_electrical_power'] == 2
    saved = mgr.ledger.previous.at
    await asyncio.sleep(.01)
    hass.states.async_set('sensor.meter_power','2000',attrs)
    await hass.async_block_till_done()
    assert mgr.ledger.previous.at > saved
    await mgr.async_close()
    frozen = deepcopy(mgr.store.saved)
    hass.states.async_set('sensor.meter_power','3000',attrs)
    await hass.async_block_till_done()
    assert mgr.store.saved == frozen and not mgr._tasks


@pytest.mark.asyncio
async def test_stale_source_and_restored_state_rejected(tmp_path,monkeypatch):
    mgr, coordinator,_ = await manager(tmp_path,monkeypatch,source='external', external_power='sensor.meter')
    hass=coordinator.hass
    hass.states.async_set('sensor.meter','2000',{'unit_of_measurement':'W','device_class':'power','restored':True})
    await mgr.async_process()
    assert mgr.values()['selected_electrical_power'] is None
    hass.states.async_set('sensor.meter','2000',{'unit_of_measurement':'W','device_class':'power'})
    await mgr.async_process()
    assert mgr.values()['selected_electrical_power'] == 2
    clock=datetime.now(timezone.utc).timestamp()+100
    monkeypatch.setattr(monitoring,'time',lambda:clock)
    await mgr.async_process()
    assert mgr.values()['selected_electrical_power'] is None


async def options_flow(tmp_path,monkeypatch):
    coordinator,_ = await harness(tmp_path)
    hass=coordinator.hass
    hass.config_entries=ConfigEntries(hass,{})
    from homeassistant.helpers import entity_registry as er, device_registry as dr
    dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    options={'allow_control':True,'authorized_identity':[404,0,1,130],
             'measurement_divisor':1,'unknown_future_option':'preserve'}
    entry=ConfigEntry(version=1,minor_version=1,domain='househeating',title='Test',data={'name':'Test'},
                      options=options,source='user',unique_id='test',discovery_keys=MappingProxyType({}),subentries_data=None)
    hass.config_entries=ConfigEntries(hass,{})
    monkeypatch.setattr(hass.config_entries,'async_get_known_entry',lambda _:entry)
    monkeypatch.setattr(hass.config_entries,'async_get_entry',lambda entry_id:entry if entry_id == entry.entry_id else None)
    flow=config_flow.HouseHeatingOptionsFlow()
    flow.hass,flow.handler=hass,entry.entry_id
    return flow,entry


@pytest.mark.asyncio
async def test_monitoring_options_never_probe_or_change_commissioning(tmp_path,monkeypatch):
    flow,entry=await options_flow(tmp_path,monkeypatch)
    probe=AsyncMock(side_effect=AssertionError('monitoring must never probe/control'))
    monkeypatch.setattr(config_flow,'probe',probe)
    menu=await flow.async_step_init()
    assert set(menu['menu_options']) == {'control','monitoring','operation','weather_curve'}
    form=await flow.async_step_monitoring()
    inputs=form['data_schema']({'enabled':True,'thermal_confirmed':True})
    result=await flow.async_step_monitoring(inputs)
    for key,value in entry.options.items():
        assert result['data'][key] == value
    assert result['data']['monitoring']['enabled']
    probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_sources_validate_units_and_allow_clearing_counter(tmp_path,monkeypatch):
    flow,entry=await options_flow(tmp_path,monkeypatch)
    attrs={'device_class':'power','unit_of_measurement':'W'}
    flow.hass.states.async_set('sensor.power','2000',attrs)
    flow.hass.states.async_set('sensor.kwh','100',{'device_class':'energy','unit_of_measurement':'kWh'})
    data=asdict(MonitoringConfig(enabled=True,source='external',external_power='sensor.power',external_energy='sensor.kwh'))
    result=await flow.async_step_monitoring(data)
    assert result['data']['monitoring']['external_energy']=='sensor.kwh'
    data['external_energy']=None
    cleared=await flow.async_step_monitoring(data)
    assert cleared['data']['monitoring']['external_energy']==''
    flow.hass.states.async_set('sensor.power','2000',{'device_class':'power','unit_of_measurement':'V'})
    invalid=await flow.async_step_monitoring(data)
    assert invalid['errors']['base']=='invalid_monitoring'


@pytest.mark.asyncio
async def test_own_derived_power_cannot_be_selected_as_external_source(tmp_path,monkeypatch):
    flow,entry=await options_flow(tmp_path,monkeypatch)
    from homeassistant.helpers import entity_registry as er
    registry=er.async_get(flow.hass)
    entity=registry.async_get_or_create('sensor','househeating',entry.entry_id+'_thermal_power_estimated',
                                       config_entry=entry,suggested_object_id='thermal_estimate')
    flow.hass.states.async_set(entity.entity_id,'6',{'device_class':'power','unit_of_measurement':'kW'})
    inputs=asdict(MonitoringConfig(enabled=True,source='external',external_power=entity.entity_id))
    result=await flow.async_step_monitoring(inputs)
    assert result['errors']['base']=='invalid_monitoring'


@pytest.mark.asyncio
async def test_watchdog_expires_values_without_a_new_device_poll(tmp_path,monkeypatch):
    mgr,coordinator,_=await manager(tmp_path,monkeypatch)
    clock=[datetime.now(timezone.utc).timestamp()]
    monkeypatch.setattr(monitoring,'time',lambda:clock[0])
    monkeypatch.setattr(monitoring,'monotonic',lambda:clock[0])
    snapshot=coordinator.device.snapshot
    snapshot=replace(snapshot,raw=dict(snapshot.raw)|{0x58:20},samples={
        a:replace(w,start=clock[0],end=clock[0],monotonic_end=clock[0]) for a,w in snapshot.samples.items()})
    callbacks=[]
    monkeypatch.setattr(monitoring,'async_track_point_in_utc_time',
                        lambda hass,action,when: (callbacks.append((action,when)) or (lambda:None)))
    mgr._schedule=lambda:monitoring.MonitoringManager._schedule(mgr)
    await mgr.async_snapshot(snapshot)
    assert mgr.values()['thermal_power_estimated'] is not None
    action,deadline=callbacks[-1]
    clock[0]=deadline.timestamp()+.1
    action(deadline)
    await coordinator.hass.async_block_till_done()
    assert mgr.values()['thermal_power_estimated'] is None
    assert mgr.values()['cop_instant'] is None
    await mgr.async_close()


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_real_setup_and_unload_monitoring_lifecycle(tmp_path,monkeypatch,enabled):
    import custom_components.househeating as integration
    from homeassistant.core import HomeAssistant
    from fake_unit import FakeUnit
    hass=HomeAssistant(str(tmp_path))
    hass.config_entries=ConfigEntries(hass,{})
    forward=AsyncMock()
    unload=AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries,'async_forward_entry_setups',forward)
    monkeypatch.setattr(hass.config_entries,'async_unload_platforms',unload)
    unit=FakeUnit()
    unit.data[0x58]=20
    monkeypatch.setattr(integration,'async_get_unit',lambda *args:unit)
    entry=ConfigEntry(version=1,minor_version=1,domain='househeating',title='Test',
                      data={'name':'Test','transport':'tcp','host':'192.0.2.1','port':502,'unit_id':1},
                      options={'monitoring':{'enabled':enabled,'thermal_confirmed':True}},
                      source='user',unique_id='setup-test',discovery_keys=MappingProxyType({}),subentries_data=None)
    from homeassistant.config_entries import ConfigEntryState
    entry._async_set_state(hass,ConfigEntryState.SETUP_IN_PROGRESS,None)
    assert await integration.async_setup_entry(hass,entry)
    forward.assert_awaited_once()
    mgr=entry.runtime_data.monitoring
    assert (mgr is not None) is enabled
    if enabled:
        assert mgr.values()['thermal_power_estimated'] is not None
        assert mgr._timer is not None
    assert not unit.writes
    assert await integration.async_unload_entry(hass,entry)
    if enabled:
        assert mgr._closed
    await entry.runtime_data.async_shutdown()
