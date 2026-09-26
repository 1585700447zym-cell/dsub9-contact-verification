"""Fail-closed selection of the already qualified, isolated MuJoCo runtime."""
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / 'deliverables/native313_validation/compatibility_3.13.0.json'


def verify_digest(path, expected):
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(f'SHA256 mismatch: {path}')
    return actual


def validate_module(module, expected_file):
    if module.__version__ != '3.13.0':
        raise RuntimeError('Unqualified MuJoCo version')
    if Path(module.__file__).resolve() != Path(expected_file).resolve():
        raise RuntimeError('Unqualified MuJoCo module path')


def verify_runtime(package_path: Path) -> dict:
    record = json.loads(RECORD.read_text(encoding='utf-8'))
    expected = Path(record['module_file']).resolve()
    package = Path(package_path).resolve()
    if package / 'mujoco/__init__.py' != expected or not expected.is_file():
        raise RuntimeError('Use the exact qualified package path')
    loaded = sys.modules.get('mujoco')
    if loaded is not None:
        try:
            validate_module(loaded, expected)
        except RuntimeError as exc:
            raise RuntimeError('Another MuJoCo runtime is already imported; start a fresh process') from exc
    # Verify before native code is loaded, including repeated calls.
    dlls = {str(Path(p).resolve()): verify_digest(p, digest)
            for p, digest in record['dll_sha256'].items()}
    if loaded is None:
        sys.path.insert(0, str(package))
        loaded = importlib.import_module('mujoco')
    validate_module(loaded, expected)
    return {'version': loaded.__version__, 'module_file': str(expected),
            'dll_verified': True, 'dll_sha256': dlls,
            'compatibility_record_sha256': hashlib.sha256(RECORD.read_bytes()).hexdigest()}
