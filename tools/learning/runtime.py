"""Fail-closed selection of the already qualified, isolated MuJoCo runtime."""
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / 'deliverables/native313_validation/compatibility_3.13.0.json'
_selection = None


def _selected_record(path, expected_digest):
    verify_digest(path, expected_digest)
    record = json.loads(Path(path).read_text(encoding='utf-8'))
    if record.get('version') != 'native313_repair_runtime_v1':
        raise RuntimeError('Unregistered runtime record schema')
    expected = Path(record['module_file']).resolve()
    if expected.name != '__init__.py' or expected.parent.name != 'mujoco':
        raise RuntimeError('Invalid runtime module location')
    package = expected.parent.parent
    files = record['files']
    if not {'mujoco/__init__.py', 'mujoco/mujoco.dll'}.issubset(files):
        raise RuntimeError('Incomplete native package record')
    for name, digest in files.items():
        target = (package/name).resolve()
        if Path(name).is_absolute() or not target.is_relative_to(package/'mujoco'):
            raise RuntimeError('Runtime file escapes package')
        verify_digest(target, digest)
    actual = {p.relative_to(package).as_posix() for p in (package/'mujoco').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    if actual != set(files):
        raise RuntimeError('Runtime package inventory changed')
    return record, package, expected


def select_runtime(record_path, *, expected_digest):
    """Explicit pinned selection before environment imports; immutable per process."""
    global _selection
    selected = (Path(record_path).resolve(), expected_digest)
    if _selection is not None and _selection != selected:
        raise RuntimeError('Cannot switch runtime in an existing process')
    _, _, expected = _selected_record(*selected)
    loaded = sys.modules.get('mujoco')
    if loaded is not None:
        validate_module(loaded, expected)
    _selection = selected


def active_package():
    return _selected_record(*_selection)[1] if _selection else ROOT/'tmp/mujoco_3_13_probe'


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
    if _selection is not None:
        record, package, expected = _selected_record(*_selection)
        if Path(package_path).resolve() != package:
            raise RuntimeError('Use the explicitly selected package path')
        loaded = sys.modules.get('mujoco')
        if loaded is None:
            sys.path.insert(0, str(package))
            loaded = importlib.import_module('mujoco')
        validate_module(loaded, expected)
        return dict(version=loaded.__version__, module_file=str(expected), dll_verified=True,
            dll_sha256={str(package/name): digest for name,digest in record['files'].items()
                        if Path(name).suffix.lower() in ('.dll','.pyd')},
            compatibility_record_sha256=_selection[1], package_files_verified=len(record['files']))
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
