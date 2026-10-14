"""Build an installation ZIP and complete source ZIP without caches or PDFs."""
from pathlib import Path
import argparse
import hashlib
import zipfile
import json

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'__pycache__', '.pytest_cache', '.git', '.venv', 'dist'}


def include(path):
    return (path.is_file() and not EXCLUDED.intersection(path.relative_to(ROOT).parts)
            and path.suffix not in ('.pyc', '.pdf'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    out = parser.parse_args().output
    out.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / 'custom_components/househeating/manifest.json').read_text())['version']
    install = out / f'househeating_modbus_v{version}.zip'
    full = out / f'househeating_modbus_project_v{version}.zip'
    with zipfile.ZipFile(install, 'w', zipfile.ZIP_DEFLATED) as archive:
        base = ROOT
        for path in sorted((base / 'custom_components').rglob('*')):
            if include(path):
                archive.write(path, path.relative_to(base))
        for name in ('README.md', 'assets/logo.png', 'INSTALLATIE.md', 'ENERGIEMONITORING.md', 'FUNCTIES.md', 'REGISTERS.md', 'SOURCES.md', 'TEST_REPORT.md', 'LICENSE'):
            archive.write(ROOT / name, name)
    with zipfile.ZipFile(full, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            if include(path) and path not in (install, full):
                archive.write(path, Path('househeating_modbus_project') / path.relative_to(ROOT))
    for path in (install, full):
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
        print(f'{path.name}: {path.stat().st_size} bytes; SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
