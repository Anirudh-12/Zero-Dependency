"""
analysis.py — Graph algorithms for PyXRay.

All algorithms are implemented from scratch using only Python's standard
library.  Replaces: networkx.

Algorithms implemented:
    - BFS / DFS traversal
    - Depth calculation (BFS from roots)
    - Reachability (forward + reverse)
    - Cycle detection (DFS node-colouring)
    - Longest path (topological sort + DP on DAG, with cycle guard)
    - Hotspot ranking (in-degree count)
    - Duplicate version detection (from installed packages)
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from pyxray.models import DependencyGraph, Package

# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


def reachable_from(graph: DependencyGraph, start: str) -> set[str]:
    """Return all nodes reachable forward from *start* (including start)."""
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for dep in graph.forward.get(node, set()):
            if dep not in visited:
                queue.append(dep)
    return visited


def reachable_reverse(graph: DependencyGraph, start: str) -> set[str]:
    """Return all nodes that have *start* in their transitive forward closure.

    In other words: who depends on *start*, transitively?
    """
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for dep in graph.reverse.get(node, set()):
            if dep not in visited:
                queue.append(dep)
    # Exclude start itself
    visited.discard(start)
    return visited


# ---------------------------------------------------------------------------
# Shortest paths (why / impact)
# ---------------------------------------------------------------------------


def find_paths(
    graph: DependencyGraph,
    start: str,
    target: str,
    max_paths: int = 5,
    max_depth: int = 20,
) -> list[list[str]]:
    """Find up to *max_paths* shortest paths from *start* to *target*.

    Uses BFS so the first paths found are the shortest.
    Returns list of paths (each path is a list of node names start→target).
    """
    if start == target:
        return [[start]]

    results: list[list[str]] = []
    # BFS: each queue entry is the current path
    queue: deque[list[str]] = deque([[start]])
    visited_at_depth: dict[tuple[str, int], bool] = {}

    while queue and len(results) < max_paths:
        path = queue.popleft()
        current = path[-1]

        if len(path) > max_depth:
            continue

        for neighbor in graph.forward.get(current, set()):
            new_path = path + [neighbor]
            if neighbor == target:
                results.append(new_path)
            else:
                key = (neighbor, len(new_path))
                if key not in visited_at_depth:
                    visited_at_depth[key] = True
                    queue.append(new_path)

    return results


def find_reverse_paths(
    graph: DependencyGraph,
    target: str,
    roots: set[str],
    max_paths: int = 5,
    max_depth: int = 20,
) -> list[list[str]]:
    """Find paths from any root to *target* via reverse traversal.

    Used for the ``why`` command.
    """
    paths: list[list[str]] = []
    for root in sorted(roots):
        new = find_paths(
            graph, root, target, max_paths=max_paths - len(paths), max_depth=max_depth
        )
        paths.extend(new)
        if len(paths) >= max_paths:
            break
    return paths[:max_paths]


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def find_cycles(graph: DependencyGraph) -> list[list[str]]:
    """Detect all simple dependency cycles using DFS node colouring.

    Returns a list of cycles; each cycle is a list of node names forming
    the loop (the first node is repeated at the end for clarity).

    Colour scheme:
        WHITE (0) = unvisited
        GREY  (1) = in current DFS stack
        BLACK (2) = fully processed
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {n: WHITE for n in graph.all_nodes()}
    parent: dict[str, Optional[str]] = {n: None for n in graph.all_nodes()}
    cycles: list[list[str]] = []
    seen_cycles: set[frozenset[str]] = set()

    def dfs(node: str, stack: list[str]) -> None:
        colour[node] = GREY
        stack.append(node)

        for neighbour in sorted(graph.forward.get(node, set())):
            if colour.get(neighbour, WHITE) == GREY:
                # Back edge → cycle found
                idx = stack.index(neighbour)
                cycle = stack[idx:] + [neighbour]
                key = frozenset(cycle)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(cycle)
            elif colour.get(neighbour, WHITE) == WHITE:
                parent[neighbour] = node
                dfs(neighbour, stack)

        stack.pop()
        colour[node] = BLACK

    for node in sorted(graph.all_nodes()):
        if colour[node] == WHITE:
            dfs(node, [])

    return cycles


# ---------------------------------------------------------------------------
# Depth / BFS levels
# ---------------------------------------------------------------------------


