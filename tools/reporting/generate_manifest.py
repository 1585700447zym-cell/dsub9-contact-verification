from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Iterable, Sequence


REVIEW_DIRECTORIES = ("assets", "models", "plugins", "tools", "tests", "reports")
REVIEW_ROOT_FILES = (
    "README.md",
    "pyproject.toml",
    ".gitattributes",
    ".gitignore",
)
MANIFEST_RELATIVE_PATH = Path("reports/final_file_manifest.txt")
EXCLUDED_DIRECTORY_NAMES = {"__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc"}


def _reviewed_files(project_root: Path) -> Iterable[tuple[str, Path]]:
    for name in REVIEW_ROOT_FILES:
        path = project_root / name
        if path.is_file():
            yield path.relative_to(project_root).as_posix(), path

    for directory in REVIEW_DIRECTORIES:
        audit_root = project_root / directory
        if not audit_root.is_dir():
            raise FileNotFoundError(f"review directory does not exist: {audit_root}")
        for current, directories, filenames in os.walk(audit_root):
            directories[:] = [
                name for name in directories if name not in EXCLUDED_DIRECTORY_NAMES
            ]
            for filename in filenames:
                path = Path(current) / filename
                relative = path.relative_to(project_root)
                if relative == MANIFEST_RELATIVE_PATH:
                    continue
                if path.suffix.lower() in EXCLUDED_SUFFIXES or not path.is_file():
                    continue
                yield relative.as_posix(), path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(project_root: Path) -> str:
    root = Path(project_root).resolve()
    entries = sorted(_reviewed_files(root), key=lambda item: item[0])
    return "".join(f"{_sha256(path)}  {relative}\n" for relative, path in entries)


def write_manifest(project_root: Path) -> Path:
    root = Path(project_root).resolve()
    output = root / MANIFEST_RELATIVE_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(build_manifest(root))
    return output


def verify_manifest(project_root: Path) -> bool:
    root = Path(project_root).resolve()
    manifest = root / MANIFEST_RELATIVE_PATH
    return manifest.is_file() and manifest.read_text(encoding="utf-8") == build_manifest(
        root
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify the reviewed D-sub9 file manifest."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="project root (default: current directory)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="return success only when the checked-in manifest is current",
    )
    args = parser.parse_args(argv)

    if args.verify:
        if verify_manifest(args.project_root):
            print("manifest is current")
            return 0
        print("manifest is missing or stale")
        return 1

    output = write_manifest(args.project_root)
    entry_count = len(output.read_text(encoding="utf-8").splitlines())
    print(f"wrote {entry_count} entries to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
