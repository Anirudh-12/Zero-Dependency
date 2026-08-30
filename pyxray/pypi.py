"""
pypi.py — Fetch package metadata from PyPI JSON API.

Replaces: needing packages installed locally.

Uses only:
    urllib.request  (stdlib)
    urllib.error    (stdlib)
    json            (stdlib)

This is the ONLY module in PyXRay that makes network requests.
It is opt-in via the --pypi flag.
The tool is offline-first by default; this is an explicit escape hatch.

PyPI JSON API:
    https://pypi.org/pypi/{name}/json           → latest version metadata
    https://pypi.org/pypi/{name}/{version}/json → specific version metadata

Response includes:
    info.name
    info.version
    info.requires_dist   ← list of PEP 508 requirement strings
    info.requires_python

Rate limits: PyPI asks for reasonable use. We add a small delay between
requests and cache results in-process to avoid hammering the API.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from pyxray.models import DependencyGraph, Package, normalize_name
from pyxray.requirements import evaluate_marker, parse_requirement

# ---------------------------------------------------------------------------
# In-process cache (avoids re-fetching the same package twice per run)
# ---------------------------------------------------------------------------

_CACHE: dict[str, dict | None] = {}

PYPI_BASE = "https://pypi.org/pypi"
REQUEST_DELAY = 0.05  # 50ms between requests — polite to PyPI


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


def _fetch_json(url: str, timeout: float = 3.0, verbose: bool = False) -> dict | None:
    """Fetch *url* and parse JSON. Returns None on any error."""
    if url in _CACHE:
        return _CACHE[url]

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "pyxray/0.1.0 (hackathon; stdlib-only)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _CACHE[url] = data
        return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _CACHE[url] = None
        if verbose:
            import sys
            import traceback

            print(f"[pypi] HTTP error fetching {url}: {exc}", file=sys.stderr)
            traceback.print_exc()
        return None
    except Exception as exc:
        if verbose:
            import sys
            import traceback

            print(f"[pypi] Error fetching {url}: {exc}", file=sys.stderr)
            traceback.print_exc()
        _CACHE[url] = None
        return None


def fetch_package_metadata(
    name: str,
    version: str | None = None,
    verbose: bool = False,
) -> Package | None:
    """Fetch metadata for *name* (optionally at *version*) from PyPI.

    Returns a Package object or None if not found / network error.
    """
    norm = normalize_name(name)

    if version:
        url = f"{PYPI_BASE}/{name}/{version}/json"
    else:
        url = f"{PYPI_BASE}/{name}/json"

    if verbose:
        import sys
        print(f"  [pypi] fetching {name}...", file=sys.stderr)

    data = _fetch_json(url, verbose=verbose)
    if not data:
        return None

    info = data.get("info", {})
    pkg_name = info.get("name", name)
    pkg_version = info.get("version", version or "?")
    raw_requires = info.get("requires_dist") or []

    reqs = [parse_requirement(r) for r in raw_requires]

    return Package(
        name=pkg_name,
        normalized_name=normalize_name(pkg_name),
        version=pkg_version,
        requires=reqs,
        metadata_path=f"pypi:{pkg_name}=={pkg_version}",
    )


# ---------------------------------------------------------------------------
# Graph builder via PyPI
# ---------------------------------------------------------------------------


def build_graph_from_pypi(
    declared_reqs: list,  # list[Requirement]
    max_packages: int = 300,
    verbose: bool = False,
) -> tuple[DependencyGraph, list[str]]:
    """Build a full dependency graph by fetching metadata from PyPI.

    Starts from *declared_reqs* and BFS-traverses the graph,
    fetching each package's Requires-Dist from the PyPI JSON API.

    Parameters
    ----------
    declared_reqs:
        The project's directly declared requirements.
    max_packages:
        Safety cap — stop BFS after this many packages to prevent
        runaway fetching. Large graphs can require hundreds of requests.
    verbose:
        Print fetch progress to stderr.

    Returns (DependencyGraph, warnings).
    """
    from collections import deque

    warnings: list[str] = []
    graph = DependencyGraph()
    visited: set[str] = set()
    queue: deque[str] = deque()

    # Seed from declared deps
    for req in declared_reqs:
        if not req.name:
            continue
        norm = req.normalized_name
        graph.roots.add(norm)
        if norm not in visited:
            visited.add(norm)
            queue.append(norm)

    fetched = 0
    while queue and fetched < max_packages:
        norm_name = queue.popleft()
        fetched += 1

        pkg = fetch_package_metadata(norm_name, verbose=verbose)
        time.sleep(REQUEST_DELAY)

        if pkg is None:
            graph.missing.add(norm_name)
            stub = Package(
                name=norm_name,
                normalized_name=norm_name,
                version="?",
            )
            graph.add_package(stub)
            if verbose:
                print(f"  [pypi] not found: {norm_name}", file=sys.stderr)
            continue

        graph.add_package(pkg)

        for req in pkg.requires:
            if not req.name:
                continue
            # Evaluate environment markers
            if req.marker and not evaluate_marker(req.marker):
                continue
            dep_norm = req.normalized_name
            graph.add_edge(norm_name, dep_norm)
            if dep_norm not in visited:
                visited.add(dep_norm)
                queue.append(dep_norm)

    if queue:
        remaining = len(queue)
        warnings.append(
            f"PyPI fetch stopped at {max_packages} packages ({remaining} more unreached). "
            f"Use --max-packages N to increase the limit."
        )

    return graph, warnings


# ---------------------------------------------------------------------------
# Latest-version helper (used by cmd_outdated)
# ---------------------------------------------------------------------------


def fetch_latest_version(name: str, verbose: bool = False) -> str | None:
    """Return the latest version of *name* on PyPI, or None on error/not found.

    Uses the existing in-process _CACHE to avoid duplicate requests.
    """
    url = f"{PYPI_BASE}/{name}/json"
    data = _fetch_json(url, verbose=verbose)
    if not data:
        return None
    info = data.get("info", {})
    return info.get("version")
