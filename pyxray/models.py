"""
models.py — Core data structures for PyXRay.

All data flows through these immutable-ish dataclasses. No third-party
libraries. dataclasses + typing only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Package normalisation
# ---------------------------------------------------------------------------

_NORMALIZE_RE = re.compile(r"[-_.]+")


def normalize_name(name: str) -> str:
    """Return the PEP-503 / PEP-508 canonical package name.

    Equivalent to what ``packaging.utils.canonicalize_name`` does:
    lower-case and collapse runs of [-_.] to a single hyphen.

    We intentionally do NOT import ``packaging``; this is a direct
    implementation of the same one-liner normalisation rule defined in
    PEP 503 and referenced in PEP 508.

    Limitation: very exotic Unicode package names are not tested.
    """
    return _NORMALIZE_RE.sub("-", name).lower()


# ---------------------------------------------------------------------------
# Requirement (parsed PEP 508 dependency string)
# ---------------------------------------------------------------------------

@dataclass
class Specifier:
    """A single version specifier, e.g. ``>=2.0``."""
    operator: str   # one of ==, !=, >=, <=, >, <, ~=, ===
    version: str

    def __str__(self) -> str:
        return f"{self.operator}{self.version}"


@dataclass
class Requirement:
    """Structured representation of a PEP 508 requirement string.

    Fields
    ------
    raw:            The original unparsed string.
    name:           Display name as found in the metadata.
    normalized_name: PEP-503 canonical name (lower, hyphens).
    extras:         Frozenset of requested extras, e.g. {"security"}.
    specifiers:     List of version specifiers.
    marker:         Raw marker expression string (unparsed beyond stripping).
    parse_error:    Non-None if the string could not be fully parsed.
    """
    raw: str
    name: str
    normalized_name: str
    extras: frozenset[str]
    specifiers: list[Specifier]
    marker: Optional[str] = None
    parse_error: Optional[str] = None

    def __str__(self) -> str:
        specs = ",".join(str(s) for s in self.specifiers)
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        marker = f" ; {self.marker}" if self.marker else ""
        return f"{self.name}{extras}{specs}{marker}"


# ---------------------------------------------------------------------------
# Package (an installed distribution)
# ---------------------------------------------------------------------------

@dataclass
class Package:
    """An installed Python distribution as seen by importlib.metadata.

    Fields
    ------
    name:             Display name from distribution metadata.
    normalized_name:  PEP-503 canonical name.
    version:          Installed version string.
    raw_requires:     List of raw dependency strings.
    metadata_path:    Path to the .dist-info directory (for tracing).
    """
    name: str
    normalized_name: str
    version: str
    raw_requires: list[str] = field(default_factory=list)
    metadata_path: Optional[str] = None
    
    _requires_cache: Optional[list[Requirement]] = field(default=None, init=False, repr=False)
    _top_level_cache: Optional[list[str]] = field(default=None, init=False, repr=False)

    @property
    def requires(self) -> list[Requirement]:
        if self._requires_cache is None:
            from pyxray.requirements import parse_requirement
            self._requires_cache = [parse_requirement(r) for r in self.raw_requires]
        return self._requires_cache

    @requires.setter
    def requires(self, value: list[Requirement]) -> None:
        self._requires_cache = value

    @property
    def top_level_names(self) -> list[str]:
        if self._top_level_cache is None:
            import importlib.metadata
            from pyxray.metadata import _get_top_level_names
            try:
                # We use the name to find the distribution. If it's a lockfile pkg
                # that is NOT installed, this throws PackageNotFoundError and returns [].
                dist = importlib.metadata.distribution(self.name)
                self._top_level_cache = _get_top_level_names(dist)
            except importlib.metadata.PackageNotFoundError:
                self._top_level_cache = []
        return self._top_level_cache

    @top_level_names.setter
    def top_level_names(self, value: list[str]) -> None:
        self._top_level_cache = value

    def __hash__(self) -> int:
        return hash(self.normalized_name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Package):
            return NotImplemented
        return self.normalized_name == other.normalized_name


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------

@dataclass
class DependencyGraph:
    """Directed dependency graph.

    Edges are stored in two directions for efficient traversal:

    forward[A] = {B, C, ...}   means A depends on B, C, …
    reverse[B] = {A, D, ...}   means B is depended on by A, D, …

    Nodes are normalized package names (strings).
    packages maps normalized_name → Package for metadata lookup.
    roots is the set of "direct" project-declared dependencies.
    """
    packages: dict[str, Package] = field(default_factory=dict)
    forward: dict[str, set[str]] = field(default_factory=dict)
    reverse: dict[str, set[str]] = field(default_factory=dict)
    roots: set[str] = field(default_factory=set)
    # Packages that were referenced but not found in installed metadata
    missing: set[str] = field(default_factory=set)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_package(self, pkg: Package) -> None:
        self.packages[pkg.normalized_name] = pkg
        self.forward.setdefault(pkg.normalized_name, set())
        self.reverse.setdefault(pkg.normalized_name, set())

    def add_edge(self, from_norm: str, to_norm: str) -> None:
        """Record that ``from_norm`` depends on ``to_norm``."""
        self.forward.setdefault(from_norm, set()).add(to_norm)
        self.reverse.setdefault(to_norm, set()).add(from_norm)
        # Ensure both keys exist in the reverse map
        self.reverse.setdefault(from_norm, set())
        self.forward.setdefault(to_norm, set())

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def dependencies_of(self, norm_name: str) -> set[str]:
        """Return direct dependencies of *norm_name* (forward edges)."""
        return self.forward.get(norm_name, set())

    def dependents_of(self, norm_name: str) -> set[str]:
        """Return packages that directly depend on *norm_name* (reverse edges)."""
        return self.reverse.get(norm_name, set())

    def all_nodes(self) -> set[str]:
        return set(self.packages.keys())

    def edge_count(self) -> int:
        return sum(len(v) for v in self.forward.values())


# ---------------------------------------------------------------------------
# Project (the thing being analysed)
# ---------------------------------------------------------------------------

@dataclass
class Project:
    """Represents the user's project being analysed.

    Fields
    ------
    name:         Project name (from pyproject.toml or directory name).
    root:         Absolute path to the project root directory.
    declared:     Requirements declared in pyproject.toml / requirements.txt.
    source_roots: Directories to scan for .py files.
    """
    name: str
    root: str
    declared: list[Requirement] = field(default_factory=list)
    source_roots: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Source import (from AST analysis)
# ---------------------------------------------------------------------------

@dataclass
class SourceImport:
    """A single import statement found in source code.

    Fields
    ------
    module:   Top-level module name (e.g. "requests" for ``import requests``
              or ``from requests import get``).
    file:     Relative path to the source file.
    line:     1-based line number.
    col:      0-based column offset.
    is_from:  True if this is a ``from X import Y`` form.
    """
    module: str
    file: str
    line: int
    col: int
    is_from: bool = False


# ---------------------------------------------------------------------------
# Analysis result (top-level aggregate)
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """Everything PyXRay computed for one invocation."""
    project: Project
    graph: DependencyGraph
    source_imports: list[SourceImport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
