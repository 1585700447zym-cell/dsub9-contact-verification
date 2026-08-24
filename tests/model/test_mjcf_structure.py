from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "dsub9_pair.xml"
FALLBACK_MODEL = ROOT / "build" / "dsub9_pair_polygon32.xml"
VISUAL_INCLUDE = ROOT / "models" / "includes" / "dsub9_visual.xml"
COLLISION_INCLUDE = ROOT / "models" / "includes" / "dsub9_collision.xml"

EXPECTED_PIN_CENTRES = (
    (-0.00554, 0.00142),
    (-0.00277, 0.00142),
    (0.0, 0.00142),
    (0.00277, 0.00142),
    (0.00554, 0.00142),
    (-0.004155, -0.00142),
    (-0.001385, -0.00142),
    (0.001385, -0.00142),
    (0.004155, -0.00142),
)

EXPECTED_SOURCE_HASHES = {
    "DSub9_Deliverables_V4/DSub9_Female_Refined_V3.STL":
        "13b9329e214a07abe3d1346072572cad03b2374c455125ba56a6f3c7cce6cbbd",
    "DSub9_Deliverables_V4/DSub9_Female_Refined_V3.step":
        "8afb66c2ecbab8b02be06b59a4cd726c29ed949be3c354f3233bf7595d7eb39f",
    "DSub9_Deliverables_V4/DSub9_Male_TwoStageRearShell_V3.step":
        "e6b3c453c5066ab18e3c594c53a21ee006f6c9030e9e8ee17b4274d2e26ad44a",
    "assets/visual/dsub9_female_visual_centered.stl":
        "c37b549a7db371d39388b9109889efb525eb2182f3cd520d07c51add16ffe065",
    "assets/visual/dsub9_male_visual_centered.stl":
        "e2d0ce38faee11f4d00acee74155983719f36830984d186d3838f6bf28f1d153",
}


