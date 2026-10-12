"""Retain native binaries and reproducible source/build identity after validation."""
import difflib
import json
from pathlib import Path
import shutil
import subprocess
from probe import HERE, ROOT, write
from validate_candidate import sha

source = ROOT/'tmp/mujoco_3_13_horizon_source'
commit = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'], text=True).strip()
assert commit == '123347c0eeab7e13c8da0828ab593bbd95bcf335'
original = (HERE/'upstream/engine_collision_gjk.c').read_text()
fixed = (HERE/'engine_collision_gjk_fixed.c').read_text(encoding='utf-8')
assert (source/'src/engine/engine_collision_gjk.c').read_text(encoding='utf-8') == fixed
from patch_horizon import patch
assert patch(original) == fixed
diff = ''.join(difflib.unified_diff(original.splitlines(True),fixed.splitlines(True),
    fromfile='a/src/engine/engine_collision_gjk.c',tofile='b/src/engine/engine_collision_gjk.c'))
(HERE/'horizon_capacity.patch').write_text(diff,encoding='utf-8')
destination = HERE/'native_binaries'
destination.mkdir(exist_ok=True)
binaries = {}
for label in ('horizon_fixed','horizon_control02'):
    record = json.loads((HERE/(label+'_runtime.json')).read_text(encoding='utf-8'))
    dll = Path(record['package'])/'mujoco/mujoco.dll'
    assert sha(dll) == record['files']['mujoco/mujoco.dll']
    target = destination/(label+'.dll')
    if target.exists():
        assert sha(target) == sha(dll)
    else:
        shutil.copy2(dll,target)
    binaries[label] = dict(path=target.relative_to(HERE).as_posix(),sha256=sha(target),
                          runtime_manifest=label+'_runtime.json')
build = ROOT/'tmp/mujoco_3_13_horizon_build'
write(HERE/'build.json',dict(source_repository='https://github.com/google-deepmind/mujoco.git',
    tag='3.13.0',commit=commit,source_file='src/engine/engine_collision_gjk.c',
    original_source_sha256=sha(HERE/'upstream/engine_collision_gjk.c'),
    fixed_source_sha256=sha(HERE/'engine_collision_gjk_fixed.c'),patch_sha256=sha(HERE/'horizon_capacity.patch'),
    generator='Visual Studio 18 2026',architecture='x64',configuration='Release',
    configure_options=dict(MUJOCO_BUILD_EXAMPLES='OFF',MUJOCO_BUILD_SIMULATE='OFF',
        MUJOCO_BUILD_TESTS='OFF',BUILD_TESTING='OFF',MUJOCO_TEST_PYTHON_UTIL='OFF',MUJOCO_USE_FILAMENT='OFF'),
    cmake_cache_sha256=sha(build/'CMakeCache.txt'),
    compiler_configurations={p.relative_to(build).as_posix():p.read_text(encoding='utf-8')
        for pattern in ('CMakeCCompiler.cmake','CMakeCXXCompiler.cmake') for p in (build/'CMakeFiles').rglob(pattern)},
    build_logs={name:sha(HERE/name) for name in ('full_build.log','control_build.log','control_build_02.log')},
    binaries=binaries,first_control_build_invalid=True,
    build_directory_latest_binary='unpatched control; use named retained binary by digest',
    package_origin='Original qualified Python package copied unchanged, only main mujoco.dll replaced',
    training_admitted=False))
write(HERE/'manifest.json',dict(version='native_crash_repair_v1',files={
    p.relative_to(HERE).as_posix():sha(p) for p in sorted(HERE.rglob('*'))
    if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}))
print(json.dumps(dict(commit=commit,binaries=binaries),indent=2))
