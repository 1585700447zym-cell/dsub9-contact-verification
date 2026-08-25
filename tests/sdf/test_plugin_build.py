import ctypes
from contextlib import contextmanager
import functools
import msvcrt
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pytest

from tools.sdf.hole_reference import HoleParams, hole_distance, hole_gradient


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "plugins" / "dsub9_hole_sdf"
BUILD = ROOT / "build" / "dsub9_hole_sdf"
PLUGIN_RELATIVE_PATH = Path("build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll")
PARAMS = HoleParams(0.000575, 0.000675, 0.00025, 0.00450, 0.00100)
PARAM_ARRAY = (ctypes.c_double * 5)(
    PARAMS.bore_radius,
    PARAMS.entry_radius,
    PARAMS.entry_depth,
    PARAMS.bore_depth,
    PARAMS.outer_radius,
)
DEFAULT_CONFIG = {
    "bore_radius": "0.000575",
    "entry_radius": "0.000675",
    "entry_depth": "0.00025",
    "bore_depth": "0.00450",
    "outer_radius": "0.00100",
}

MUJOCO_PROBE = r"""
import mujoco

import ctypes
from pathlib import Path
import sys

PLUGIN_NAME = b"mujoco.sdf.dsub9_hole"
ATTRIBUTE_NAMES = (
    b"bore_radius",
    b"entry_radius",
    b"entry_depth",
    b"bore_depth",
    b"outer_radius",
)
PLUGIN_PATH = Path("build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll")


class PluginPrefix(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("nattribute", ctypes.c_int),
        ("attributes", ctypes.POINTER(ctypes.c_char_p)),
    ]


core = ctypes.WinDLL(str(Path(mujoco.__file__).resolve().parent / "mujoco.dll"))
core.mjp_getPlugin.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
core.mjp_getPlugin.restype = ctypes.POINTER(PluginPrefix)


def find_plugin():
    slot = ctypes.c_int(-1)
    plugin = core.mjp_getPlugin(PLUGIN_NAME, ctypes.byref(slot))
    return plugin, slot.value


plugin, slot = find_plugin()
if plugin:
    raise AssertionError(f"target plugin was already registered in fresh process at slot {slot}")

# Do not pre-load the target with ctypes: this call must be the source of registration.
mujoco.mj_loadPluginLibrary(str(PLUGIN_PATH))
plugin, slot = find_plugin()
if not plugin:
    raise AssertionError(f"target plugin not registered after loading {PLUGIN_PATH}")
actual_attributes = tuple(
    plugin.contents.attributes[index] for index in range(plugin.contents.nattribute)
)
if plugin.contents.name != PLUGIN_NAME:
    raise AssertionError(f"wrong plugin name: {plugin.contents.name!r}")
if actual_attributes != ATTRIBUTE_NAMES:
    raise AssertionError(f"wrong plugin attributes: {actual_attributes!r}")

mode = sys.argv[1]
if mode == "registration":
    print(f"registered slot={slot} name={plugin.contents.name!r} attributes={actual_attributes!r}")
elif mode == "valid_mjcf":
    model = mujoco.MjModel.from_xml_string(sys.stdin.read())
    data = mujoco.MjData(model)
    if model.nplugin != 1 or data is None:
        raise AssertionError(f"unexpected valid model state: nplugin={model.nplugin}, data={data!r}")
    print(f"valid model nplugin={model.nplugin}")
elif mode == "invalid_mjcf":
    try:
        mujoco.MjModel.from_xml_string(sys.stdin.read())
    except ValueError as error:
        expected = "mj_initPlugin: plugin->init failed for plugin id 0"
        if expected not in str(error):
            raise AssertionError(f"unexpected invalid-config error: {error}") from error
        print(expected)
    else:
        raise AssertionError("invalid plugin configuration unexpectedly compiled")
else:
    raise AssertionError(f"unknown probe mode: {mode}")
"""


def minimal_mjcf(config=DEFAULT_CONFIG):
    config_xml = "\n".join(
        f'<config key="{name}" value="{value}"/>' for name, value in config.items()
    )
    return f"""
    <mujoco>
      <extension>
        <plugin plugin="mujoco.sdf.dsub9_hole">
          <instance name="hole">{config_xml}</instance>
        </plugin>
      </extension>
      <asset>
        <mesh name="hole_mesh"><plugin instance="hole"/></mesh>
      </asset>
      <worldbody>
        <geom name="hole" type="sdf" mesh="hole_mesh"><plugin instance="hole"/></geom>
      </worldbody>
    </mujoco>
    """


@contextmanager
def serialized_build():
    lock_path = BUILD.parent / ".dsub9_hole_sdf_build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, 2)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()

        deadline = time.monotonic() + 120
        while True:
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for plugin build lock: {lock_path}")
                time.sleep(0.1)
        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