def _root(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def _body(root: ET.Element, name: str) -> ET.Element:
    body = root.find(f"./worldbody/body[@name='{name}']")
    assert body is not None
    return body


def _floats(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in value.split())


def _defaults(root: ET.Element) -> dict[str, ET.Element]:
    return {
        element.attrib["class"]: element.find("geom")
        for element in root.findall("./default/default")
    }


def test_pin_centres_form_exact_five_plus_four_pattern():
    """Changing row order, pitch, or either staggered row must be detected."""
    from tools.model.generate_mjcf import pin_centres_m

    assert pin_centres_m() == EXPECTED_PIN_CENTRES


@pytest.mark.parametrize(
    "mode, path",
    [("sdf", MODEL), ("polygon32", FALLBACK_MODEL)],
)
def test_generated_pair_xml_matches_deterministic_builder(mode: str, path: Path):
    """A stale checked-in/generated model must not diverge from its generator."""
    from tools.model.generate_mjcf import build_pair_xml

    first = build_pair_xml(mode)
    assert build_pair_xml(mode) == first
    assert path.read_text(encoding="utf-8") == first


def test_generated_model_and_includes_use_utf8_lf_bytes(tmp_path, monkeypatch):
    """Platform-default newline translation must not create reviewed CRLF bytes."""
    import tools.model.generate_mjcf as generator

    include_dir = tmp_path / "models" / "includes"
    monkeypatch.setattr(generator, "INCLUDE_DIR", include_dir)
    monkeypatch.setattr(generator, "_require_assets", lambda: None)
    target = generator.generate_model("sdf", tmp_path / "models" / "pair.xml")

    for path in (
        target,
        include_dir / "dsub9_visual.xml",
        include_dir / "dsub9_collision.xml",
    ):
        raw = path.read_bytes()
        raw.decode("utf-8")
        assert b"\n" in raw, path
        assert b"\r\n" not in raw, path


def test_reported_fallback_hash_matches_fresh_canonical_generation(tmp_path, monkeypatch):
    """The reviewed report hash must identify the generator's canonical fallback bytes."""
    import tools.model.generate_mjcf as generator

    monkeypatch.setattr(generator, "INCLUDE_DIR", tmp_path / "includes")
    target = generator.generate_model(
        "polygon32", tmp_path / "dsub9_pair_polygon32.xml"
    )
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    report = (ROOT / "reports" / "collision_geometry_report.md").read_text(
        encoding="utf-8"
    )
    match = re.search(r"Fallback XML SHA-256 is `([0-9a-f]{64})`", report)

    assert match is not None
    assert match.group(1) == actual


def test_formal_model_uses_real_generated_includes_before_body_geometry():
    """Removing an include or declaring defaults after use breaks reproducibility."""
    root = _root(MODEL)
    children = list(root)
    default_index = next(index for index, child in enumerate(children) if child.tag == "default")
    worldbody_index = next(index for index, child in enumerate(children) if child.tag == "worldbody")
    assert default_index < worldbody_index
    assert [item.attrib["file"] for item in root.findall("./include")] == [
        "includes/dsub9_visual.xml",
        "includes/dsub9_collision.xml",
    ]

    visual_meshes = _root(VISUAL_INCLUDE).findall("./asset/mesh")
    collision_meshes = _root(COLLISION_INCLUDE).findall("./asset/mesh")
    assert len(visual_meshes) == 2
    assert len(collision_meshes) == 120
    assert {mesh.attrib["file"] for mesh in visual_meshes} == {
        "visual/dsub9_female_visual_centered.stl",
        "visual/dsub9_male_visual_centered.stl",
    }
    assert sum("d_guide_male_seg_" in mesh.attrib["file"] for mesh in collision_meshes) == 78
    assert sum("d_socket_female_seg_" in mesh.attrib["file"] for mesh in collision_meshes) == 42
    for mesh in visual_meshes + collision_meshes:
        assert mesh.attrib["scale"] == "0.001 0.001 0.001"
        assert (ROOT / "assets" / mesh.attrib["file"]).is_file()


def test_visual_meshes_are_explicitly_collision_disabled_and_untransformed():
    """A visual STL participating in collision or mass would corrupt dynamics."""
    root = _root(MODEL)
    visual_geoms = root.findall(".//geom[@class='visual']")
    assert len(visual_geoms) == 2
    assert {geom.attrib["mesh"] for geom in visual_geoms} == {
        "dsub9_female_visual",
        "dsub9_male_visual",
    }
    for geom in visual_geoms:
        assert geom.attrib["type"] == "mesh"
        assert geom.attrib["group"] == "2"
        assert geom.attrib["contype"] == "0"
        assert geom.attrib["conaffinity"] == "0"
        assert not ({"pos", "quat", "euler", "axisangle"} & geom.attrib.keys())


def test_default_collision_masks_allow_only_required_mating_pairs():
    """Shared bits would enable pin-pin, hole-hole, or cross-feature contacts."""
    defaults = _defaults(_root(MODEL))
    expected = {
        "visual": ("0", "0"),
        "pin_collision": ("1", "2"),
        "hole_sdf_collision": ("2", "1"),
        "male_guide_collision": ("4", "8"),
        "female_socket_collision": ("8", "4"),
        "hole_polygon32_collision": ("2", "1"),
    }
    assert set(defaults) == set(expected)
    for class_name, (contype, conaffinity) in expected.items():
        geom = defaults[class_name]
        assert geom is not None
        assert geom.attrib["contype"] == contype
        assert geom.attrib["conaffinity"] == conaffinity


def test_uncalibrated_contact_baseline_is_versioned_frozen_and_consumable():
    """Task 6 sensitivity must import one typed baseline instead of copying constants."""
    from tools.model.generate_mjcf import (
        ContactParameters,
        baseline_contact_parameters,
        build_pair_xml,
        contact_parameters_mjcf,
    )

    parameters = baseline_contact_parameters()
    assert isinstance(parameters, ContactParameters)
    assert parameters.name == "uncalibrated_diagnostic_v1"
    assert parameters.friction == (1.0, 0.005, 0.0001)
    assert parameters.solref == (0.02, 1.0)
    assert parameters.solimp == (0.9, 0.95, 0.001, 0.5, 2.0)
    assert parameters.margin_m == 0.0
    assert contact_parameters_mjcf(parameters) == {
        "friction": "1 0.005 0.0001",
        "solref": "0.02 1",
        "solimp": "0.9 0.95 0.001 0.5 2",
        "margin": "0",
    }
    with pytest.raises(FrozenInstanceError):
        parameters.margin_m = 1e-6

    perturbed = replace(parameters, margin_m=1e-6)
    root = ET.fromstring(build_pair_xml("sdf", contact_parameters=perturbed))
    collision_defaults = [
        item.find("geom")
        for item in root.findall("./default/default")
        if item.attrib["class"] != "visual"
    ]
    assert collision_defaults
    assert {geom.attrib["margin"] for geom in collision_defaults} == {"0.000001"}


@pytest.mark.parametrize("path", [MODEL, FALLBACK_MODEL])
def test_every_collision_default_explicitly_freezes_contact_baseline(path: Path):
    """Removing explicit physics would silently reintroduce engine-version defaults."""
    defaults = _defaults(_root(path))
    expected = {
        "friction": "1 0.005 0.0001",
        "solref": "0.02 1",
        "solimp": "0.9 0.95 0.001 0.5 2",
        "margin": "0",
    }
    collision_classes = set(defaults) - {"visual"}
    assert collision_classes == {
        "pin_collision",
        "hole_sdf_collision",
        "male_guide_collision",
        "female_socket_collision",
        "hole_polygon32_collision",
    }
    for class_name in collision_classes:
        geom = defaults[class_name]
        assert geom is not None
        assert {name: geom.attrib[name] for name in expected} == expected
    assert not (set(expected) & defaults["visual"].attrib.keys())


def test_formal_model_contains_exact_pin_and_sdf_hole_geometry():
    """Dropping a pair, shifting a centre, or substituting a polygon must fail."""
    root = _root(MODEL)
    female = _body(root, "female")
    male = _body(root, "male")
    pins = male.findall("./geom[@class='pin_collision']")
    holes = female.findall("./geom[@class='hole_sdf_collision']")
    assert len(pins) == 9
    assert len(holes) == 9
    assert [geom.attrib["name"] for geom in pins] == [f"pin_{index:02d}" for index in range(1, 10)]
    assert [geom.attrib["name"] for geom in holes] == [f"hole_sdf_{index:02d}" for index in range(1, 10)]

    for geom, (x, y) in zip(pins, EXPECTED_PIN_CENTRES, strict=True):
        assert geom.attrib["type"] == "cylinder"
        assert _floats(geom.attrib["size"]) == (0.0005, 0.002)
        assert _floats(geom.attrib["pos"]) == pytest.approx((x, y, 0.002), abs=1e-15)
    for geom, (x, y) in zip(holes, EXPECTED_PIN_CENTRES, strict=True):
        assert geom.attrib["type"] == "sdf"
        assert geom.attrib["mesh"] == "hole_sdf_mesh"
        assert _floats(geom.attrib["pos"]) == pytest.approx((x, y, 0.0), abs=1e-15)
        plugin = geom.find("plugin")
        assert plugin is not None and plugin.attrib == {"instance": "hole_sdf"}

    assert not root.findall(".//geom[@class='hole_polygon32_collision']")
    assert "hole_fallback_32" not in MODEL.read_text(encoding="utf-8")


def test_sdf_plugin_instance_has_exact_name_and_parameters():
    """A wrong plugin name or radius/depth silently changes formal geometry."""
    root = _root(MODEL)
    plugin = root.find("./extension/plugin")
    assert plugin is not None and plugin.attrib == {"plugin": "mujoco.sdf.dsub9_hole"}
    instance = plugin.find("instance")
    assert instance is not None and instance.attrib == {"name": "hole_sdf"}
    assert {item.attrib["key"]: item.attrib["value"] for item in instance.findall("config")} == {
        "bore_radius": "0.000575",
        "entry_radius": "0.000675",
        "entry_depth": "0.00025",
        "bore_depth": "0.00450",
        "outer_radius": "0.00100",
    }
    mesh = root.find("./asset/mesh[@name='hole_sdf_mesh']")
    assert mesh is not None
    mesh_plugin = mesh.find("plugin")
    assert mesh_plugin is not None and mesh_plugin.attrib == {"instance": "hole_sdf"}


def test_all_cad_d_parts_are_on_their_corresponding_body():
    """An overall hull, rectangle, missing strip, or wrong-body strip must fail."""
    root = _root(MODEL)
    female = _body(root, "female")
    male = _body(root, "male")
    male_parts = male.findall("./geom[@class='male_guide_collision']")
    female_parts = female.findall("./geom[@class='female_socket_collision']")
    assert len(male_parts) == 78
    assert len(female_parts) == 42
    assert {geom.attrib["mesh"] for geom in male_parts} == {
        f"d_guide_male_seg_{index:03d}" for index in range(78)
    }
    assert {geom.attrib["mesh"] for geom in female_parts} == {
        f"d_socket_female_seg_{index:03d}" for index in range(42)
    }
    assert all(geom.attrib["type"] == "mesh" for geom in male_parts + female_parts)


def test_female_is_fixed_and_male_has_freejoint_and_explicit_inertial():
    """Mesh-derived mass or a movable female invalidates the validation scene."""
    root = _root(MODEL)
    female = _body(root, "female")
    male = _body(root, "male")
    assert not female.findall("./joint")
    assert not female.findall("./freejoint")
    assert male.find("./freejoint") is not None
    assert not male.findall("./joint")
    inertial = male.find("./inertial")
    assert inertial is not None
    assert float(inertial.attrib["mass"]) > 0
    assert all(value > 0 for value in _floats(inertial.attrib["diaginertia"]))
    assert not ({"pos", "quat", "euler", "axisangle"} & female.attrib.keys())
    assert not ({"pos", "quat", "euler", "axisangle"} & male.attrib.keys())


def test_polygon32_model_contains_every_layer_hole_and_sector_as_fallback_only():
    """A partial sector/layer inventory or an SDF-labelled fallback must fail."""
    root = _root(FALLBACK_MODEL)
    assert root.attrib["model"] == "dsub9_pair_polygon32_fallback"
    assert root.find("./extension") is None
    female = _body(root, "female")
    fallback = female.findall("./geom[@class='hole_polygon32_collision']")
    assert len(fallback) == 9 * 2 * 32
    expected_names = {
        f"hole_fallback_32_h{hole:02d}_{layer}_s{sector:02d}"
        for hole in range(1, 10)
        for layer in ("entry", "main")
        for sector in range(32)
    }
    assert {geom.attrib["name"] for geom in fallback} == expected_names
    assert {geom.attrib["mesh"] for geom in fallback} == expected_names
    assert all(geom.attrib["type"] == "mesh" for geom in fallback)
    assets = root.findall("./asset/mesh")
    assert len(assets) == 576
    assert {mesh.attrib["name"] for mesh in assets} == expected_names
    for mesh in assets:
        assert mesh.attrib["scale"] == "0.001 0.001 0.001"
        assert mesh.attrib["file"].startswith("collision/hole_fallback_32_")
        assert (ROOT / "assets" / mesh.attrib["file"]).is_file()


def test_models_have_no_unexpected_collision_substitutes():
    """Boxes, hulls, or extra colliders must not replace the reviewed inventory."""
    formal = _root(MODEL)
    fallback = _root(FALLBACK_MODEL)
    formal_classes = [geom.attrib.get("class") for geom in formal.findall(".//worldbody//geom")]
    fallback_classes = [geom.attrib.get("class") for geom in fallback.findall(".//worldbody//geom")]
    assert sorted(formal_classes) == sorted(
        ["visual"] * 2
        + ["pin_collision"] * 9
        + ["hole_sdf_collision"] * 9
        + ["male_guide_collision"] * 78
        + ["female_socket_collision"] * 42
    )
    assert sorted(fallback_classes) == sorted(
        ["visual"] * 2
        + ["pin_collision"] * 9
        + ["hole_polygon32_collision"] * 576
        + ["male_guide_collision"] * 78
        + ["female_socket_collision"] * 42
    )


def test_source_and_reviewed_visual_assets_are_unchanged():
    """Task 5 must consume, never rewrite, CAD and reviewed visual assets."""
    for relative_path, expected_hash in EXPECTED_SOURCE_HASHES.items():
        actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert actual == expected_hash, relative_path
