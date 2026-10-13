"""Adapter contract tests with explicit stubs, not a real HA runtime test."""
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from contract_stubs import Entry, HAError, install

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from fake_unit import FakeUnit


@pytest.fixture
def modules(monkeypatch):
    install(monkeypatch)
    monkeypatch.syspath_prepend(str(ROOT))
    prefix='custom_components.househeating'
    for key in list(sys.modules):
        if key.startswith(prefix):
            monkeypatch.delitem(sys.modules,key)
    names=['__init__','connection','config_flow','sensor','binary_sensor','number','select','switch','button','diagnostics']
    result={name:importlib.import_module(prefix if name=='__init__' else prefix+'.'+name) for name in names}
    yield result
    for key in list(sys.modules):
        if key.startswith(prefix):
            sys.modules.pop(key,None)


class Manager:
    def __init__(self):
        self.forwarded=[]
        self.reloads=[]
    async def async_forward_entry_setups(self,entry,platforms):
        self.forwarded=list(platforms)
    async def async_unload_platforms(self,entry,platforms):
        return True
    def async_update_entry(self,entry,**kwargs):
        for key,value in kwargs.items():setattr(entry,key,value)
    async def async_reload(self,entry_id):
        self.reloads.append(entry_id)


def harness(modules):
    data=modules['connection'].normalize_connection({'name':'HouseHeating','transport':'rtu_tcp',
                                                    'host':'192.0.2.1','port':502,'unit_id':1})
    options=importlib.import_module('custom_components.househeating.const').DEFAULT_OPTIONS.copy()
    entry=Entry(data,options)
    hass=SimpleNamespace(unit=FakeUnit(),shared_calls=[],temporary_calls=[],config_entries=Manager())
    return hass,entry


@pytest.mark.parametrize('transport,extra',[('tcp',{'host':'Example.LOCAL','port':502}),
                                          ('rtu_tcp',{'host':'2001:db8::1','port':8899}),
                                          ('serial',{'serial_device':'/dev/serial/by-id/test'})])
def test_transport_parameters(modules,transport,extra):
    data=modules['connection'].normalize_connection({'transport':transport,'unit_id':1,**extra})
    params=modules['connection'].connection_params(data)
    if transport=='tcp': assert params.endpoint==('tcp','example.local',502)
    if transport=='rtu_tcp': assert params.device=='socket://[2001:db8::1]:8899'
    if transport=='serial': assert (params.baudrate,params.bytesize,params.parity,params.stopbits)==(9600,8,'N',1)


@pytest.mark.parametrize('data',[{'transport':'tcp','host':'','unit_id':1},
                                 {'transport':'tcp','host':'https://pump','unit_id':1},
                                 {'transport':'tcp','host':'pump','unit_id':0},
                                 {'transport':'tcp','host':'pump','unit_id':248},
                                 {'transport':'serial','serial_device':'COM3','unit_id':1}])
def test_invalid_connection_rejected(modules,data):
    with pytest.raises(ValueError):modules['connection'].normalize_connection(data)


@pytest.mark.asyncio
async def test_setup_uses_shared_unit_and_no_writes(modules):
    hass,entry=harness(modules)
    assert await modules['__init__'].async_setup_entry(hass,entry)
    assert len(hass.shared_calls)==1
    assert len(hass.config_entries.forwarded)==6
    assert not hass.unit.writes
    assert len(entry.unload_callbacks)==1


@pytest.mark.asyncio
async def test_every_entity_constructs_and_controls_are_locked(modules):
    hass,entry=harness(modules)
    await modules['__init__'].async_setup_entry(hass,entry)
    for name in ('sensor','binary_sensor','number','select','switch','button'):
        entities=[]
        await modules[name].async_setup_entry(hass,entry,lambda values:entities.extend(values))
        assert entities
        assert len({e._attr_unique_id for e in entities})==len(entities)
        for entity in entities:
            assert entity.device_info['identifiers']=={('househeating','stable_entry')}
            assert isinstance(entity.available,bool)
            if name in ('number','select','switch'):assert not entity.available


