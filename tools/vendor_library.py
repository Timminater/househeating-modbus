"""Bundle our own device library and refresh the Core-development copy."""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'device_library/src/househeating_modbus'
CUSTOM = ROOT / 'custom_components/househeating'
VENDOR = CUSTOM / '_vendor/househeating_modbus'
CORE = ROOT / 'core_integration/homeassistant/components/househeating'
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache')


def main():
    if VENDOR.exists():
        shutil.rmtree(VENDOR)
    shutil.copytree(SOURCE, VENDOR, ignore=IGNORE)
    if CORE.exists():
        shutil.rmtree(CORE)
    CORE.mkdir(parents=True)
    for source in CUSTOM.iterdir():
        if source.name in ('_vendor', '__pycache__', 'translations'):
            continue
        if source.is_file():
            text = source.read_text(encoding='utf-8')
            if source.suffix == '.py':
                text = text.replace('from ._vendor.househeating_modbus', 'from househeating_modbus')
            (CORE / source.name).write_text(text, encoding='utf-8')
    manifest = json.loads((CORE / 'manifest.json').read_text())
    manifest.pop('version')
    # This dependency is deliberately NOT used by the installable custom build.
    # Publication and maintainer review are prerequisites for the Core draft.
    version = json.loads((CUSTOM / 'manifest.json').read_text())['version']
    manifest['requirements'] = [f'househeating-modbus=={version}']
    (CORE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy2(ROOT / 'device_library/tests/fake_unit.py', ROOT / 'tests/fake_unit.py')
    print('Own library synchronized; Core draft refreshed.')


if __name__ == '__main__':
    main()