def compute_depths(graph: DependencyGraph) -> dict[str, int]:
    """BFS from roots; return depth (0-based) of each reachable node.

    Root nodes get depth 0. Missing nodes get depth -1 (not reached from roots).
    """
    depths: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()

    for root in graph.roots:
        if root in graph.packages and root not in depths:
            depths[root] = 0
            queue.append((root, 0))

    while queue:
        node, depth = queue.popleft()
        for dep in graph.forward.get(node, set()):
            if dep not in depths:
                depths[dep] = depth + 1
                queue.append((dep, depth + 1))

    return depths


# ---------------------------------------------------------------------------
# Hotspots (in-degree)
# ---------------------------------------------------------------------------


def compute_in_degrees(graph: DependencyGraph) -> dict[str, int]:
    """Return in-degree (number of dependents) for every node."""
    return {node: len(graph.reverse.get(node, set())) for node in graph.all_nodes()}


# ---------------------------------------------------------------------------
# Duplicate versions
# ---------------------------------------------------------------------------


def find_duplicate_versions(
    installed: dict[str, Package],
    graph: DependencyGraph,
) -> dict[str, list[str]]:
    """Detect packages that appear with multiple versions in installed metadata.

    Because importlib.metadata normalises names, genuine duplicates only arise
    when the same distribution was installed in multiple site-packages paths
    (e.g. user-site + system-site) or via editable install alongside a wheel.

    We detect them by scanning raw distribution names via distributions().
    """
    import importlib.metadata

    name_to_versions: dict[str, list[str]] = {}
    for dist in importlib.metadata.distributions():
        try:
            meta = dist.metadata
            name = meta["Name"] or ""
            version = meta["Version"] or "?"
        except Exception:
            continue
        norm = _normalize_name_local(name)
        name_to_versions.setdefault(norm, [])
        if version not in name_to_versions[norm]:
            name_to_versions[norm].append(version)

    return {k: v for k, v in name_to_versions.items() if len(v) > 1}


def _normalize_name_local(name: str) -> str:
    import re

    return re.sub(r"[-_.]+", "-", name).lower()


# ---------------------------------------------------------------------------
# Longest chain (DAG path + cycle guard)
# ---------------------------------------------------------------------------


def find_longest_chain(
    graph: DependencyGraph,
    cycles: Optional[list[list[str]]] = None,
) -> list[str]:
    """Return a longest dependency chain starting from a root.

    If cycles exist, falls back to a cycle-aware DFS with a visited guard
    (so it terminates, but may not find the true longest path).
    """
    if cycles is None:
        cycles = find_cycles(graph)

    has_cycles = bool(cycles)

    if not has_cycles:
        return _longest_chain_dag(graph)
    else:
        return _longest_chain_with_cycles(graph)


def _longest_chain_dag(graph: DependencyGraph) -> list[str]:
    """Topological sort + DP to find the longest path in a DAG."""
    # Kahn's algorithm for topological sort
    in_deg: dict[str, int] = {n: 0 for n in graph.all_nodes()}
    for node in graph.all_nodes():
        for dep in graph.forward.get(node, set()):
            in_deg[dep] = in_deg.get(dep, 0) + 1

    queue: deque[str] = deque(n for n, d in in_deg.items() if d == 0)
    topo: list[str] = []
    while queue:
        node = queue.popleft()
        topo.append(node)
        for dep in graph.forward.get(node, set()):
            in_deg[dep] -= 1
            if in_deg[dep] == 0:
                queue.append(dep)

    # DP: dist[n] = (length, path) of longest path to n
    dist: dict[str, tuple[int, list[str]]] = {n: (0, [n]) for n in topo}
    for node in topo:
        cur_len, cur_path = dist[node]
        for dep in graph.forward.get(node, set()):
            if dep in dist:
                candidate = cur_len + 1
                if candidate > dist[dep][0]:
                    dist[dep] = (candidate, cur_path + [dep])

    if not dist:
        return []
    _, best_path = max(dist.values(), key=lambda x: x[0])
    return best_path


def _longest_chain_with_cycles(graph: DependencyGraph) -> list[str]:
    """DFS with visited guard (cycle-safe); finds a long but not guaranteed
    longest path from any root."""
    best: list[str] = []

    def dfs(node: str, path: list[str], visited: set[str]) -> None:
        nonlocal best
        if len(path) > len(best):
            best = path[:]
        for dep in graph.forward.get(node, set()):
            if dep not in visited:
                visited.add(dep)
                path.append(dep)
                dfs(dep, path, visited)
                path.pop()
                visited.discard(dep)

    for root in sorted(graph.roots):
        dfs(root, [root], {root})

    return best


