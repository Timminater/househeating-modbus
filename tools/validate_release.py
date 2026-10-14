"""Validate HACS layout and import the install ZIP in isolation with real HA.

Run using requirements-test-runtime.txt after tools/package.py.
No gateway or physical device is contacted.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/househeating'


def main():
    hacs = json.loads((ROOT / 'hacs.json').read_text())
    manifest = json.loads((COMPONENT / 'manifest.json').read_text())
    assert hacs['name'] == manifest['name']
    assert hacs['render_readme'] is True
    assert hacs['homeassistant'] == '2026.10.1'
    assert not hacs.get('content_in_root', False)
    assert not hacs.get('zip_release', False)  # HACS uses the release source tree.
    assert [p.name for p in (ROOT / 'custom_components').iterdir() if p.is_dir() and p.name != '__pycache__'] == ['househeating']
    for key in ('domain', 'documentation', 'issue_tracker', 'codeowners', 'name', 'version'):
        assert manifest[key], key
    assert manifest['config_flow'] is True and manifest['dependencies'] == ['modbus']
    for path in COMPONENT.rglob('*.json'):
        json.loads(path.read_text(encoding='utf-8'))
    source = ROOT / 'device_library/src/househeating_modbus'
    for path in source.iterdir():
        if path.is_file():
            assert path.read_bytes() == (COMPONENT / '_vendor/househeating_modbus' / path.name).read_bytes(), path.name
    archive_path = ROOT / 'dist' / f"househeating_modbus_v{manifest['version']}.zip"
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        for name in ('manifest.json', '__init__.py', 'config_flow.py', 'climate.py', 'water_heater.py',
                     'monitoring.py', 'operation.py', 'dashboard.py', 'services.yaml',
                     '_vendor/househeating_modbus/operation.py', '_vendor/househeating_modbus/telemetry.py',
                     '_vendor/househeating_modbus/controls.py', 'translations/nl.json',
                     'translations/en.json', 'brand/icon.png', 'brand/icon@2x.png'):
            assert 'custom_components/househeating/' + name in names, name
        assert not any('__pycache__' in name or 'core_integration' in name for name in names)
        for path in COMPONENT.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                rel = path.relative_to(ROOT).as_posix()
                assert archive.read(rel) == path.read_bytes(), rel
        with tempfile.TemporaryDirectory(prefix='househeating-zip-check-', dir=ROOT.parent) as folder:
            archive.extractall(folder)
            code = '''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
for part in ('', '.config_flow', '.climate', '.water_heater', '.sensor', '.binary_sensor',
             '.number', '.select', '.switch', '.button', '.diagnostics', '.monitoring', '.operation', '.dashboard'):
    importlib.import_module('custom_components.househeating' + part)
from custom_components.househeating.config_flow import connection_schema
import probatio
assert isinstance(connection_schema({}), probatio.Schema)
from custom_components.househeating._vendor.househeating_modbus.telemetry import MonitoringConfig
assert MonitoringConfig.from_options({}).enabled is False
from custom_components.househeating._vendor.househeating_modbus.operation import CurveConfig
assert CurveConfig.from_options({}).enabled is False
assert CurveConfig.from_options({}).automatic is False
from custom_components.househeating.sensor import MONITORING_SENSORS,OPERATION_SENSORS
from custom_components.househeating._vendor.househeating_modbus.operation import RELAY_FLAGS
for name in ('strings.json','translations/nl.json','translations/en.json'):
    labels=json.loads((Path(sys.argv[1])/'custom_components/househeating'/name).read_text(encoding='utf-8'))
    assert set(MONITORING_SENSORS)|set(OPERATION_SENSORS) <= set(labels['entity']['sensor'])
    assert set(RELAY_FLAGS) <= set(labels['entity']['binary_sensor'])
import yaml
from homeassistant.helpers.selector import validate_selector
services=yaml.safe_load((Path(sys.argv[1])/'custom_components/househeating/services.yaml').read_text(encoding='utf-8'))
validate_selector(services['generate_dashboard']['fields']['entry_id']['selector'])
from PIL import Image
for name, size in (('icon.png', 256), ('icon@2x.png', 512)):
    with Image.open(Path(sys.argv[1]) / 'custom_components/househeating/brand' / name) as im:
        assert im.size == (size, size) and im.mode == 'RGBA'
print('Isolated install ZIP: all platform imports, schema and brand images passed')
'''
            subprocess.run([sys.executable, '-I', '-c', code, folder], cwd=folder, check=True)
    print('HACS metadata/layout, JSON, vendor parity and installation contents passed')


if __name__ == '__main__':
    main()
