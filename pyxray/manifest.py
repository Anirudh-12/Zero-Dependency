"""
manifest.py — Read project dependency declarations.

Supports:
    pyproject.toml  — [project] dependencies = [...]
    requirements.txt — one requirement per line

Uses only:
    tomllib (stdlib, Python 3.11+)
    pathlib / os (stdlib)

Replaces: poetry, pip, toml/tomli (third-party)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from pyxray.models import Project, Requirement, normalize_name
from pyxray.requirements import parse_requirement

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — we target 3.12 but keep this for safety
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------

def _parse_requirements_file(path: Path) -> tuple[list[Requirement], list[str]]:
    """Parse a requirements.txt file.

    Returns (requirements, warnings).
    Skips blank lines, comments (#), -r/-c/-i/-f flags gracefully.
    """
    reqs: list[Requirement] = []
    warnings: list[str] = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        warnings.append(f"could not read {path}: {exc}")
        return reqs, warnings

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # pip options: -r, -c, -i, -f, --index-url, etc.
        if line.startswith("-"):
            warnings.append(
                f"{path.name}:{lineno}: pip option ignored: {line!r}"
            )
            continue
        req = parse_requirement(line)
        if req.parse_error == "empty" or req.parse_error == "comment line":
            continue
        if req.parse_error and req.name:
            warnings.append(
                f"{path.name}:{lineno}: parse warning for {req.name!r}: {req.parse_error}"
            )
        if not req.name:
            warnings.append(f"{path.name}:{lineno}: could not parse line: {line!r}")
            continue
        reqs.append(req)

    return reqs, warnings


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------

def _parse_pyproject(path: Path) -> tuple[str, list[Requirement], list[str]]:
    """Parse [project] name and dependencies from a pyproject.toml.

    Returns (project_name, requirements, warnings).
    """
    warnings: list[str] = []
    name = path.parent.name  # fallback

    if tomllib is None:
        warnings.append(
            "tomllib not available (Python < 3.11); pyproject.toml not parsed"
        )
        return name, [], warnings

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        warnings.append(f"could not parse {path}: {exc}")
        return name, [], warnings

    project = data.get("project", {})
    name = project.get("name", name)

    raw_deps: list[str] = project.get("dependencies", [])

    reqs: list[Requirement] = []
    for raw in raw_deps:
        req = parse_requirement(raw)
        if req.parse_error and req.name:
            warnings.append(f"pyproject.toml: parse warning for {raw!r}: {req.parse_error}")
        if req.name:
            reqs.append(req)

    # Also try PEP 735 dependency-groups (optional, best-effort)
    dep_groups: dict = data.get("dependency-groups", {})
    if dep_groups and not reqs:
        # Only warn when [project].dependencies is empty — acts as a "did you mean?" hint.
        # When [project].dependencies is populated, dependency-groups are dev/test extras
        # that PyXRay intentionally skips (they are not runtime dependencies).
        warnings.append(
            "pyproject.toml: [dependency-groups] found but [project].dependencies is empty. "
            "PyXRay reads runtime deps from [project].dependencies only."
        )

    # tool.poetry fallback
    poetry = data.get("tool", {}).get("poetry", {})
    if not reqs and poetry:
        warnings.append(
            "pyproject.toml: [tool.poetry] detected; "
            "reading tool.poetry.dependencies"
        )
        name = poetry.get("name", name)
        for pkg_name, constraint in poetry.get("dependencies", {}).items():
            if pkg_name.lower() == "python":
                continue
            if isinstance(constraint, str):
                raw = f"{pkg_name}{constraint}" if constraint not in ("*", "") else pkg_name
            else:
                raw = pkg_name
            req = parse_requirement(raw)
            if req.name:
                reqs.append(req)

    return name, reqs, warnings


# ---------------------------------------------------------------------------
# Project discovery
# ---------------------------------------------------------------------------

def discover_project(root: Optional[str] = None) -> tuple[Project, list[str]]:
    """Discover project metadata from *root* directory.

    Search order:
        1. pyproject.toml
        2. requirements.txt

    Returns (Project, warnings).
    """
    root_path = Path(root).resolve() if root else Path.cwd()
    warnings: list[str] = []
    declared: list[Requirement] = []
    project_name = root_path.name

    # ---- pyproject.toml ------------------------------------------------
    pyproject = root_path / "pyproject.toml"
    if pyproject.exists():
        name, reqs, w = _parse_pyproject(pyproject)
        project_name = name
        declared.extend(reqs)
        warnings.extend(w)

    # ---- requirements.txt (supplement, not duplicate) ------------------
    req_files = [
        root_path / "requirements.txt",
        root_path / "requirements" / "base.txt",
        root_path / "requirements" / "prod.txt",
    ]
    seen_names: set[str] = {normalize_name(r.name) for r in declared}

    for req_file in req_files:
        if req_file.exists():
            reqs, w = _parse_requirements_file(req_file)
            warnings.extend(w)
            for r in reqs:
                if r.name and normalize_name(r.name) not in seen_names:
                    declared.append(r)
                    seen_names.add(normalize_name(r.name))

    if not declared:
        warnings.append(
            "No project dependencies found. "
            "PyXRay will analyse the installed environment without a project root."
        )

    # ---- Source roots ---------------------------------------------------
    source_roots: list[str] = []
    for candidate in ["src", ".", project_name.replace("-", "_")]:
        p = root_path / candidate
        if p.is_dir():
            source_roots.append(str(p))

    return (
        Project(
            name=project_name,
            root=str(root_path),
            declared=declared,
            source_roots=source_roots[:3],  # cap at 3 sensible roots
        ),
        warnings,
    )