# ---------------------------------------------------------------------------
# Stats summary
# ---------------------------------------------------------------------------


def compute_stats(graph: DependencyGraph) -> dict[str, object]:
    """Compute scalar graph metrics returned as a plain dict.

    All values are directly traceable to graph structure.
    """
    depths = compute_depths(graph)
    in_deg = compute_in_degrees(graph)
    cycles = find_cycles(graph)

    direct = len(graph.roots)
    total = len(graph.packages)
    transitive = total - direct
    edges = graph.edge_count()
    leaves = sum(1 for n in graph.all_nodes() if not graph.forward.get(n))
    max_depth = max(depths.values(), default=0)
    avg_depth = round(sum(depths.values()) / len(depths), 2) if depths else 0.0
    max_fan_out = max((len(v) for v in graph.forward.values()), default=0)
    max_fan_in = max(in_deg.values(), default=0)

    # Largest subtree (from any root)
    largest_subtree_root = ""
    largest_subtree_size = 0
    for root in graph.roots:
        size = len(reachable_from(graph, root))
        if size > largest_subtree_size:
            largest_subtree_size = size
            largest_subtree_root = root

    # Most depended upon
    if in_deg:
        hotspot = max(in_deg, key=lambda n: in_deg[n])
        hotspot_count = in_deg[hotspot]
    else:
        hotspot = ""
        hotspot_count = 0

    return {
        "direct_dependencies": direct,
        "transitive_dependencies": transitive,
        "total_packages": total,
        "dependency_edges": edges,
        "leaf_packages": leaves,
        "maximum_depth": max_depth,
        "average_depth": avg_depth,
        "maximum_fan_out": max_fan_out,
        "maximum_fan_in": max_fan_in,
        "cycle_count": len(cycles),
        "largest_subtree_root": largest_subtree_root,
        "largest_subtree_size": largest_subtree_size,
        "most_depended_upon": hotspot,
        "most_depended_upon_count": hotspot_count,
        "missing_packages": len(graph.missing),
    }


# ---------------------------------------------------------------------------
# Prune / reimplement candidate analysis
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from dataclasses import field as _field


@dataclass
class PruneCandidate:
    """A declared dependency flagged for potential removal or reimplementation.

    Every field is traceable to graph edges or AST nodes — no guessing.

    Signals
    -------
    transitive_count:   Number of packages in this dep's forward closure.
                        0 = leaf (no deps of its own).
    file_count:         Number of source files that import it (AST).
    symbol_count:       Number of distinct symbols imported from it (AST).
                        '*' = bare ``import pkg`` (full module used).
    is_transitively_covered:
                        True if this dep is already reachable as a
                        transitive dep of another declared dep —
                        so removing the direct declaration is safe today.

    Labels
    ------
    REIMPLEMENT:  Thin + narrow + shallow → strong candidate to rewrite
                  in stdlib. The package does little and you use little of it.
    REMOVE:       No static usage detected AND transitively covered.
                  Safe to remove from declared deps right now.
    UNDECLARE:    No static usage AND NOT transitively covered.
                  Not imported, but removing it changes the install set.
    COVERED:      Transitively covered; already arrives via another dep.
                  Removing the direct declaration is safe but subtle.
    KEEP:         Signals do not support removal. Leave it alone.
    """

    norm_name: str
    version: str
    label: str  # REIMPLEMENT / REMOVE / UNDECLARE / COVERED / KEEP
    confidence: str  # HIGH / MEDIUM / LOW
    transitive_count: int = 0
    file_count: int = 0
    symbol_count: int = 0
    symbols_used: list = _field(default_factory=list)
    files_using: list = _field(default_factory=list)
    is_transitively_covered: bool = False
    has_static_import: bool = False
    uses_full_module: bool = False
    reason: str = ""


