from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_RELATIVE_PATH = Path("build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll")
PLUGIN = ROOT / PLUGIN_RELATIVE_PATH

MODEL_PROBE = r"""
import ctypes
import json
from pathlib import Path
import sys

import mujoco


PLUGIN_NAME = b"mujoco.sdf.dsub9_hole"
ATTRIBUTE_NAMES = (
    b"bore_radius",
    b"entry_radius",
    b"entry_depth",
    b"bore_depth",
    b"outer_radius",
)


class PluginPrefix(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("nattribute", ctypes.c_int),
        ("attributes", ctypes.POINTER(ctypes.c_char_p)),
    ]


root = Path.cwd().resolve()
if root != Path(sys.argv[1]).resolve():
    raise AssertionError(f"probe cwd {root} does not match project root {sys.argv[1]}")
plugin_path = Path(sys.argv[4])
plugin_path_exists = plugin_path.is_file()

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

load_plugin = sys.argv[3] == "1"
if load_plugin:
    if not plugin_path_exists:
        raise AssertionError(f"target plugin path does not exist: {plugin_path}")
    # This relative ASCII path is intentionally the only target-DLL load in the child.
    mujoco.mj_loadPluginLibrary(str(plugin_path))
    plugin, slot = find_plugin()
    if not plugin:
        raise AssertionError("target plugin did not register through mj_loadPluginLibrary")
    attributes = tuple(
        plugin.contents.attributes[index] for index in range(plugin.contents.nattribute)
    )
    if plugin.contents.name != PLUGIN_NAME or attributes != ATTRIBUTE_NAMES:
        raise AssertionError(
            f"wrong plugin registration: name={plugin.contents.name!r}, attributes={attributes!r}"
        )

model = mujoco.MjModel.from_xml_path(sys.argv[2])
data = mujoco.MjData(model)
plugin, slot = find_plugin()
if load_plugin and not plugin:
    raise AssertionError("target plugin disappeared after model compilation")
if not load_plugin and plugin:
    raise AssertionError(f"fallback model unexpectedly registered target plugin at slot {slot}")
geom_names = [
    mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index)
    for index in range(model.ngeom)
]
name_to_id = {name: index for index, name in enumerate(geom_names)}


def geom_record(name):
    index = name_to_id[name]
    return {
        "type": int(model.geom_type[index]),
        "plugin": int(model.geom_plugin[index]),
        "body": int(model.geom_bodyid[index]),
        "contype": int(model.geom_contype[index]),
        "conaffinity": int(model.geom_conaffinity[index]),
    }


type_counts = {}
for value in model.geom_type:
    key = str(int(value))
    type_counts[key] = type_counts.get(key, 0) + 1

print(json.dumps({
    "version": mujoco.mj_versionString(),
    "version_int": mujoco.mj_version(),
    "plugin_path_exists": plugin_path_exists,
    "plugin_registered": bool(plugin),
    "registration_slot": slot,
    "nbody": model.nbody,
    "ngeom": model.ngeom,
    "nmesh": model.nmesh,
    "nplugin": model.nplugin,
    "njnt": model.njnt,
    "nq": model.nq,
    "type_counts": type_counts,
    "female_body": mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "female"),
    "male_body": mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "male"),
    "male_mass": float(model.body_mass[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "male")]),
    "records": {
        name: geom_record(name)
        for name in (
            "female_visual",
            "male_visual",
            "d_socket_female_seg_000",
            "d_socket_female_seg_041",
            "d_guide_male_seg_000",
            "d_guide_male_seg_077",
            "pin_01",
            "pin_09",
            *(["hole_sdf_01", "hole_sdf_09"] if "hole_sdf_01" in name_to_id else []),
            *(
                ["hole_fallback_32_h01_entry_s00", "hole_fallback_32_h09_main_s31"]
                if "hole_fallback_32_h01_entry_s00" in name_to_id else []
            ),
        )
    },
    "sdf_plugins": [
        int(model.geom_plugin[index])
        for index, name in enumerate(geom_names)
        if name.startswith("hole_sdf_")
    ],
    "fallback_plugins": [
        int(model.geom_plugin[index])
        for index, name in enumerate(geom_names)
        if name.startswith("hole_fallback_32_")
    ],
    "data_created": data is not None,
}))
"""


def _load_in_fresh_process(relative_model: str, *, load_plugin: bool) -> dict:
    if load_plugin:
        assert PLUGIN.is_file(), f"build Task 4 plugin first: {PLUGIN}"
    plugin_argument = str(PLUGIN_RELATIVE_PATH if load_plugin else PLUGIN)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            MODEL_PROBE,
            str(ROOT),
            relative_model,
            "1" if load_plugin else "0",
            plugin_argument,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"fresh MuJoCo model probe failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return json.loads(result.stdout)


