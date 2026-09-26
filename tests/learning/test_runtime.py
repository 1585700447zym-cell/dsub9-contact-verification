"""Wrong runtime paths, DLLs and already imported versions must fail closed."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'tmp/mujoco_3_13_probe'


def run_script(body):
    return subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', body], cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8')


def test_exact_runtime_loads_and_reports_fingerprint():
    result = run_script("from tools.learning.runtime import verify_runtime; from pathlib import Path; "
                        "r=verify_runtime(Path('tmp/mujoco_3_13_probe')); "
                        "assert r['version']=='3.13.0'; assert r['dll_verified']; print('verified')")
    assert result.returncode == 0, result.stderr
    assert 'verified' in result.stdout


def test_wrong_path_rejected_before_import():
    result = run_script("from tools.learning.runtime import verify_runtime; from pathlib import Path; "
                        "verify_runtime(Path('missing_runtime'))")
    assert result.returncode != 0
    assert 'qualified package path' in result.stderr


def test_already_imported_other_runtime_rejected():
    # Do not assume that the caller's isolated environment installs old MuJoCo.
    # Only this fresh negative-test child loads the explicitly archived 3.9 path.
    result = run_script("""
import json, sys
from pathlib import Path
from tools.learning.runtime import verify_runtime, verify_digest
record = json.loads(Path('deliverables/native313_validation/compatibility_3.9.0.json').read_text(encoding='utf-8'))
for path, digest in record['dll_sha256'].items():
    verify_digest(path, digest)
sys.path.insert(0, str(Path(record['module_file']).parents[1]))
import mujoco
assert mujoco.__version__ == record['mujoco_version']
assert Path(mujoco.__file__).resolve() == Path(record['module_file']).resolve()
verify_runtime(Path('tmp/mujoco_3_13_probe'))
""")
    assert result.returncode != 0
    assert 'already imported' in result.stderr


def test_wrong_dll_digest_rejected(tmp_path):
    from tools.learning.runtime import verify_digest
    import pytest
    dll = tmp_path / 'fake.dll'
    dll.write_bytes(b'not the qualified DLL')
    with pytest.raises(RuntimeError, match='SHA256'):
        verify_digest(dll, '0' * 64)


def test_wrong_version_rejected():
    from types import SimpleNamespace
    from tools.learning.runtime import validate_module
    import pytest
    with pytest.raises(RuntimeError, match='version'):
        validate_module(SimpleNamespace(__version__='3.9.0', __file__=str(PACKAGE/'mujoco/__init__.py')),
                        PACKAGE/'mujoco/__init__.py')
