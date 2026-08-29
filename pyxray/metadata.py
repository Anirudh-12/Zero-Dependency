"""
metadata.py — Discover installed distributions using importlib.metadata.

Replaces: pipdeptree, pip show, packaging

Uses only:
    importlib.metadata (stdlib, Python 3.8+)
    importlib.resources (stdlib)

Reads:
    - Distribution name, version
    - Requires-Dist entries → parsed via requirements.py
    - top_level.txt (best-effort, often absent in modern wheels)
    - RECORD file → extract top-level import names as fallback
"""

from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path
from typing import Optional

from pyxray.models import Package, normalize_name
from pyxray.requirements import parse_requirement

# ---------------------------------------------------------------------------
# Top-level import name discovery
# ---------------------------------------------------------------------------


def _top_level_from_top_level_txt(dist: importlib.metadata.Distribution) -> list[str]:
    """Read top_level.txt if present (old-style wheel/egg metadata)."""
    try:
        text = dist.read_text("top_level.txt")
        if text:
            return [line.strip() for line in text.splitlines() if line.strip()]
    except Exception:
        pass
    return []


def _top_level_from_record(dist: importlib.metadata.Distribution) -> list[str]:
    """Infer top-level import names from the RECORD file.

    RECORD lists every installed file relative to site-packages.
    We look for:
        somepkg/__init__.py  → somepkg
        somepkg.py           → somepkg
    and return the unique first path component (excluding .dist-info).
    """
    try:
        record_text = dist.read_text("RECORD")
        if not record_text:
            return []
    except Exception:
        return []

    names: set[str] = set()
    for line in record_text.splitlines():
        path_part = line.split(",")[0].strip()
        if not path_part:
            continue
        parts = Path(path_part).parts
        if not parts:
            continue
        top = parts[0]
        # Skip .dist-info and .data directories
        if top.endswith(".dist-info") or top.endswith(".data"):
            continue
        # Strip .py suffix for single-file modules
        if top.endswith(".py"):
            top = top[:-3]
        if top and not top.startswith("_") or top == "__future__":
            names.add(top)
    return sorted(names)


def _get_top_level_names(dist: importlib.metadata.Distribution) -> list[str]:
    """Best-effort list of importable names provided by *dist*."""
    names = _top_level_from_top_level_txt(dist)
    if names:
        return names
    return _top_level_from_record(dist)


# ---------------------------------------------------------------------------
# Distribution → Package
# ---------------------------------------------------------------------------


def _dist_to_package(dist: importlib.metadata.Distribution) -> Package:
    """Convert an importlib.metadata Distribution to a Package."""
    meta = dist.metadata
    name: str = meta["Name"] or ""
    version: str = meta["Version"] or "unknown"
    normalized = normalize_name(name)

    # Requires-Dist can appear multiple times in metadata
    raw_requires: list[str] = meta.get_all("Requires-Dist") or []  # type: ignore[attr-defined]

    parsed_requires = [parse_requirement(r) for r in raw_requires]

    top_level = _get_top_level_names(dist)

    # Attempt to locate the .dist-info path
    try:
        meta_path = str(dist._path)  # type: ignore[attr-defined]
    except AttributeError:
        meta_path = None

    return Package(
        name=name,
        normalized_name=normalized,
        version=version,
        requires=parsed_requires,
        top_level_names=top_level,
        metadata_path=meta_path,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover_all_installed() -> dict[str, Package]:
    """Return a dict of normalized_name → Package for every installed dist.

    Uses importlib.metadata.distributions() which iterates all installed
    distributions in the current Python environment (site-packages etc.).
    """
    packages: dict[str, Package] = {}
    for dist in importlib.metadata.distributions():
        try:
            pkg = _dist_to_package(dist)
        except Exception as exc:
            # Corrupt or unusual metadata — skip and warn via stderr
            _warn(f"could not read distribution metadata: {exc}")
            continue
        if pkg.normalized_name:
            # If the same normalized name appears twice (editable installs,
            # multiple site-packages), keep the first we see.  Duplicate
            # detection lives in the graph layer.
            if pkg.normalized_name not in packages:
                packages[pkg.normalized_name] = pkg

    return packages


def get_package(name: str) -> Optional[Package]:
    """Fetch metadata for a single named distribution, or None if not found."""
    try:
        dist = importlib.metadata.distribution(name)
        return _dist_to_package(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def _warn(msg: str) -> None:
    print(f"[pyxray] WARNING: {msg}", file=sys.stderr)
