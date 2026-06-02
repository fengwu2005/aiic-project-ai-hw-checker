from __future__ import annotations

from pathlib import Path

from cocode_viva.config import EXPECTED_FILES


def _normalize(path: Path) -> str:
    return path.as_posix().lower().strip("/")


def _find_by_suffix(root: Path, expected: str) -> Path | None:
    expected_norm = expected.lower()
    for file_path in root.rglob("*"):
        if file_path.is_file() and _normalize(file_path.relative_to(root)).endswith(expected_norm):
            return file_path
    return None


def read_expected_materials(root: Path) -> dict:
    materials = {}
    missing = []

    for key, expected in EXPECTED_FILES.items():
        path = _find_by_suffix(root, expected)
        if not path:
            missing.append(expected)
            materials[key] = {
                "expected": expected,
                "found": None,
                "text": "",
                "chars": 0,
            }
            continue

        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        materials[key] = {
            "expected": expected,
            "found": path.relative_to(root).as_posix(),
            "text": text,
            "chars": len(text),
        }

    return {
        "materials": materials,
        "missing": missing,
    }