@pytest.mark.asyncio
async def test_config_flow_is_read_only(modules):
    hass,entry=harness(modules)
    flow=modules['config_flow'].HouseHeatingConfigFlow()
    flow.hass=hass
    result=await flow.async_step_user(entry.data)
    assert result['type']=='create_entry'
    assert result['options']['allow_control'] is False
    assert hass.temporary_calls and not hass.unit.writes


@pytest.mark.asyncio
async def test_explicit_confirmation_required_and_never_writes(modules):
    hass,entry=harness(modules)
    flow=modules['config_flow'].HouseHeatingOptionsFlow()
    flow.hass,flow.config_entry=hass,entry
    result=await flow.async_step_init(entry.options|{'allow_control':True})
    assert result['step_id']=='confirm_control'
    result=await flow.async_step_confirm_control({'confirm_values':False})
    assert result['errors']['base']=='confirmation_required'
    result=await flow.async_step_confirm_control({'confirm_values':True})
    assert result['type']=='create_entry'
    assert result['data']['authorized_identity']==[404,0,1,130]
    assert not hass.unit.writes


@pytest.mark.asyncio
async def test_reconfigure_keeps_entity_identity_and_relocks(modules):
    hass,entry=harness(modules)
    await modules['__init__'].async_setup_entry(hass,entry)
    entity=modules['switch'].HouseHeatingPower(entry.runtime_data,'power')
    before=entity._attr_unique_id
    flow=modules['config_flow'].HouseHeatingConfigFlow()
    flow.hass,flow.test_entry=hass,entry
    result=await flow.async_step_reconfigure(entry.data|{'host':'192.0.2.2'})
    assert result['reason']=='reconfigure_successful'
    assert not entry.options['allow_control']
    after=modules['switch'].HouseHeatingPower(entry.runtime_data,'power')._attr_unique_id
    assert before==after
    assert hass.config_entries.reloads==['stable_entry']
    assert not hass.unit.writes


@pytest.mark.asyncio
async def test_read_failure_marks_entities_unavailable_and_recovery_works(modules):
    hass,entry=harness(modules)
    await modules['__init__'].async_setup_entry(hass,entry)
    r=importlib.import_module('custom_components.househeating._vendor.househeating_modbus').BY_KEY['water_outlet_temperature']
    entity=modules['sensor'].HouseHeatingSensor(entry.runtime_data,r)
    assert entity.available
    hass.unit.fail_addresses.add(0x300)
    await entry.runtime_data.async_refresh()
    assert not entity.available
    hass.unit.fail_addresses.clear()
    await entry.runtime_data.async_refresh()
    assert entity.available


@pytest.mark.asyncio
async def test_write_routes_to_allowlist_and_readback(modules):
    hass,entry=harness(modules)
    entry.options.update(allow_control=True,authorized_identity=[404,0,1,130])
    await modules['__init__'].async_setup_entry(hass,entry)
    from dataclasses import replace
    entry.runtime_data.device.config=replace(entry.runtime_data.device.config,verify_delay=0)
    number=modules['number'].HouseHeatingNumber(entry.runtime_data,'heating_setpoint')
    assert number.available
    await number.async_set_native_value(40)
    assert hass.unit.writes==[(0x301,400)]
    assert number.native_value==40


@pytest.mark.asyncio
async def test_diagnostics_redact_transport_details(modules):
    hass,entry=harness(modules)
    await modules['__init__'].async_setup_entry(hass,entry)
    from dataclasses import replace
    device=entry.runtime_data.device
    device.snapshot=replace(device.snapshot,errors={'test':'timeout at 192.0.2.1'})
    data=await modules['diagnostics'].async_get_config_entry_diagnostics(hass,entry)
    assert '192.0.2.1' not in str(data)
    assert data['registers']['0x0301']==350
