"""
lockfile.py — Parse lock files to reconstruct dependency graphs offline.

Replaces: needing packages installed to analyse them.

Supports:
    uv.lock      — TOML, [[package]] sections with dependencies = [{name=...}]
    poetry.lock  — TOML, [[package]] with [package.dependencies]
    requirements.txt (pinned, pip-compile output) — flat pinned list

Uses only:
    tomllib  (stdlib Python 3.11+)
    re       (stdlib)
    json     (stdlib)

This allows PyXRay to analyse a project's dependency graph WITHOUT
having any of the packages installed in the current environment.
The lock file already contains the fully-resolved graph.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

from pyxray.models import DependencyGraph, Package, normalize_name
from pyxray.requirements import parse_requirement

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Lock file detection
# ---------------------------------------------------------------------------

LOCK_FILE_NAMES = [
    "uv.lock",
    "poetry.lock",
]


def detect_lockfile(root: str) -> Optional[Path]:
    """Return the first recognised lock file found in *root*, or None."""
    root_path = Path(root)
    for name in LOCK_FILE_NAMES:
        p = root_path / name
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# uv.lock parser
# ---------------------------------------------------------------------------


def _parse_uv_lock(path: Path) -> tuple[dict[str, Package], list[str]]:
    """Parse a uv.lock file.

    uv.lock format (TOML):
    ----------------------
        version = 1

        [[package]]
        name = "requests"
        version = "2.32.3"
        source = { registry = "https://pypi.org/simple" }
        dependencies = [
            { name = "certifi" },
            { name = "charset-normalizer" },
        ]

        [[package]]
        name = "certifi"
        version = "2024.2.2"
        ...

    Returns (packages_dict, warnings).
    """
    warnings: list[str] = []

    if tomllib is None:
        warnings.append("tomllib not available; cannot parse uv.lock")
        return {}, warnings

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        warnings.append(f"Could not parse {path.name}: {exc}")
        return {}, warnings

    packages: dict[str, Package] = {}
    raw_pkgs = data.get("package", [])

    for entry in raw_pkgs:
        name = entry.get("name", "")
        version = entry.get("version", "?")
        norm = normalize_name(name)

        # Build Requirement objects from dependency entries
        reqs = []
        for dep in entry.get("dependencies", []):
            dep_name = dep.get("name", "")
            if dep_name:
                req = parse_requirement(dep_name)
                reqs.append(req)

        # Also parse optional/dev deps if present
        # uv.lock groups optional deps under 'optional-dependencies'
        for _group, group_deps in entry.get("optional-dependencies", {}).items():
            for dep in group_deps:
                dep_name = dep.get("name", "")
                if dep_name:
                    reqs.append(parse_requirement(dep_name))

        pkg = Package(
            name=name,
            normalized_name=norm,
            version=version,
            requires=reqs,
            metadata_path=str(path),
        )

        if norm not in packages:
            packages[norm] = pkg

    return packages, warnings


# ---------------------------------------------------------------------------
# poetry.lock parser
# ---------------------------------------------------------------------------


def _parse_poetry_lock(path: Path) -> tuple[dict[str, Package], list[str]]:
    """Parse a poetry.lock file.

    poetry.lock format (TOML):
    --------------------------
        [[package]]
        name = "requests"
        version = "2.32.3"
        description = "..."
        optional = false
        python-versions = ">=3.8"

        [package.dependencies]
        certifi = ">=2017.4.17"
        charset-normalizer = ">=2,<4"
        idna = ">=2.5,<4"
        urllib3 = ">=1.21.1,<3"

        [package.extras]
        security = ["cryptography", "pyOpenSSL", "idna"]

    Returns (packages_dict, warnings).
    """
    warnings: list[str] = []

    if tomllib is None:
        warnings.append("tomllib not available; cannot parse poetry.lock")
        return {}, warnings

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        warnings.append(f"Could not parse {path.name}: {exc}")
        return {}, warnings

    packages: dict[str, Package] = {}
    raw_pkgs = data.get("package", [])

    for entry in raw_pkgs:
        name = entry.get("name", "")
        version = entry.get("version", "?")
        norm = normalize_name(name)

        reqs = []
        dep_table = entry.get("dependencies", {})
        for dep_name, constraint in dep_table.items():
            if dep_name.lower() == "python":
                continue
            # constraint can be str, dict, or list
            if isinstance(constraint, str):
                raw = (
                    f"{dep_name}{constraint}"
                    if constraint not in ("*", "")
                    else dep_name
                )
            elif isinstance(constraint, dict):
                # {version = ">=1.0", optional = true, markers = "..."}
                ver = constraint.get("version", "")
                marker = constraint.get("markers", "")
                optional = constraint.get("optional", False)
                if optional:
                    continue  # skip optional deps for clarity
                raw = f"{dep_name}{ver}"
                if marker:
                    raw += f" ; {marker}"
            elif isinstance(constraint, list):
                # multiple constraints — take first non-optional
                raw = dep_name
            else:
                raw = dep_name

            req = parse_requirement(raw)
            if req.name:
                reqs.append(req)

        pkg = Package(
            name=name,
            normalized_name=norm,
            version=version,
            requires=reqs,
            metadata_path=str(path),
        )

        if norm not in packages:
            packages[norm] = pkg

    return packages, warnings


# ---------------------------------------------------------------------------
# Pinned requirements.txt (pip-compile output)
# ---------------------------------------------------------------------------


def _parse_pinned_requirements(path: Path) -> tuple[dict[str, Package], list[str]]:
    """Parse a fully-pinned requirements.txt (e.g. pip-compile output).

    These files contain all transitive deps with ==version pins.
    They do NOT contain Requires-Dist info, so the resulting graph
    will have all packages as root-level nodes with no edges.

    Useful for: knowing exactly what's in the environment, duplicate detection.
    Not useful for: tree/why/impact (no edges).
    """
    warnings: list[str] = []
    packages: dict[str, Package] = {}

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        warnings.append(f"Could not read {path}: {exc}")
        return packages, warnings

    warnings.append(
        f"{path.name}: pinned requirements.txt has no Requires-Dist info; "
        "tree/why/impact will show no edges. Use uv.lock or poetry.lock for full graph."
    )

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        req = parse_requirement(line)
        if req.name and not req.parse_error:
            norm = req.normalized_name
            ver = req.specifiers[0].version if req.specifiers else "?"
            pkg = Package(
                name=req.name,
                normalized_name=norm,
                version=ver,
                requires=[],
                metadata_path=str(path),
            )
            if norm not in packages:
                packages[norm] = pkg

    return packages, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_lockfile(path: Path) -> tuple[dict[str, Package], list[str]]:
    """Parse the lock file at *path* and return (packages, warnings).

    Dispatches to the correct parser based on filename.
    """
    name = path.name.lower()
    if name == "uv.lock":
        return _parse_uv_lock(path)
    elif name == "poetry.lock":
        return _parse_poetry_lock(path)
    elif name.endswith(".txt"):
        return _parse_pinned_requirements(path)
    else:
        return {}, [f"Unrecognised lock file format: {path.name}"]


def build_graph_from_lockfile(
    lockfile_path: Path,
    declared_names: set[str],
) -> tuple[DependencyGraph, list[str]]:
    """Build a DependencyGraph entirely from a lock file.

    Parameters
    ----------
    lockfile_path:
        Path to the lock file (uv.lock, poetry.lock, etc.)
    declared_names:
        Normalized names of directly declared project dependencies
        (used to set graph.roots).

    Returns (DependencyGraph, warnings).
    """
    packages, warnings = load_lockfile(lockfile_path)

    graph = DependencyGraph()

    # Add all packages as nodes
    for pkg in packages.values():
        graph.add_package(pkg)

    # Add edges from Requires-Dist
    for norm_name, pkg in packages.items():
        for req in pkg.requires:
            if not req.name:
                continue
            dep_norm = req.normalized_name
            if dep_norm in packages:
                graph.add_edge(norm_name, dep_norm)
            # If dep not in lockfile, it's fine — cross-ref missing is optional

    # Set roots: packages that are declared project deps
    for norm in declared_names:
        if norm in packages:
            graph.roots.add(norm)
        else:
            # declared but not in lockfile
            graph.missing.add(norm)

    # If no declared names found, treat all packages with no in-edges as roots
    if not graph.roots:
        in_degrees = {n: 0 for n in graph.all_nodes()}
        for node in graph.all_nodes():
            for dep in graph.forward.get(node, set()):
                in_degrees[dep] = in_degrees.get(dep, 0) + 1
        graph.roots = {n for n, d in in_degrees.items() if d == 0}

    return graph, warnings