@functools.lru_cache(maxsize=1)
def plugin_library_path() -> Path:
    import mujoco

    mujoco_root = Path(mujoco.__file__).resolve().parent
    with serialized_build():
        subprocess.run(
            [
                "cmake",
                "-S",
                str(SOURCE),
                "-B",
                str(BUILD),
                "-G",
                "Visual Studio 18 2026",
                "-A",
                "x64",
                f"-DMUJOCO_ROOT={mujoco_root}",
            ],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            ["cmake", "--build", str(BUILD), "--config", "Release"],
            cwd=ROOT,
            check=True,
        )
    library = ROOT / PLUGIN_RELATIVE_PATH
    assert library.is_file()
    return library


@functools.lru_cache(maxsize=1)
def loaded_plugin():
    library = ctypes.WinDLL(str(plugin_library_path()))
    library.dsub9_hole_distance.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
    ]
    library.dsub9_hole_distance.restype = ctypes.c_double
    library.dsub9_hole_gradient.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
    ]
    library.dsub9_hole_gradient.restype = None
    library.dsub9_hole_validate.argtypes = [ctypes.POINTER(ctypes.c_double)]
    library.dsub9_hole_validate.restype = ctypes.c_int
    return library


def run_mujoco_probe(mode, xml=""):
    plugin_library_path()
    result = subprocess.run(
        [sys.executable, "-c", MUJOCO_PROBE, mode],
        cwd=ROOT,
        input=xml,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"fresh MuJoCo probe failed in mode {mode!r} with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result.stdout


def test_plugin_library_exists_and_loads():
    ctypes.WinDLL(str(plugin_library_path()))


def test_plugin_registers_exact_name_and_attributes():
    output = run_mujoco_probe("registration")
    assert "registered slot=" in output
    assert "mujoco.sdf.dsub9_hole" in output


def test_minimal_mjcf_plugin_instance_loads():
    assert "valid model nplugin=1" in run_mujoco_probe("valid_mjcf", minimal_mjcf())


@pytest.mark.parametrize(
    "point",
    [
        np.array([0.0, 0.0, 0.00200]),
        np.array([0.00059, 0.00002, 0.00200]),
        np.array([0.000625, 0.0, 0.00010]),
        np.array([0.000625, 0.0, 0.00050]),
        np.array([0.000800, 0.0, PARAMS.entry_depth - 1e-9]),
        np.array([0.000800, 0.0, PARAMS.entry_depth]),
        np.array([0.000800, 0.0, PARAMS.entry_depth + 1e-9]),
        np.array([0.00120, 0.00010, 0.00480]),
    ],
)
def test_cpp_distance_and_gradient_match_python_reference(point):
    library = loaded_plugin()
    point_array = (ctypes.c_double * 3)(*point)
    gradient_array = (ctypes.c_double * 3)()
    actual_distance = library.dsub9_hole_distance(point_array, PARAM_ARRAY)
    library.dsub9_hole_gradient(gradient_array, point_array, PARAM_ARRAY)
    assert actual_distance == pytest.approx(hole_distance(point, PARAMS), abs=1e-14)
    np.testing.assert_allclose(
        np.ctypeslib.as_array(gradient_array),
        hole_gradient(point, PARAMS),
        atol=1e-12,
    )


@pytest.mark.parametrize(
    "values",
    [
        (0.000675, 0.000675, 0.00025, 0.00450, 0.00100),
        (0.000575, 0.00100, 0.00025, 0.00450, 0.00100),
        (0.000575, 0.000675, 0.0, 0.00450, 0.00100),
        (0.000575, 0.000675, 0.00450, 0.00450, 0.00100),
        (float("nan"), 0.000675, 0.00025, 0.00450, 0.00100),
        (0.000575, 0.000675, 0.00025, float("inf"), 0.00100),
    ],
)
def test_cpp_rejects_invalid_parameters(values):
    params = (ctypes.c_double * 5)(*values)
    assert loaded_plugin().dsub9_hole_validate(params) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"bore_radius": "0.000675"},
        {"entry_radius": "0.00100"},
        {"entry_depth": "0.0"},
        {"entry_depth": "0.00450"},
        {"bore_radius": "nan"},
        {"bore_depth": "inf"},
    ],
)
def test_mujoco_instance_rejects_invalid_plugin_config(changes):
    config = DEFAULT_CONFIG | changes
    # MuJoCo 3.9 creates temporary mjData while compiling a model, so plugin
    # init is reached inside from_xml_string rather than at the later explicit
    # MjData construction.  Matching the engine error proves static SDF/AABB
    # processing completed with finite fallback values and init rejected the
    # original invalid attributes through the real plugin lifecycle.
    assert "mj_initPlugin: plugin->init failed for plugin id 0" in run_mujoco_probe(
        "invalid_mjcf", minimal_mjcf(config)
    )
