from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

from tools.reporting.generate_manifest import (
    build_manifest,
    verify_manifest,
    write_manifest,
)


REVIEW_ROOTS = ("assets", "models", "plugins", "tools", "tests", "reports")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_project(root: Path) -> None:
    for directory in REVIEW_ROOTS:
        (root / directory).mkdir(parents=True)
    (root / "README.md").write_text("read me\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")
    (root / ".gitattributes").write_text("* text=auto eol=lf\n", encoding="utf-8")


def manifest_paths(text: str) -> list[str]:
    return [line.split("  ", maxsplit=1)[1] for line in text.splitlines()]


def test_manifest_paths_are_posix_relative_and_sorted(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "assets" / "z.stl").write_bytes(b"z")
    nested = tmp_path / "assets" / "nested"
    nested.mkdir()
    (nested / "a.stl").write_bytes(b"a")

    paths = manifest_paths(build_manifest(tmp_path))

    assert paths == sorted(paths)
    assert "assets/nested/a.stl" in paths
    assert all("\\" not in path for path in paths)
    assert all(not Path(path).is_absolute() for path in paths)


def test_manifest_sha256_matches_file_bytes(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "assets" / "known.bin").write_bytes(b"abc")

    lines = build_manifest(tmp_path).splitlines()

    assert (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        "  assets/known.bin"
    ) in lines


def test_manifest_excludes_itself(tmp_path: Path) -> None:
    make_project(tmp_path)
    manifest = tmp_path / "reports" / "final_file_manifest.txt"
    manifest.write_text("stale self reference\n", encoding="utf-8")

    text = build_manifest(tmp_path)

    assert "reports/final_file_manifest.txt" not in text


def test_manifest_covers_all_reviewed_regular_files(tmp_path: Path) -> None:
    make_project(tmp_path)
    expected = {".gitattributes", ".gitignore", "README.md", "pyproject.toml"}
    for directory in REVIEW_ROOTS:
        path = tmp_path / directory / f"reviewed {directory}.dat"
        path.write_bytes(directory.encode("ascii"))
        expected.add(f"{directory}/reviewed {directory}.dat")

    actual = set(manifest_paths(build_manifest(tmp_path)))

    assert actual == expected


def test_verify_detects_stale_manifest(tmp_path: Path) -> None:
    make_project(tmp_path)
    reviewed = tmp_path / "models" / "model.xml"
    reviewed.write_text("<model version='1'/>\n", encoding="utf-8")
    write_manifest(tmp_path)
    assert verify_manifest(tmp_path)

    reviewed.write_text("<model version='2'/>\n", encoding="utf-8")

    assert not verify_manifest(tmp_path)


def test_verify_accepts_git_crlf_checkout(tmp_path: Path) -> None:
    make_project(tmp_path)
    manifest = write_manifest(tmp_path)
    manifest.write_bytes(manifest.read_bytes().replace(b"\n", b"\r\n"))

    assert verify_manifest(tmp_path)


def test_autocrlf_fresh_checkout_preserves_all_manifest_hashes(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source project"
    for directory in REVIEW_ROOTS:
        (source / directory).mkdir(parents=True)
    (source / "README.md").write_bytes(b"project\nreadme\n")
    (source / "pyproject.toml").write_bytes(b"[project]\nname='fixture'\n")
    (source / ".gitignore").write_bytes(b"build/\n")
    attributes = PROJECT_ROOT / ".gitattributes"
    if attributes.is_file():
        shutil.copy2(attributes, source / ".gitattributes")
    (source / "tools" / "reporting").mkdir()
    shutil.copy2(
        PROJECT_ROOT / "tools" / "reporting" / "generate_manifest.py",
        source / "tools" / "reporting" / "generate_manifest.py",
    )
    (source / "assets" / "reviewed.stl").write_bytes(
        b"solid text_like_stl\nendsolid text_like_stl\n"
    )
    (source / "source_cad.step").write_bytes(
        b"ISO-10303-21;\r\nHEADER;\r\nENDSEC;\r\nEND-ISO-10303-21;\r\n"
    )
    for directory in REVIEW_ROOTS:
        (source / directory / "reviewed.dat").write_bytes(
            f"reviewed {directory}\n".encode("ascii")
        )

    import tools.model.generate_mjcf as model_generator
    import tools.validation.run_contact_cases as contact_runner

    monkeypatch.setattr(model_generator, "PROJECT_ROOT", source)
    monkeypatch.setattr(model_generator, "ASSET_DIR", source / "assets")
    monkeypatch.setattr(model_generator, "MODEL_DIR", source / "models")
    monkeypatch.setattr(model_generator, "INCLUDE_DIR", source / "models" / "includes")
    monkeypatch.setattr(model_generator, "_require_assets", lambda: None)
    model_generator.generate_model("sdf", source / "models" / "generated.xml")
    contact_runner._write_document(
        source / "reports" / "generated.json",
        {"results": [], "schema_version": 3},
    )
    write_manifest(source)

    git_dir = tmp_path / "external.git"
    subprocess.run(
        ["git", "init", "--separate-git-dir", str(git_dir), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            f"--git-dir={git_dir}",
            f"--work-tree={source}",
            "add",
            "-A",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    fresh = tmp_path / "fresh checkout"
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            f"--git-dir={git_dir}",
            f"--work-tree={source}",
            "checkout-index",
            "-a",
            f"--prefix={fresh.as_posix()}/",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    verification = subprocess.run(
        [sys.executable, "-m", "tools.reporting.generate_manifest", "--verify"],
        cwd=fresh,
        capture_output=True,
        text=True,
    )
    mismatches = []
    for line in (fresh / "reports" / "final_file_manifest.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        expected, relative = line.split("  ", maxsplit=1)
        actual = hashlib.sha256((fresh / relative).read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(relative)

    assert verification.returncode == 0, verification.stdout + verification.stderr
    assert mismatches == []
    assert (fresh / "assets" / "reviewed.stl").read_bytes() == (
        b"solid text_like_stl\nendsolid text_like_stl\n"
    )
    assert (fresh / "source_cad.step").read_bytes() == (
        b"ISO-10303-21;\r\nHEADER;\r\nENDSEC;\r\nEND-ISO-10303-21;\r\n"
    )
