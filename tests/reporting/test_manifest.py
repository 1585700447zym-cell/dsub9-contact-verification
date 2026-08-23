from __future__ import annotations

from pathlib import Path

from tools.reporting.generate_manifest import (
    build_manifest,
    verify_manifest,
    write_manifest,
)


REVIEW_ROOTS = ("assets", "models", "plugins", "tools", "tests", "reports")


def make_project(root: Path) -> None:
    for directory in REVIEW_ROOTS:
        (root / directory).mkdir(parents=True)
    (root / "README.md").write_text("read me\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")


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
    expected = {".gitignore", "README.md", "pyproject.toml"}
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