def _assert_supported_mujoco_version(version_int: int) -> None:
    # MuJoCo encodes M.m.p as M*1_000_000 + m*1_000 + p.
    assert 3_003_000 <= version_int < 4_000_000


def _assert_shared_pair_metadata(result: dict) -> None:
    _assert_supported_mujoco_version(result["version_int"])
    assert result["nbody"] == 3
    assert result["njnt"] == 1
    assert result["nq"] == 7
    assert result["female_body"] == 1
    assert result["male_body"] == 2
    assert result["male_mass"] == 0.05
    assert result["data_created"] is True
    records = result["records"]
    for name in ("female_visual", "male_visual"):
        assert records[name] == {
            "type": 7,
            "plugin": -1,
            "body": 1 if name == "female_visual" else 2,
            "contype": 0,
            "conaffinity": 0,
        }
    for name in ("d_socket_female_seg_000", "d_socket_female_seg_041"):
        assert records[name] == {
            "type": 7,
            "plugin": -1,
            "body": 1,
            "contype": 8,
            "conaffinity": 4,
        }
    for name in ("d_guide_male_seg_000", "d_guide_male_seg_077"):
        assert records[name] == {
            "type": 7,
            "plugin": -1,
            "body": 2,
            "contype": 4,
            "conaffinity": 8,
        }
    for name in ("pin_01", "pin_09"):
        assert records[name] == {
            "type": 5,
            "plugin": -1,
            "body": 2,
            "contype": 1,
            "conaffinity": 2,
        }


def test_supported_mujoco_version_range_is_not_minor_locked():
    """Any supported MuJoCo 3.x minor must pass without a packaging dependency."""
    _assert_supported_mujoco_version(3_003_000)
    _assert_supported_mujoco_version(3_999_999)
    with pytest.raises(AssertionError):
        _assert_supported_mujoco_version(3_002_999)
    with pytest.raises(AssertionError):
        _assert_supported_mujoco_version(4_000_000)


def test_fallback_load_does_not_require_or_register_sdf_plugin(monkeypatch):
    """The mesh-only fallback must compile even when the target DLL is absent."""
    missing = ROOT / "build" / "missing-for-fallback-test" / "dsub9_hole_sdf.dll"
    assert not missing.exists()
    monkeypatch.setattr(sys.modules[__name__], "PLUGIN", missing)
    monkeypatch.chdir(Path(ROOT.anchor))
    assert Path.cwd().resolve() != ROOT

    result = _load_in_fresh_process(
        "build/dsub9_pair_polygon32.xml", load_plugin=False
    )

    assert result["plugin_path_exists"] is False
    assert result["plugin_registered"] is False
    assert result["registration_slot"] == -1
    assert result["nplugin"] == 0


def test_formal_sdf_pair_compiles_with_exact_plugin_slots_and_inventory():
    """The formal model must compile as nine true SDF holes, not a loose smoke test."""
    result = _load_in_fresh_process("models/dsub9_pair.xml", load_plugin=True)
    _assert_shared_pair_metadata(result)
    assert result["plugin_registered"] is True
    assert result["registration_slot"] >= 0
    assert result["ngeom"] == 140
    assert result["nmesh"] == 123
    assert result["nplugin"] == 1
    assert result["type_counts"] == {"5": 9, "7": 122, "8": 9}
    # mjp_getPlugin returns a process-global registration slot, while
    # mjModel.geom_plugin stores the model-local plugin instance id.
    assert result["sdf_plugins"] == [0] * 9
    assert result["fallback_plugins"] == []
    for name in ("hole_sdf_01", "hole_sdf_09"):
        assert result["records"][name] == {
            "type": 8,
            "plugin": 0,
            "body": 1,
            "contype": 2,
            "conaffinity": 1,
        }


def test_polygon32_fallback_compiles_with_full_mesh_inventory_and_no_instances():
    """The fallback must retain all 576 mesh pieces while remaining non-formal."""
    result = _load_in_fresh_process(
        "build/dsub9_pair_polygon32.xml", load_plugin=False
    )
    _assert_shared_pair_metadata(result)
    assert result["plugin_registered"] is False
    assert result["registration_slot"] == -1
    assert result["ngeom"] == 707
    assert result["nmesh"] == 698
    assert result["nplugin"] == 0
    assert result["type_counts"] == {"5": 9, "7": 698}
    assert result["sdf_plugins"] == []
    assert result["fallback_plugins"] == [-1] * 576
    for name in ("hole_fallback_32_h01_entry_s00", "hole_fallback_32_h09_main_s31"):
        assert result["records"][name] == {
            "type": 7,
            "plugin": -1,
            "body": 1,
            "contype": 2,
            "conaffinity": 1,
        }
