"""Zip the cr folder. Usage: python zip_cr.py [output.zip]"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
EXCLUDED_DIRS = {"__pycache__", ".git", ".venv", ".pytest_cache", ".streamlit"}
EXCLUDED_SUFFIXES = {".pyc", ".zip"}


def build_zip(output: Path) -> int:
    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob("*")):
            relative = path.relative_to(SOURCE)
            if not path.is_file() or path.suffix in EXCLUDED_SUFFIXES:
                continue
            if EXCLUDED_DIRS.intersection(relative.parts):
                continue
            archive.write(path, Path(SOURCE.name) / relative)
            count += 1
    return count


if __name__ == "__main__":
    # Default output sits beside the folder so the archive never contains itself.
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE.parent / f"{SOURCE.name}.zip"
    files = build_zip(target.resolve())
    print(f"Wrote {files} files to {target.resolve()}")
