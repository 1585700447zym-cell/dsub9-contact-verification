import ctypes
import functools
from pathlib import Path
import subprocess

import numpy as np
import pytest

from tools.sdf.hole_reference import HoleParams, hole_distance, hole_gradient


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "plugins" / "dsub9_hole_sdf"
BUILD = ROOT / "build" / "dsub9_hole_sdf"
PLUGIN_NAME = b"mujoco.sdf.dsub9_hole"
ATTRIBUTE_NAMES = (
    b"bore_radius",
    b"entry_radius",
    b"entry_depth",
    b"bore_depth",
    b"outer_radius",
)
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


@functools.lru_cache(maxsize=1)
def plugin_library_path() -> Path:
    import mujoco

    mujoco_root = Path(mujoco.__file__).resolve().parent
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
    library = BUILD / "Release" / "dsub9_hole_sdf.dll"
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


def load_plugin_with_mujoco():
    import mujoco

    library = plugin_library_path()
    # MuJoCo 3.9's Windows loader accepts a narrow path.  Keep the path passed
    # into that API ASCII-only; ROOT itself contains non-ASCII characters.
    assert Path.cwd().resolve() == ROOT.resolve()
    mujoco.mj_loadPluginLibrary(str(library.relative_to(ROOT)))
    return library


def test_plugin_library_exists_and_loads():
    ctypes.WinDLL(str(plugin_library_path()))


def test_plugin_registers_exact_name_and_attributes():
    import mujoco

    load_plugin_with_mujoco()
    core = ctypes.WinDLL(str(Path(mujoco.__file__).resolve().parent / "mujoco.dll"))

    class PluginPrefix(ctypes.Structure):
        _fields_ = [
            ("name", ctypes.c_char_p),
            ("nattribute", ctypes.c_int),
            ("attributes", ctypes.POINTER(ctypes.c_char_p)),
        ]

    core.mjp_getPlugin.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    core.mjp_getPlugin.restype = ctypes.POINTER(PluginPrefix)
    slot = ctypes.c_int(-1)
    plugin = core.mjp_getPlugin(PLUGIN_NAME, ctypes.byref(slot))
    assert bool(plugin)
    assert slot.value >= 0
    assert plugin.contents.name == PLUGIN_NAME
    assert plugin.contents.nattribute == len(ATTRIBUTE_NAMES)
    assert tuple(plugin.contents.attributes[i] for i in range(5)) == ATTRIBUTE_NAMES


def test_minimal_mjcf_plugin_instance_loads():
    import mujoco

    load_plugin_with_mujoco()
    model = mujoco.MjModel.from_xml_string(minimal_mjcf())
    data = mujoco.MjData(model)
    assert model.nplugin == 1
    assert data is not None


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
    import mujoco

    load_plugin_with_mujoco()
    config = DEFAULT_CONFIG | changes
    # MuJoCo 3.9 creates temporary mjData while compiling a model, so plugin
    # init is reached inside from_xml_string rather than at the later explicit
    # MjData construction.  Matching the engine error proves static SDF/AABB
    # processing completed with finite fallback values and init rejected the
    # original invalid attributes through the real plugin lifecycle.
    with pytest.raises(
        ValueError,
        match=r"mj_initPlugin: plugin->init failed for plugin id 0",
    ):
        mujoco.MjModel.from_xml_string(minimal_mjcf(config))