def compute_prune_candidates(
    graph: "DependencyGraph",
    usage_map: dict,  # norm_name → SourceUsage
    thin_threshold: int = 3,  # transitive deps ≤ this → "thin"
    narrow_threshold: int = 3,  # files ≤ this → "narrow"
    shallow_threshold: int = 5,  # symbols ≤ this → "shallow"
) -> list[PruneCandidate]:
    """Score every direct declared dependency across three signals.

    Parameters
    ----------
    graph:             The dependency graph.
    usage_map:         Per-package source usage from ``scan_with_usage``.
    thin_threshold:    Max transitive deps to be considered "thin".
    narrow_threshold:  Max source files to be considered "narrow".
    shallow_threshold: Max imported symbols to be considered "shallow".

    Returns a list of PruneCandidate sorted by confidence then label.
    """
    candidates: list[PruneCandidate] = []

    for norm_name in sorted(graph.roots):
        pkg = graph.packages.get(norm_name)
        version = pkg.version if pkg else "?"

        # ── Signal 1: Thin graph ─────────────────────────────────────────
        # How many packages does this dep bring with it?
        subtree = reachable_from(graph, norm_name)
        subtree.discard(norm_name)  # exclude self
        transitive_count = len(subtree)
        is_thin = transitive_count <= thin_threshold

        # ── Signal 2: Narrow usage ───────────────────────────────────────
        usage = usage_map.get(norm_name)
        has_static_import = usage is not None and usage.file_count > 0
        file_count = usage.file_count if usage else 0
        is_narrow = file_count <= narrow_threshold

        # ── Signal 3: Shallow API usage ──────────────────────────────────
        symbol_count = usage.symbol_count if usage else 0
        uses_full_module = usage.uses_full_module if usage else False
        # If bare `import pkg` was used, treat as full API → not shallow
        is_shallow = (not uses_full_module) and (symbol_count <= shallow_threshold)
        symbols_used = sorted(usage.symbols - {"*", "?"}) if usage else []
        files_using = sorted(usage.files) if usage else []

        # ── Signal 4: Transitively covered ───────────────────────────────
        # Is this package reachable as a transitive dep of another root?
        other_roots = graph.roots - {norm_name}
        is_covered = any(
            norm_name in reachable_from(graph, other) - {other} for other in other_roots
        )

        # ── Classify ─────────────────────────────────────────────────────
        signals_for_reimplement = sum([is_thin, is_narrow, is_shallow])

        if is_thin and is_narrow and is_shallow and not uses_full_module:
            label = "REIMPLEMENT"
            confidence = "HIGH" if transitive_count == 0 else "MEDIUM"
            reason = (
                f"Zero deps of its own"
                if transitive_count == 0
                else f"Only {transitive_count} transitive dep(s)"
            )
            reason += (
                f"; used in {file_count} file(s)"
                f"; only {symbol_count} symbol(s) imported"
            )
            if symbols_used:
                reason += f": {', '.join(symbols_used[:5])}"

        elif not has_static_import and is_covered:
            label = "REMOVE"
            confidence = "HIGH"
            reason = (
                "No static import detected AND already arrives transitively "
                "via another declared dep — safe to remove from declared deps"
            )

        elif not has_static_import and not is_covered:
            label = "UNDECLARE"
            confidence = "MEDIUM"
            reason = (
                "No static import detected. "
                "Removing from declared deps would change the install set — "
                "verify it is not used via entry points or dynamic imports"
            )

        elif is_covered and not is_thin:
            label = "COVERED"
            confidence = "MEDIUM"
            reason = (
                "Already arrives as a transitive dep of another declared dep. "
                "Removing the direct declaration is safe but changes pinning semantics"
            )

        else:
            label = "KEEP"
            confidence = "LOW"
            reason = (
                f"{transitive_count} transitive dep(s), "
                f"used in {file_count} file(s), "
                f"{symbol_count} symbol(s) — not a strong removal candidate"
            )

        candidates.append(
            PruneCandidate(
                norm_name=norm_name,
                version=version,
                label=label,
                confidence=confidence,
                transitive_count=transitive_count,
                file_count=file_count,
                symbol_count=symbol_count,
                symbols_used=symbols_used,
                files_using=files_using,
                is_transitively_covered=is_covered,
                has_static_import=has_static_import,
                uses_full_module=uses_full_module,
                reason=reason,
            )
        )

    # Sort: actionable first (REMOVE > REIMPLEMENT > UNDECLARE > COVERED > KEEP)
    _order = {"REMOVE": 0, "REIMPLEMENT": 1, "UNDECLARE": 2, "COVERED": 3, "KEEP": 4}
    candidates.sort(key=lambda c: (_order.get(c.label, 9), c.norm_name))
    return candidates
