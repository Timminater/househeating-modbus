"""Narrow adapter test doubles, NOT an implementation of Home Assistant.

Only test our wiring and flow decisions. Real config-flow serialization,
registries, dependency loading, scheduling and device transport are not tested.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
import sys
from types import ModuleType, SimpleNamespace


class Generic:
    @classmethod
    def __class_getitem__(cls, item):
        return cls


class HAError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args or (kwargs.get('translation_key', ''),))
        self.details = kwargs


class UpdateFailed(Exception):
    pass


class Entry(Generic):
    def __init__(self, data, options):
        self.data, self.options = data, options
        self.entry_id = 'stable_entry'
        self.unique_id = data.get('connection_key', 'endpoint')
        self.title = data.get('name', 'HouseHeating')
        self.unload_callbacks = []

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)


class Coordinator(Generic):
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.last_update_success = True
        self.data = None

    async def async_refresh(self):
        try:
            self.data = await self._async_update_data()
            self.last_update_success = True
        except UpdateFailed:
            self.last_update_success = False

    async def async_config_entry_first_refresh(self):
        self.data = await self._async_update_data()
        self.last_update_success = True

    async def async_request_refresh(self):
        await self.async_refresh()

    def async_set_update_error(self, error):
        self.last_update_success = False


class CoordinatorEntity(Generic):
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self):
        return self.coordinator.last_update_success


class Flow:
    def __init_subclass__(cls, domain=None):
        super().__init_subclass__()

    async def async_set_unique_id(self, unique_id):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        return None

    def async_create_entry(self, **kwargs):
        return {'type': 'create_entry', **kwargs}

    def async_show_form(self, **kwargs):
        return {'type': 'form', **kwargs}

    def async_abort(self, **kwargs):
        return {'type': 'abort', **kwargs}

    def _async_current_entries(self):
        return []

    def _get_reconfigure_entry(self):
        return self.test_entry


@dataclass(frozen=True, kw_only=True)
class TcpParams:
    host: str
    port: int = 502

    @property
    def endpoint(self):
        return ('tcp', self.host, self.port)


@dataclass(frozen=True, kw_only=True)
class SerialParams:
    device: str
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = 'N'
    stopbits: int = 1
    framer: str = 'rtu'

    @property
    def endpoint(self):
        return ('serial', self.device)


def install(monkeypatch):
    def module(name, **attrs):
        m = ModuleType(name)
        m.__path__ = []
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, m)
        return m

    for n in ('homeassistant', 'homeassistant.components', 'homeassistant.helpers'):
        module(n)
    module('homeassistant.core', HomeAssistant=object, callback=lambda f: f)
    module('homeassistant.config_entries', ConfigEntry=Entry, ConfigFlow=Flow,
           OptionsFlowWithReload=Flow)
    module('homeassistant.exceptions', HomeAssistantError=HAError)
    platform=StrEnum('Platform', {n:n.lower() for n in ('SENSOR','BINARY_SENSOR','NUMBER','SELECT','SWITCH','BUTTON')})
    module('homeassistant.const', Platform=platform,
           UnitOfTemperature=StrEnum('UnitOfTemperature', {'CELSIUS':'°C'}))
    module('homeassistant.helpers.config_validation', config_entry_only_config_schema=lambda d: {})
    module('homeassistant.helpers.entity', EntityCategory=StrEnum('EntityCategory', {'DIAGNOSTIC':'diagnostic','CONFIG':'config'}))
    module('homeassistant.helpers.device_registry', DeviceInfo=dict)
    module('homeassistant.helpers.update_coordinator', DataUpdateCoordinator=Coordinator,
           CoordinatorEntity=CoordinatorEntity, UpdateFailed=UpdateFailed)
    for name,cls in (('sensor','SensorEntity'),('number','NumberEntity'),('select','SelectEntity'),
                     ('switch','SwitchEntity'),('binary_sensor','BinarySensorEntity'),('button','ButtonEntity')):
        extra={}
        if name=='sensor':
            extra={'SensorDeviceClass':StrEnum('SensorDeviceClass',{x.upper():x for x in ('temperature','frequency','voltage','current','power','energy','enum')}),
                   'SensorStateClass':StrEnum('SensorStateClass',{'MEASUREMENT':'measurement'})}
        if name=='number':
            extra={'NumberDeviceClass':StrEnum('NumberDeviceClass',{'TEMPERATURE':'temperature'}),
                   'NumberMode':StrEnum('NumberMode',{'BOX':'box'})}
        if name=='binary_sensor':
            extra={'BinarySensorDeviceClass':StrEnum('BinarySensorDeviceClass',{'PROBLEM':'problem'})}
        module(f'homeassistant.components.{name}', **{cls:type(cls,(),{}), **extra})
    module('modbus_connection', ModbusSerialParams=SerialParams, ModbusTcpParams=TcpParams)

    def unit(hass, entry, params, unit_id):
        hass.shared_calls.append((params,unit_id))
        return hass.unit
    @asynccontextmanager
    async def temporary(hass, params, unit_id):
        hass.temporary_calls.append((params,unit_id))
        yield hass.unit
    module('homeassistant.components.modbus', async_get_unit=unit, async_get_temporary_unit=temporary)
    module('probatio', Schema=lambda x:x, Required=lambda key,**kw:key,
           Optional=lambda key,**kw:key, All=lambda *args:args, Coerce=lambda x:x,
           Range=lambda **kw:kw)
    module('homeassistant.helpers.selector', SelectSelector=lambda x:x,
           SelectSelectorConfig=lambda **kw:kw,
           SelectSelectorMode=SimpleNamespace(DROPDOWN='dropdown'))
