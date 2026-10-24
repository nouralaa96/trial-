"""Inventory deliverable files and verify preserved inputs; never fetches data."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP = {'.venv', '__pycache__', '.pytest_cache', '.git', 'pytest_tmp', 'pytest_final'}
MANIFEST = ROOT / 'artifacts/full_manifest.json'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(root=ROOT):
    result = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(part in SKIP for part in path.relative_to(root).parts):
            continue
        if path == MANIFEST or path.suffix == '.zip':
            continue
        result[str(path.relative_to(root))] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    return result

def original_verification():
    source = Path('/workspace/trading-research-v2')
    expected = json.loads((ROOT/'artifacts/original_v2_hashes.json').read_text())
    if not source.is_dir():
        return {'status': 'original_location_not_present', 'expected_files': len(expected)}
    failures = [name for name, value in expected.items()
                if not (source/name).is_file() or digest(source/name) != value]
    return {'status': 'PASS' if not failures else 'FAIL', 'expected_files': len(expected),
            'failures': failures}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        expected = json.loads(MANIFEST.read_text())['files']
        actual = inventory()
        failures = [name for name, record in expected.items() if actual.get(name) != record]
        extras = sorted(set(actual)-set(expected))
        report = {'status': 'PASS' if not failures and not extras else 'FAIL',
                  'mismatched_or_missing': failures, 'unmanifested': extras,
                  'original': original_verification()}
        print(json.dumps(report, indent=2))
        return int(report['status'] != 'PASS' or report['original']['status'] == 'FAIL')
    original = original_verification()
    if original['status'] == 'FAIL':
        raise RuntimeError('Original project modification detected: '+str(original))
    files = inventory()
    payload = {'created_utc': datetime.now(timezone.utc).isoformat(),
               'hash': 'SHA256', 'excluded': sorted(SKIP)+['artifacts/full_manifest.json', '*.zip'],
               'original': original, 'file_count': len(files), 'files': files}
    MANIFEST.write_text(json.dumps(payload, indent=2)+'\n')
    print(json.dumps({'manifest': str(MANIFEST), 'files':len(files), 'original': original}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
