from __future__ import annotations

from pathlib import Path

MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"


def list_manifests() -> list[Path]:
    return sorted(MANIFEST_DIR.glob("*.yaml"))
