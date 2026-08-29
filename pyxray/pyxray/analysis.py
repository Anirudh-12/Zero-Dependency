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
