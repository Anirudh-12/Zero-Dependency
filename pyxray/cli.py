"""
cli.py — Argument parsing and command dispatch for PyXRay.

Uses only: argparse (stdlib)
Replaces: click, typer, docopt
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Shared context (loaded once, shared across commands)
# ---------------------------------------------------------------------------


class Context:
    """Lazy-loaded analysis context shared across subcommands."""

    def __init__(
        self,
        project_root: Optional[str],
        no_color: bool,
        json_output: bool,
        quiet: bool,
        from_lock: Optional[str] = None,
        no_lock: bool = False,
        use_pypi: bool = False,
        max_packages: int = 300,
    ) -> None:
        self.project_root = project_root
        self.json_output = json_output
        self.quiet = quiet
        self.from_lock = from_lock  # explicit lock file path, or None = auto-detect
        self.no_lock = no_lock  # suppress auto-detection
        self.use_pypi = use_pypi  # fetch metadata from PyPI API
        self.max_packages = max_packages  # cap for PyPI BFS
        self._project = None
        self._installed = None
        self._graph = None
        self._warnings: list[str] = []
        self._graph_built = False

        # Configure output layer
        from pyxray import output as out

        out.set_color(not no_color)

    # ------------------------------------------------------------------
    # Lazy loaders
    # ------------------------------------------------------------------

    def get_installed(self) -> dict:
        if self._installed is None:
            from pyxray.metadata import discover_all_installed

            self._installed = discover_all_installed()
        return self._installed

    def get_project(self):
        if self._project is None:
            from pyxray.manifest import discover_project

            self._project, warnings = discover_project(self.project_root)
            self._warnings.extend(warnings)
        return self._project

    def get_graph(self):
        if not self._graph_built:
            project = self.get_project()
            self._graph_built = True

            # ── Mode 1: explicit lock file path ──────────────────────────
            if self.from_lock:
                from pathlib import Path
                from pyxray.lockfile import build_graph_from_lockfile
                from pyxray import output as out

                lock_path = Path(self.from_lock)
                if not lock_path.exists():
                    out.print_err(f"Lock file not found: {self.from_lock}")
                    self._graph, self._warnings = _empty_graph(), []
                    return self._graph
                declared_norms = {r.normalized_name for r in project.declared if r.name}
                self._graph, warnings = build_graph_from_lockfile(
                    lock_path, declared_norms
                )
                self._warnings.extend(warnings)
                if not self.quiet:
                    out.print_ok(f"Graph loaded from lock file: {lock_path.name}")
                return self._graph

            # ── Mode 2: auto-detect lock file ────────────────────────────
            if not self.use_pypi and not self.no_lock and not self.from_lock:
                from pathlib import Path
                from pyxray.lockfile import detect_lockfile, build_graph_from_lockfile

                root = Path(project.root)
                lock_path = detect_lockfile(str(root))
                if lock_path:
                    from pyxray import output as out

                    declared_norms = {
                        r.normalized_name for r in project.declared if r.name
                    }
                    self._graph, warnings = build_graph_from_lockfile(
                        lock_path, declared_norms
                    )
                    self._warnings.extend(warnings)
                    if not self.quiet:
                        out.print_ok(
                            f"Graph loaded from lock file: {lock_path.name} "
                            f"(pass --no-lock to use installed env instead)"
                        )
                    return self._graph

            # ── Mode 3: PyPI API (explicit --pypi flag) ──────────────────
            if self.use_pypi:
                from pyxray import output as out
                from pyxray.pypi import build_graph_from_pypi

                if not self.quiet:
                    out.print_warn(
                        f"Fetching dependency graph from PyPI "
                        f"(up to {self.max_packages} packages)…"
                    )
                self._graph, warnings = build_graph_from_pypi(
                    project.declared,
                    max_packages=self.max_packages,
                    verbose=not self.quiet,
                )
                self._warnings.extend(warnings)
                return self._graph

            # ── Mode 4: installed environment (default) ──────────────────
            from pyxray.graph import build_graph

            installed = self.get_installed()
            self._graph, warnings = build_graph(project, installed)
            self._warnings.extend(warnings)
        return self._graph

    def emit_warnings(self) -> None:
        if not self.quiet:
            from pyxray import output as out

            for w in self._warnings:
                out.print_warn(w)
            self._warnings.clear()


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _compute_health_grade(stats: dict) -> tuple[str, str]:
    """Return (grade, reason) based on graph health signals."""
    cycles = stats["cycle_count"]
    missing = stats["missing_packages"]
    depth = stats["maximum_depth"]

    if cycles > 3 or missing > 5:
        grade = "F"
        reason = f"{cycles} cycle(s), {missing} missing package(s)"
    elif cycles >= 1 or missing > 2:
        grade = "D"
        parts = []
        if cycles:
            parts.append(f"{cycles} cycle(s)")
        if missing > 2:
            parts.append(f"{missing} missing package(s)")
        reason = ", ".join(parts)
    elif missing > 0 or depth > 12:
        grade = "C"
        parts = []
        if missing:
            parts.append(f"{missing} missing package(s)")
        if depth > 12:
            parts.append(f"depth {depth} is very deep")
        reason = ", ".join(parts)
    elif depth > 8:
        grade = "B"
        reason = f"no cycles, 0 missing, depth {depth} is moderate"
    else:
        grade = "A"
        reason = "no cycles, 0 missing, depth OK"
    return grade, reason


def cmd_summary(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_stats

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    stats = compute_stats(graph)

    if ctx.json_output:
        data = {"project": project.name, **stats}
        if graph.missing:
            data["missing_packages"] = sorted(graph.missing)
        out.print_json(data)
        return 0

    out.header()
    out.section(f"Project: {project.name}")

    rows = [
        ("Direct dependencies", str(stats["direct_dependencies"])),
        ("Transitive dependencies", str(stats["transitive_dependencies"])),
        ("Total packages", str(stats["total_packages"])),
        ("", ""),
        ("Dependency edges", str(stats["dependency_edges"])),
        ("Leaf packages", str(stats["leaf_packages"])),
        ("Maximum depth", str(stats["maximum_depth"])),
        ("Average depth", str(stats["average_depth"])),
        ("Cycles detected", str(stats["cycle_count"])),
        ("Missing packages", str(stats["missing_packages"])),
    ]

    for label, value in rows:
        if not label:
            out.println()
            continue
        out.println(f"  {label:<30} {out.bold(value)}")

    if stats["largest_subtree_root"]:
        out.println()
        out.println(
            f"  {'Largest subtree':<30} "
            f"{out.cyan(stats['largest_subtree_root'])} → "
            f"{stats['largest_subtree_size']} packages"
        )

    if stats["most_depended_upon"]:
        out.println(
            f"  {'Most depended upon':<30} "
            f"{out.cyan(stats['most_depended_upon'])} → "
            f"{stats['most_depended_upon_count']} dependents"
        )

    # Health grade (R5)
    grade, reason = _compute_health_grade(stats)
    grade_color = (
        out.green if grade in ("A", "B")
        else out.yellow if grade in ("C", "D")
        else out.red
    )
    out.println(
        f"\n  {'Health':<30} {grade_color(out.bold(grade))}  "
        f"{out.dim(f'({reason})')}"
    )

    if graph.missing and not ctx.quiet:
        out.println()
        out.println(
            out.yellow("  Missing packages (declared/required but not installed):")
        )
        for m in sorted(graph.missing):
            out.println(f"    {out.red('✗')} {m}")

    out.println()
    return 0


def cmd_tree(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.output import render_tree
    from pyxray.analysis import compute_in_degrees

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    max_depth = args.depth
    sort_by = getattr(args, "sort_by", "alpha")

    def display(norm_name: str) -> str:
        pkg = graph.packages.get(norm_name)
        if pkg:
            ver = out.dim(f" {pkg.version}")
            if norm_name in graph.missing:
                return out.red(norm_name) + out.dim(" [not installed]")
            return out.cyan(norm_name) + ver
        return out.red(norm_name) + out.dim(" [?]")

    if ctx.json_output:

        def build_tree_dict(node: str, seen: set) -> dict:
            if node in seen:
                return {"name": node, "already_shown": True}
            seen.add(node)
            children = sorted(graph.forward.get(node, set()))
            pkg = graph.packages.get(node)
            return {
                "name": node,
                "version": pkg.version if pkg else "?",
                "dependencies": [build_tree_dict(c, seen) for c in children],
            }

        roots = sorted(graph.roots)
        result = {
            "project": project.name,
            "trees": [build_tree_dict(r, set()) for r in roots],
        }
        out.print_json(result)
        return 0

    out.section(f"Dependency Tree — {project.name}")

    if not graph.roots:
        out.println(out.dim("  (no dependencies declared)"))
        return 0

    # R6: build sort key — in-degree proxy for "heaviness"
    if sort_by == "in-degree":
        in_deg = compute_in_degrees(graph)
        def children_fn(n: str) -> list[str]:
            kids = list(graph.forward.get(n, set()))
            # Sort by in-degree descending (most-depended-upon first), then alpha
            return sorted(kids, key=lambda x: (-in_deg.get(x, 0), x))
    else:
        def children_fn(n: str) -> list[str]:
            return sorted(graph.forward.get(n, set()))

    # Render each root as its own subtree
    for root in sorted(graph.roots):
        lines = render_tree(
            root,
            children_fn=children_fn,
            display_fn=display,
            max_depth=max_depth,
        )
        for line in lines:
            out.println("  " + line)
        out.println()

    return 0


def _get_edge_constraint(graph, from_norm: str, to_norm: str) -> str:
    """Return the version specifier string that ties from_norm → to_norm.

    Walks raw_requires of the from package and extracts the specifier portion
    (e.g. '>=0.36.3') for the matching dependency entry. Returns '' if none found.
    """
    from pyxray.requirements import fast_extract_normalized_name
    pkg = graph.packages.get(from_norm)
    if not pkg:
        return ""
    for raw in pkg.raw_requires:
        dep_norm = fast_extract_normalized_name(raw)
        if dep_norm == to_norm:
            # Extract specifier: everything after the first name token
            # raw is like 'starlette>=0.36.3' or 'anyio>=4.0.0,<5'
            # Strip the package name (up to first =/</>/ ;)
            import re
            m = re.match(r"[A-Za-z0-9_\-.]+\s*([^;]*)", raw)
            if m:
                spec = m.group(1).strip().split(";")[0].strip()
                return spec
    return ""


def cmd_why(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_reverse_paths
    from pyxray.models import normalize_name

    package = args.package
    norm = normalize_name(package)

    graph = ctx.get_graph()
    ctx.emit_warnings()

    if norm not in graph.packages:
        out.print_err(
            f"'{package}' is not in the dependency graph. "
            f"Is it installed? Try: python -m pyxray summary"
        )
        return 1

    paths = find_reverse_paths(
        graph, target=norm, roots=graph.roots, max_paths=args.max_paths
    )

    pkg = graph.packages.get(norm)
    ver_str = f" ({pkg.version})" if pkg else ""

    if ctx.json_output:
        out.print_json(
            {
                "package": norm,
                "version": pkg.version if pkg else "?",
                "paths": paths,
            }
        )
        return 0

    out.section(f"Why is '{package}' installed?{ver_str}")

    if not paths:
        if norm in graph.roots:
            out.print_ok(f"'{package}' is a direct (root) project dependency.")
        else:
            out.println(out.dim(f"  No path found from project roots to '{package}'."))
            out.println(
                out.dim(
                    "  It may be installed but not reachable from declared dependencies."
                )
            )
        return 0

    for i, path in enumerate(paths, 1):
        out.println(out.bold(f"\n  Path {i}"))

        def pkg_display(n: str) -> str:
            return (
                (graph.packages[n].name if n in graph.packages else n)
                + " "
                + out.dim(
                    f"({graph.packages[n].version})"
                    if n in graph.packages and graph.packages[n].version != "?"
                    else ""
                )
            )

        # R7: edge_label_fn shows version constraint between hops
        def edge_label_fn(from_n: str, to_n: str) -> str:
            return _get_edge_constraint(graph, from_n, to_n)

        from pyxray.output import render_path

        for line in render_path(path, display_fn=pkg_display, edge_label_fn=edge_label_fn):
            out.println("    " + line)

    out.println()
    return 0


def cmd_impact(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import reachable_reverse, compute_depths
    from pyxray.models import normalize_name

    package = args.package
    norm = normalize_name(package)
    expand_all = getattr(args, "all", False)
    limit = getattr(args, "limit", None)

    graph = ctx.get_graph()
    ctx.emit_warnings()

    if norm not in graph.packages:
        out.print_err(f"'{package}' is not in the dependency graph.")
        return 1

    affected = reachable_reverse(graph, norm)

    pkg = graph.packages.get(norm)
    ver_str = f" ({pkg.version})" if pkg else ""

    if ctx.json_output:
        out.print_json(
            {
                "package": norm,
                "version": pkg.version if pkg else "?",
                "affected_count": len(affected),
                "affected": sorted(affected),
            }
        )
        return 0

    out.section(f"Impact of '{package}'{ver_str}")
    out.println(
        f"  If '{out.cyan(package)}' disappeared, "
        f"{out.bold(str(len(affected)))} package(s) would be affected:"
    )
    out.println()

    if not affected:
        out.println(out.dim("  (nothing depends on this package)"))
        return 0

    # R1: group by hop distance from the target package using reverse-graph depths
    # depth[dep] - depth[norm] gives approximate hop distance.
    depths = compute_depths(graph)
    norm_depth = depths.get(norm, 0)

    def _hop(dep: str) -> int:
        d = depths.get(dep, norm_depth)
        diff = d - norm_depth
        return max(diff, 1)  # at least 1 hop

    # Sort affected: hop ascending, then alpha
    sorted_affected = sorted(affected, key=lambda d: (_hop(d), d))

    # Apply --limit (R8)
    display_affected = sorted_affected
    truncated = 0
    if limit and limit > 0 and len(sorted_affected) > limit:
        display_affected = sorted_affected[:limit]
        truncated = len(sorted_affected) - limit

    # Render grouped by hop band
    current_band: Optional[int] = None
    band_labels = {1: "Direct dependents", 2: "2 hops", 3: "3+ hops (deep transitive)"}
    deep_threshold = 3

    rendered_in_deep = 0
    total_deep = sum(1 for d in sorted_affected if _hop(d) >= deep_threshold)

    for dep in display_affected:
        hop = _hop(dep)
        band = min(hop, deep_threshold)
        if band != current_band:
            current_band = band
            label = band_labels.get(band, f"{band}+ hops")
            count = sum(1 for d in sorted_affected if min(_hop(d), deep_threshold) == band)
            out.println(
                f"  {out.bold(label):<38} {out.dim(f'── {count} package(s)')}"
            )
        if band >= deep_threshold and not expand_all:
            rendered_in_deep += 1
            if rendered_in_deep == 1:
                # Show count summary instead of listing
                out.println(
                    f"    {out.dim(f'{total_deep} package(s)  (use --all to expand)')}"
                )
            continue  # skip individual lines unless --all

        pkg_d = graph.packages.get(dep)
        ver = out.dim(f" {pkg_d.version}") if pkg_d else ""
        marker = out.green("  ⊕ root ") if dep in graph.roots else "       "
        out.println(f"  {marker} {out.cyan(dep)}{ver}")

    if truncated:
        out.println(out.dim(f"  … and {truncated} more (remove --limit to see all)"))

    out.println()
    return 0


def cmd_duplicates(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_duplicate_versions

    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    dupes = find_duplicate_versions(installed, graph)

    if ctx.json_output:
        out.print_json({"duplicates": {k: v for k, v in sorted(dupes.items())}})
        return 0

    out.section("Duplicate Package Versions")

    if not dupes:
        out.print_ok("No duplicate versions detected.")
        return 0

    for norm_name in sorted(dupes):
        versions = dupes[norm_name]
        out.println(f"  {out.cyan(norm_name)}")
        for v in versions:
            out.println(f"    {out.dim('•')} {v}")
        out.println()

    return 0


def cmd_cycles(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_cycles
    from pyxray.output import render_path

    graph = ctx.get_graph()
    ctx.emit_warnings()

    cycles = find_cycles(graph)

    if ctx.json_output:
        out.print_json({"cycles": cycles, "cycle_count": len(cycles)})
        return 0

    out.section("Circular Dependencies")

    if not cycles:
        out.print_ok("No dependency cycles detected.")
        return 0

    out.println(out.yellow(f"  {len(cycles)} cycle(s) detected:"))
    out.println()

    for i, cycle in enumerate(cycles, 1):
        out.println(out.bold(f"  Cycle {i}"))
        for line in render_path(cycle):
            out.println("    " + line)
        out.println()

    return 0


def cmd_stats(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_stats, compute_in_degrees, compute_depths

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    stats = compute_stats(graph)
    depths = compute_depths(graph)
    in_deg = compute_in_degrees(graph)

    if ctx.json_output:
        out.print_json({"project": project.name, "stats": stats})
        return 0

    out.section(f"Graph Statistics — {project.name}")

    metrics = [
        ("Packages (total)", stats["total_packages"], "nodes"),
        ("Direct dependencies", stats["direct_dependencies"], "root nodes"),
        ("Transitive dependencies", stats["transitive_dependencies"], "non-root nodes"),
        ("Dependency edges", stats["dependency_edges"], "edges"),
        ("Leaf packages", stats["leaf_packages"], "no outgoing edges"),
        ("Missing packages", stats["missing_packages"], "not installed"),
        ("", "", ""),
        ("Maximum depth", stats["maximum_depth"], "hops from a root"),
        ("Average depth", stats["average_depth"], "BFS from roots"),
        ("Maximum fan-out", stats["maximum_fan_out"], "direct deps of one package"),
        ("Maximum fan-in", stats["maximum_fan_in"], "dependents of one package"),
        ("", "", ""),
        ("Cycle count", stats["cycle_count"], "strongly connected"),
        (
            "Largest subtree",
            f"{stats['largest_subtree_root']} ({stats['largest_subtree_size']} pkgs)",
            "from one root",
        ),
        (
            "Most depended upon",
            f"{stats['most_depended_upon']} ({stats['most_depended_upon_count']} deps)",
            "highest in-degree",
        ),
    ]

    for label, value, note in metrics:
        if not label:
            out.println()
            continue
        note_str = out.dim(f"  # {note}") if note else ""
        out.println(f"  {label:<32} {out.bold(str(value)):<20}{note_str}")

    out.println()
    return 0


def cmd_hotspots(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_in_degrees, reachable_from

    graph = ctx.get_graph()
    ctx.emit_warnings()

    in_deg = compute_in_degrees(graph)
    top_n = args.top
    limit = getattr(args, "limit", None)

    ranked = sorted(in_deg.items(), key=lambda x: -x[1])
    if top_n:
        ranked = ranked[:top_n]

    # Apply --limit (R8)
    truncated = 0
    if limit and limit > 0 and len(ranked) > limit:
        truncated = len(ranked) - limit
        ranked = ranked[:limit]

    if ctx.json_output:
        out.print_json(
            {"hotspots": [{"package": k, "dependents": v} for k, v in ranked]}
        )
        return 0

    out.section(f"Dependency Hotspots (top {top_n or len(ranked)})")
    out.println(
        out.dim("  Packages with the most reverse dependencies (in-degree).")
        + out.dim("  Risk = dependents × (1 + subtree_size)")
    )
    out.println()

    if not ranked:
        out.println(out.dim("  (empty graph)"))
        return 0

    max_count = ranked[0][1] if ranked else 1
    bar_width = 20

    for norm_name, count in ranked:
        if count == 0:
            break
        pkg = graph.packages.get(norm_name)
        ver = out.dim(f" {pkg.version}") if pkg else ""
        bar_len = int(bar_width * count / max(max_count, 1))
        bar = out.cyan("█" * bar_len) + out.dim("░" * (bar_width - bar_len))

        # R4: subtree size (number of packages this one transitively pulls in, excluding self)
        subtree_size = len(reachable_from(graph, norm_name)) - 1
        risk = count * (1 + subtree_size)

        out.println(f"  {out.cyan(norm_name)}{ver}")
        out.println(
            f"  {bar}  {out.bold(str(count))} dependents  "
            f"{out.dim(f'subtree: {subtree_size}  risk: {risk}')}"
        )
        out.println()

    if truncated:
        out.println(out.dim(f"  … and {truncated} more"))

    return 0


def cmd_longest_chain(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_cycles, find_longest_chain
    from pyxray.output import render_path

    graph = ctx.get_graph()
    ctx.emit_warnings()

    cycles = find_cycles(graph)
    chain = find_longest_chain(graph, cycles=cycles)

    if ctx.json_output:
        out.print_json(
            {
                "longest_chain": chain,
                "length": len(chain),
                "has_cycles": bool(cycles),
            }
        )
        return 0

    out.section("Longest Dependency Chain")

    if cycles:
        out.print_warn(
            f"Graph has {len(cycles)} cycle(s). Longest chain is approximate "
            "(cycle-safe DFS, not true longest path)."
        )
        out.println()

    if not chain:
        out.println(out.dim("  (empty graph)"))
        return 0

    out.println(f"  Chain length: {out.bold(str(len(chain)))} packages")
    out.println()

    def pkg_display(n: str) -> str:
        pkg = graph.packages.get(n)
        ver = out.dim(f" ({pkg.version})") if pkg else ""
        return out.cyan(n) + ver

    for line in render_path(chain, display_fn=pkg_display):
        out.println("  " + line)

    out.println()
    return 0


def cmd_imports(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.source import scan_with_usage, build_import_map, classify_imports

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    mapping_packages = {**installed, **graph.packages}
    import_map = build_import_map(mapping_packages)
    all_imports, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    third_party, stdlib_found, unknown = classify_imports(all_imports, import_map)

    if ctx.json_output:
        out.print_json(
            {
                "source_roots": project.source_roots,
                "total_imports": len(all_imports),
                "third_party": sorted(third_party),
                "stdlib": sorted(stdlib_found),
                "unknown": sorted(unknown),
            }
        )
        return 0

    out.section(f"Source Import Summary — {project.name}")
    out.println(f"  {'Source roots':<25} {', '.join(project.source_roots) or '(none)'}")
    out.println(f"  {'Total import statements':<25} {out.bold(str(len(all_imports)))}")
    out.println(f"  {'Third-party detected':<25} {out.bold(str(len(third_party)))}")
    out.println(f"  {'Standard library':<25} {out.bold(str(len(stdlib_found)))}")
    out.println(f"  {'Unclassified':<25} {out.bold(str(len(unknown)))}")
    out.println()

    if third_party:
        out.subsection("  Third-party imports detected:")
        for mod in sorted(third_party):
            out.println(f"    {out.cyan('•')} {mod}")

    if unknown and not args.no_unknown:
        out.println()
        out.subsection("  Unclassified imports (may be local, generated, or unknown):")
        for mod in sorted(unknown):
            out.println(f"    {out.dim('?')} {mod}")

    out.println()
    return 0


# R2: helper to classify a file path as test vs production
_TEST_SEGMENTS = frozenset({"tests", "test", "testing", "spec", "specs"})


def _is_test_file(path: str) -> bool:
    """Return True if *path* looks like a test file."""
    from pathlib import PurePosixPath
    p = PurePosixPath(path.replace("\\", "/"))
    name = p.stem.lower()
    if name.startswith("test_") or name.endswith("_test"):
        return True
    return any(part.lower() in _TEST_SEGMENTS for part in p.parts)


def cmd_audit(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.source import scan_with_usage, build_import_map, classify_imports
    from pyxray.models import normalize_name

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    limit = getattr(args, "limit", None)

    import_map = build_import_map({**installed, **graph.packages})
    all_imports, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    third_party_detected, stdlib_found, unknown = classify_imports(
        all_imports, import_map
    )

    declared_norms = {normalize_name(r.name) for r in project.declared if r.name}

    # Potentially unused: declared but no static import detected
    potentially_unused = declared_norms - third_party_detected

    # Potentially undeclared: detected third-party but not declared
    potentially_undeclared = third_party_detected - declared_norms

    if ctx.json_output:
        # Gather file locations for undeclared
        undeclared_locs: dict[str, list[str]] = {}
        for imp in all_imports:
            mapped = import_map.get(imp.module)
            if mapped and mapped in potentially_undeclared:
                undeclared_locs.setdefault(mapped, []).append(f"{imp.file}:{imp.line}")

        out.print_json(
            {
                "declared_count": len(declared_norms),
                "detected_third_party": len(third_party_detected),
                "potentially_unused": sorted(potentially_unused),
                "potentially_undeclared": {
                    k: v for k, v in sorted(undeclared_locs.items())
                },
            }
        )
        return 0

    out.section(f"Dependency Audit — {project.name}")
    out.println(f"  {'Declared dependencies':<35} {out.bold(str(len(declared_norms)))}")
    out.println(
        f"  {'Third-party imports detected':<35} {out.bold(str(len(third_party_detected)))}"
    )
    out.println(
        f"  {'Potentially unused declarations':<35} {out.bold(str(len(potentially_unused)))}"
    )
    out.println(
        f"  {'Potentially undeclared imports':<35} {out.bold(str(len(potentially_undeclared)))}"
    )

    if potentially_unused:
        out.println()
        out.println(
            out.yellow("  ⚠  Declared but no static import detected")
            + out.dim(
                "  (may use dynamic imports, entry points, or be a transitive dep)"
            )
        )
        for norm in sorted(potentially_unused):
            pkg = installed.get(norm)
            ver = out.dim(f" {pkg.version}") if pkg else ""
            out.println(f"    {out.yellow('•')} {norm}{ver}")

    if potentially_undeclared:
        out.println()
        out.println(
            out.red("  ✗  Imported but not in declared dependencies")
            + out.dim("  (may be a transitive dep being imported directly)")
        )
        # Build location index
        locs: dict[str, list[str]] = {}
        for imp in all_imports:
            mapped = import_map.get(imp.module)
            if mapped and mapped in potentially_undeclared:
                locs.setdefault(mapped, []).append(f"{imp.file}:{imp.line}")

        # R2: tag each undeclared import as [production] or [test only]
        undeclared_sorted = sorted(potentially_undeclared)
        # Apply --limit (R8)
        truncated = 0
        if limit and limit > 0 and len(undeclared_sorted) > limit:
            truncated = len(undeclared_sorted) - limit
            undeclared_sorted = undeclared_sorted[:limit]

        for norm in undeclared_sorted:
            pkg_locs = locs.get(norm, [])
            all_test = all(_is_test_file(loc.split(":")[0]) for loc in pkg_locs) if pkg_locs else False
            tag = out.dim(" [test only]") if all_test else out.yellow(" [production]")
            out.println(f"    {out.red('•')} {norm}{tag}")
            for loc in pkg_locs[:5]:  # cap at 5 locations per package
                out.println(f"        {out.dim(loc)}")

        if truncated:
            out.println(out.dim(f"  … and {truncated} more (remove --limit to see all)"))

    if not potentially_unused and not potentially_undeclared:
        out.println()
        out.print_ok("Declared dependencies match detected imports.")

    out.println()
    out.println(
        out.dim(
            "  Note: Static analysis cannot detect dynamic imports "
            "(importlib.import_module, __import__, etc.)"
        )
    )
    out.println()
    return 0


def cmd_prune(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_prune_candidates
    from pyxray.source import build_import_map, scan_with_usage
    from pyxray.hints import get_hint  # R3

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    import_map = build_import_map({**installed, **graph.packages})
    _, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    from pyxray.models import normalize_name

    project_norm = normalize_name(project.name)

    candidates = [
        c
        for c in compute_prune_candidates(
            graph,
            usage_map,
            thin_threshold=args.thin,
            narrow_threshold=args.narrow,
            shallow_threshold=args.shallow,
        )
        if c.norm_name != project_norm
    ]

    if ctx.json_output:
        out.print_json(
            {
                "candidates": [
                    {
                        "package": c.norm_name,
                        "version": c.version,
                        "label": c.label,
                        "confidence": c.confidence,
                        "reason": c.reason,
                        "transitive_count": c.transitive_count,
                        "file_count": c.file_count,
                        "symbol_count": c.symbol_count,
                        "symbols_used": c.symbols_used,
                        "files_using": c.files_using,
                    }
                    for c in candidates
                ]
            }
        )
        return 0

    out.section(f"Prune Candidates — {project.name}")

    if not candidates:
        out.println("  No declared dependencies to analyze.")
        return 0

    for c in candidates:
        if c.label == "REIMPLEMENT":
            color = out.cyan
            icon = "✎"
        elif c.label == "REMOVE":
            color = out.red
            icon = "✗"
        elif c.label == "UNDECLARE":
            color = out.yellow
            icon = "⚠"
        elif c.label == "COVERED":
            color = out.magenta
            icon = "↎"
        else:
            color = out.dim
            icon = "✓"

        ver = out.dim(f" ({c.version})")
        out.println(
            f"  {color(icon)} {out.bold(c.norm_name)}{ver}  —  {color(c.label)}"
        )
        out.println(f"      Confidence: {c.confidence}")

        # Word wrap the reason
        import textwrap

        for line in textwrap.wrap(c.reason, width=70):
            out.println(f"      {line}")

        # R3: stdlib replacement hint for REIMPLEMENT candidates
        if c.label == "REIMPLEMENT":
            hint = get_hint(c.norm_name)
            out.println(f"      {out.green('Suggestion:')} {hint}")

        out.println()

    return 0


# ---------------------------------------------------------------------------
# F1 — env
# ---------------------------------------------------------------------------


def cmd_env(ctx: Context, args: argparse.Namespace) -> int:
    """Print Python environment and project information."""
    import sysconfig
    import platform
    from pyxray import output as out
    from pyxray.lockfile import detect_lockfile

    proj_root = ctx.project_root or "."
    lock_path = detect_lockfile(proj_root)
    lock_name = lock_path.name if lock_path else "none"

    venv = (
        __import__("os").environ.get("VIRTUAL_ENV")
        or __import__("os").environ.get("CONDA_PREFIX")
        or "(none)"
    )
    site_packages = sysconfig.get_path("purelib") or "?"
    py_impl = platform.python_implementation()
    py_ver = sys.version.split()[0]
    plat = sys.platform
    plat_detail = platform.platform()

    if ctx.json_output:
        out.print_json(
            {
                "python_version": py_ver,
                "implementation": py_impl,
                "executable": sys.executable,
                "virtual_env": venv,
                "site_packages": site_packages,
                "platform": plat,
                "platform_detail": plat_detail,
                "lock_file": lock_name,
                "project_root": str(__import__("pathlib").Path(proj_root).resolve()),
            }
        )
        return 0

    out.section("Python Environment")
    rows = [
        ("Python version", f"{py_ver}  ({py_impl})"),
        ("Executable", sys.executable),
        ("Virtual env", venv),
        ("Site-packages", site_packages),
        ("Platform", f"{plat}  ({plat_detail})"),
        ("Lock file", lock_name),
        ("Project root", str(__import__("pathlib").Path(proj_root).resolve())),
    ]
    for label, value in rows:
        out.println(f"  {label:<22} {out.bold(value)}")
    out.println()
    return 0


# ---------------------------------------------------------------------------
# F2 — check
# ---------------------------------------------------------------------------


def cmd_check(ctx: Context, args: argparse.Namespace) -> int:
    """CI pass/fail gate: fail on cycles, missing packages, or excessive depth."""
    from pyxray import output as out
    from pyxray.analysis import compute_stats

    graph = ctx.get_graph()
    ctx.emit_warnings()
    stats = compute_stats(graph)

    cycles = stats["cycle_count"]
    missing = stats["missing_packages"]
    depth = stats["maximum_depth"]
    max_depth = getattr(args, "max_depth", 10)
    allow_cycles = getattr(args, "allow_cycles", False)
    allow_missing = getattr(args, "allow_missing", False)

    project = ctx.get_project()

    checks: list[tuple[str, bool, str]] = []  # (name, passed, detail)
    if not allow_cycles:
        passed = cycles == 0
        checks.append(("cycles", passed, f"{cycles} cycle(s) detected" if not passed else "0 cycles"))
    if not allow_missing:
        passed = missing == 0
        checks.append(("missing", passed, f"{missing} missing package(s)" if not passed else "0 missing packages"))

    depth_passed = depth <= max_depth
    checks.append(("depth", depth_passed, f"{depth} (limit: {max_depth})"))

    all_passed = all(p for _, p, _ in checks)

    if ctx.json_output:
        out.print_json(
            {
                "project": project.name,
                "passed": all_passed,
                "checks": [
                    {"name": n, "passed": p, "detail": d} for n, p, d in checks
                ],
            }
        )
        return 0 if all_passed else 1

    out.section(f"Dependency Health Check \u2014 {project.name}")
    for name, passed, detail in checks:
        icon = out.green("\u2713") if passed else out.red("\u2717")
        out.println(f"  {icon}  {name:<14} {detail}")

    out.println()
    if all_passed:
        out.print_ok("All checks passed.")
        result_str = out.green(out.bold("PASS"))
    else:
        failed = sum(1 for _, p, _ in checks if not p)
        result_str = out.red(out.bold("FAIL"))
        out.println(f"  Result: {result_str}  ({failed} check(s) failed)")

    out.println()
    return 0 if all_passed else 1


# ---------------------------------------------------------------------------
# F3 — license
# ---------------------------------------------------------------------------

_LICENSE_ALIASES: dict[str, str] = {
    "mit license": "MIT",
    "the mit license": "MIT",
    "mit": "MIT",
    "apache software license": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd license": "BSD",
    "bsd 3-clause license": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd 2-clause license": "BSD-2-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "simplified bsd": "BSD-2-Clause",
    "gpl": "GPL",
    "gplv2": "GPL-2.0",
    "gplv3": "GPL-3.0",
    "gnu general public license v2 (gplv2)": "GPL-2.0",
    "gnu general public license v3 (gplv3)": "GPL-3.0",
    "lgpl": "LGPL",
    "lgplv2": "LGPL-2.0",
    "lgplv3": "LGPL-3.0",
    "mpl-2.0": "MPL-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "isc license (iscl)": "ISC",
    "isc": "ISC",
    "python software foundation license": "PSF",
    "psf": "PSF",
    "unlicense": "Unlicense",
    "the unlicense (unlicense)": "Unlicense",
    "public domain": "Public Domain",
    "cc0 1.0 universal (cc0 1.0) public domain dedication": "CC0-1.0",
}


def _normalise_license(raw: str) -> str:
    """Normalise a freeform license string to a canonical SPDX-ish identifier."""
    key = raw.strip().lower()
    return _LICENSE_ALIASES.get(key, raw.strip() or "Unknown")


def _get_package_license(norm_name: str) -> str:
    """Return the license string for an installed package, or 'Unknown'."""
    try:
        import importlib.metadata as im
        meta = im.metadata(norm_name)
        # Python 3.12+ has License-Expression (SPDX); prefer it
        lic = meta.get("License-Expression") or meta.get("License") or ""
        if lic:
            return _normalise_license(lic)
    except Exception:
        pass
    return "Unknown"


def cmd_license(ctx: Context, args: argparse.Namespace) -> int:
    """Display a license inventory across all packages in the graph."""
    from pyxray import output as out

    graph = ctx.get_graph()
    ctx.emit_warnings()

    show_packages = getattr(args, "show_packages", False)

    # Gather license for each package
    license_map: dict[str, list[str]] = {}  # {license_id → [norm_names]}
    for norm_name in sorted(graph.packages):
        lic = _get_package_license(norm_name)
        license_map.setdefault(lic, []).append(norm_name)

    total = sum(len(v) for v in license_map.values())
    sorted_licenses = sorted(license_map.items(), key=lambda x: -len(x[1]))

    if ctx.json_output:
        out.print_json(
            {
                "total_packages": total,
                "licenses": {k: v for k, v in sorted_licenses},
            }
        )
        return 0

    project = ctx.get_project()
    out.section(f"License Inventory \u2014 {project.name}")
    out.println(f"  {total} packages analysed\n")

    bar_width = 18
    max_count = sorted_licenses[0][1].__len__() if sorted_licenses else 1

    for lic_id, pkgs in sorted_licenses:
        count = len(pkgs)
        bar_len = int(bar_width * count / max(max_count, 1))
        bar = out.cyan("\u2588" * bar_len) + out.dim("\u2591" * (bar_width - bar_len))
        flag = "  " + out.red("\u2190 review") if lic_id == "Unknown" else ""
        out.println(f"  {lic_id:<22} {out.bold(str(count)):>4} packages  {bar}{flag}")
        if show_packages:
            for pkg in pkgs:
                ver = graph.packages[pkg].version if pkg in graph.packages else "?"
                out.println(f"      {out.dim(f'{pkg} {ver}')}")

    out.println()
    return 0


# ---------------------------------------------------------------------------
# F4 — export (mermaid / dot)
# ---------------------------------------------------------------------------


def cmd_export(ctx: Context, args: argparse.Namespace) -> int:
    """Export the dependency graph in Mermaid or Graphviz DOT format (stdout)."""
    from pyxray import output as out

    graph = ctx.get_graph()
    ctx.emit_warnings()

    fmt = getattr(args, "format", "mermaid")
    max_depth = getattr(args, "depth", None)

    # BFS to collect edges up to max_depth
    from collections import deque

    edges: list[tuple[str, str]] = []
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()

    for root in sorted(graph.roots):
        if root not in visited:
            visited.add(root)
            queue.append((root, 0))

    while queue:
        node, depth = queue.popleft()
        for child in sorted(graph.forward.get(node, set())):
            edges.append((node, child))
            if child not in visited:
                visited.add(child)
                if max_depth is None or depth + 1 < max_depth:
                    queue.append((child, depth + 1))

    def _safe_id(name: str) -> str:
        return name.replace("-", "_").replace(".", "_")

    if fmt == "mermaid":
        lines = ["graph TD"]
        for src, dst in edges:
            lines.append(f'    {_safe_id(src)} --> {_safe_id(dst)}')
        print("\n".join(lines))
    else:  # dot
        lines = ['digraph dependencies {', '    rankdir=TB;']
        for src, dst in edges:
            lines.append(f'    "{src}" -> "{dst}";')
        lines.append("}")
        print("\n".join(lines))

    return 0


# ---------------------------------------------------------------------------
# F5 — compare
# ---------------------------------------------------------------------------


def _semver_tuple(ver: str) -> tuple[int, ...]:
    """Parse a version string into a comparable int tuple. Best-effort."""
    parts = []
    for seg in ver.split("."):
        try:
            parts.append(int("".join(c for c in seg if c.isdigit()) or "0"))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _version_delta(old: str, new: str) -> str:
    """Classify the size of a version change: major / minor / patch / unknown."""
    ov = _semver_tuple(old)
    nv = _semver_tuple(new)
    if len(ov) >= 1 and len(nv) >= 1:
        if nv[0] != ov[0]:
            return "major"
        if len(ov) >= 2 and len(nv) >= 2 and nv[1] != ov[1]:
            return "minor"
    return "patch"


def cmd_compare(ctx: Context, args: argparse.Namespace) -> int:
    """Diff two lock files and report added / removed / version-changed packages."""
    from pyxray import output as out
    from pyxray.lockfile import load_lockfile
    from pathlib import Path

    old_path = Path(args.old)
    only_changed = getattr(args, "only_changed", False)

    new_arg = getattr(args, "new", None)
    if new_arg:
        new_path = Path(new_arg)
    else:
        from pyxray.lockfile import detect_lockfile
        detected = detect_lockfile(ctx.project_root or ".")
        if not detected:
            out.print_err("No lock file found. Use --new FILE to specify one.")
            return 1
        new_path = detected

    if not old_path.exists():
        out.print_err(f"Old lock file not found: {old_path}")
        return 1
    if not new_path.exists():
        out.print_err(f"New lock file not found: {new_path}")
        return 1

    old_pkgs, _ = load_lockfile(old_path)
    new_pkgs, _ = load_lockfile(new_path)

    all_names = sorted(set(old_pkgs) | set(new_pkgs))

    added: list[tuple[str, str]] = []
    removed: list[tuple[str, str]] = []
    upgraded: list[tuple[str, str, str]] = []
    downgraded: list[tuple[str, str, str]] = []

    for name in all_names:
        in_old = name in old_pkgs
        in_new = name in new_pkgs
        if in_new and not in_old:
            added.append((name, new_pkgs[name].version))
        elif in_old and not in_new:
            removed.append((name, old_pkgs[name].version))
        elif in_old and in_new:
            ov, nv = old_pkgs[name].version, new_pkgs[name].version
            if ov != nv:
                ot = _semver_tuple(ov)
                nt = _semver_tuple(nv)
                if nt >= ot:
                    upgraded.append((name, ov, nv))
                else:
                    downgraded.append((name, ov, nv))

    if ctx.json_output:
        out.print_json(
            {
                "old": str(old_path),
                "new": str(new_path),
                "added": [{"package": n, "version": v} for n, v in added],
                "removed": [{"package": n, "version": v} for n, v in removed],
                "upgraded": [{"package": n, "old": o, "new": nw} for n, o, nw in upgraded],
                "downgraded": [{"package": n, "old": o, "new": nw} for n, o, nw in downgraded],
            }
        )
        return 0

    out.section(f"Dependency Diff \u2014 {old_path.name}  \u2192  {new_path.name}")

    if not added and not removed and not upgraded and not downgraded:
        out.print_ok("No differences found — lock files are identical.")
        out.println()
        return 0

    for name, ver in added:
        out.println(f"  {out.green('+ added    ')} {out.bold(name)} {out.dim(ver)}")
    for name, ver in removed:
        out.println(f"  {out.red('- removed  ')} {out.bold(name)} {out.dim(ver)}")
    for name, ov, nv in upgraded:
        delta = _version_delta(ov, nv)
        prefix = out.cyan('↑ upgraded ')
        out.println(
            f"  {prefix} {out.bold(name)}  "
            f"{out.dim(ov)} \u2192 {out.green(nv)}  {out.dim(f'({delta})')}"
        )
    for name, ov, nv in downgraded:
        prefix = out.yellow('↓ downgrade')
        out.println(
            f"  {prefix} {out.bold(name)}  "
            f"{out.dim(ov)} \u2192 {out.yellow(nv)}"
        )

    total = len(added) + len(removed) + len(upgraded) + len(downgraded)
    out.println(
        f"\n  Summary: {out.green(str(len(added)))} added, "
        f"{out.red(str(len(removed)))} removed, "
        f"{out.cyan(str(len(upgraded) + len(downgraded)))} version change(s)  "
        f"{out.dim(f'({total} total)')}"
    )
    out.println()
    return 0


# ---------------------------------------------------------------------------
# F6 — unused-extras
# ---------------------------------------------------------------------------


def cmd_unused_extras(ctx: Context, args: argparse.Namespace) -> int:
    """Find declared extras whose sub-dependencies are never imported in source."""
    from pyxray import output as out
    from pyxray.source import build_import_map, scan_with_usage
    from pyxray.requirements import evaluate_marker

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    import_map = build_import_map({**installed, **graph.packages})
    _, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    # Find declared requirements with extras
    extras_reqs = [r for r in project.declared if r.extras]

    results: list[dict] = []

    for req in extras_reqs:
        pkg = installed.get(req.normalized_name) or graph.packages.get(req.normalized_name)
        if not pkg:
            continue

        for extra in sorted(req.extras):
            # Find sub-deps activated by this extra
            extra_sub_deps: list[str] = []
            for dep_req in pkg.requires:
                if not dep_req.marker:
                    continue
                marker = dep_req.marker
                # Check if marker references this extra
                if f'extra == "{extra}"' in marker or f"extra == '{extra}'" in marker:
                    if dep_req.normalized_name:
                        extra_sub_deps.append(dep_req.normalized_name)

            if not extra_sub_deps:
                continue

            # Check which sub-deps are actually used in source
            used = [d for d in extra_sub_deps if d in usage_map and usage_map[d]]
            unused = [d for d in extra_sub_deps if d not in used]

            results.append(
                {
                    "package": req.normalized_name,
                    "extra": extra,
                    "sub_deps": extra_sub_deps,
                    "used": used,
                    "unused": unused,
                    "wasteful": len(unused) > 0 and len(used) == 0,
                }
            )

    if ctx.json_output:
        out.print_json({"project": project.name, "extras": results})
        return 0

    out.section(f"Unused Extras \u2014 {project.name}")

    if not extras_reqs:
        out.println(out.dim("  No dependencies with extras declared."))
        out.println()
        return 0

    if not results:
        out.println(out.dim("  No extra sub-dependency information available."))
        out.println(out.dim("  (Extras analysis requires installed packages with markers)"))
        out.println()
        return 0

    wasteful = [r for r in results if r["wasteful"]]
    clean = [r for r in results if not r["wasteful"]]

    for r in wasteful:
        warning_icon = out.red('\u26a0')
        out.println(
            f"  {warning_icon} {out.bold(r['package'])}[{r['extra']}]  "
            f"{out.dim('— all sub-deps unused in source')}"
        )
        out.println(f"      Extra pulls in:  {', '.join(r['sub_deps'])}")
        out.println(f"      Source uses:     {out.red('none')}")
        out.println(f"      {out.yellow('Consider removing:')} {r['package']}[{r['extra']}]")
        out.println()

    for r in clean:
        used_count = len(r["used"])
        sub_deps_count = len(r["sub_deps"])
        check_icon = out.green('\u2713')
        out.println(
            f"  {check_icon} {out.bold(r['package'])}[{r['extra']}]  "
            f"{out.dim(f'{used_count}/{sub_deps_count} sub-dep(s) used')}"
        )

    if not wasteful:
        out.println()
        out.print_ok("No wasteful extras detected.")

    out.println()
    return 0


# ---------------------------------------------------------------------------
# F7 — outdated
# ---------------------------------------------------------------------------


def _compare_versions(installed_ver: str, latest_ver: str) -> tuple[str, bool]:
    """
    Compare two version strings.
    Returns (delta_type, is_outdated).
    delta_type is 'major', 'minor', or 'patch'.
    """
    iv = _semver_tuple(installed_ver)
    lv = _semver_tuple(latest_ver)
    if lv <= iv:
        return "patch", False
    delta = _version_delta(installed_ver, latest_ver)
    return delta, True


_DELTA_RANK = {"patch": 0, "minor": 1, "major": 2}


def cmd_outdated(ctx: Context, args: argparse.Namespace) -> int:
    """Compare installed/locked versions against PyPI latest."""
    from pyxray import output as out
    from pyxray.pypi import fetch_latest_version

    graph = ctx.get_graph()
    ctx.emit_warnings()
    project = ctx.get_project()

    top_n = getattr(args, "top", None)
    min_delta = getattr(args, "min_delta", "patch")
    min_rank = _DELTA_RANK.get(min_delta, 0)

    packages = [
        (norm, pkg)
        for norm, pkg in graph.packages.items()
        if pkg.version and pkg.version != "?"
    ]

    if not ctx.json_output:
        out.section(f"Outdated Packages \u2014 {project.name}")
        out.println(
            f"  {out.dim(f'Checking {len(packages)} packages against PyPI...')}\n"
        )

    outdated: list[tuple[str, str, str, str]] = []  # (norm, installed, latest, delta)

    for i, (norm, pkg) in enumerate(packages):
        latest = fetch_latest_version(norm)
        if not latest:
            continue
        delta, is_out = _compare_versions(pkg.version, latest)
        if is_out and _DELTA_RANK.get(delta, 0) >= min_rank:
            outdated.append((norm, pkg.version, latest, delta))
        # Progress dot every 20 packages
        if not ctx.json_output and not ctx.quiet and (i + 1) % 20 == 0:
            import sys as _sys
            print(f"  ... {i+1}/{len(packages)} checked", file=_sys.stderr)

    # Sort by delta severity desc, then alpha
    outdated.sort(key=lambda x: (-_DELTA_RANK.get(x[3], 0), x[0]))

    if top_n:
        outdated = outdated[:top_n]

    if ctx.json_output:
        out.print_json(
            {
                "project": project.name,
                "total_checked": len(packages),
                "outdated_count": len(outdated),
                "outdated": [
                    {"package": n, "installed": iv, "latest": lv, "delta": d}
                    for n, iv, lv, d in outdated
                ],
            }
        )
        return 0

    if not outdated:
        out.print_ok(f"All {len(packages)} packages are up to date.")
        out.println()
        return 0

    # Header
    out.println(
        f"  {'Package':<30} {'Installed':<14} {'Latest':<14} {'Delta'}"
    )
    out.println(f"  {'-'*30} {'-'*14} {'-'*14} {'-'*10}")

    delta_color = {"major": out.red, "minor": out.yellow, "patch": out.dim}
    arrow = "\u2191"

    for norm, iv, lv, delta in outdated:
        color = delta_color.get(delta, out.dim)
        out.println(
            f"  {out.cyan(norm):<30} {out.dim(iv):<14} {color(lv):<14} "
            f"{color(f'{arrow} {delta}')}"
        )

    out.println(
        f"\n  {out.bold(str(len(outdated)))} outdated of "
        f"{len(packages)} checked."
    )
    out.println()
    return 0


# ---------------------------------------------------------------------------
# F8 — security
# ---------------------------------------------------------------------------


def cmd_security(ctx: Context, args: argparse.Namespace) -> int:
    """Check for known CVEs via OSV.dev batch API."""
    from pyxray import output as out
    from pyxray.osv import query_osv_batch, format_severity, extract_fixed_in

    graph = ctx.get_graph()
    ctx.emit_warnings()
    project = ctx.get_project()

    min_severity = getattr(args, "min_severity", "low")
    _SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    min_rank = _SEV_RANK.get(min_severity, 0)

    packages = [
        (norm, pkg.version)
        for norm, pkg in graph.packages.items()
        if pkg.version and pkg.version != "?"
    ]

    if not ctx.json_output:
        out.section(f"Security Audit \u2014 {project.name}")
        out.println(
            out.dim(
                f"  Checking {len(packages)} packages against OSV.dev...\n"
            )
        )

    import json
    import os

    snapshot_file = os.path.join(ctx.project_root, "pyxray-security-snapshot.json")
    is_offline = getattr(args, "offline", False)
    update_snapshot = getattr(args, "update_snapshot", False)

    vuln_results = {}
    
    if is_offline:
        if not os.path.exists(snapshot_file):
            out.print_err(f"Offline mode requested, but {snapshot_file} not found.")
            return 1
        with open(snapshot_file, "r", encoding="utf-8") as f:
            vuln_results = json.load(f)
        if not ctx.json_output:
            out.println(out.dim(f"  Loaded {len(vuln_results)} records from offline snapshot.\n"))
    else:
        vuln_results = query_osv_batch(packages)
        if update_snapshot:
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(vuln_results, f, indent=2)
            if not ctx.json_output:
                out.println(out.dim(f"  Snapshot saved to {snapshot_file}\n"))

    # Filter by min severity
    findings: list[dict] = []
    for norm, version in packages:
        vulns = vuln_results.get(norm, [])
        for v in vulns:
            sev = format_severity(v).lower()
            if _SEV_RANK.get(sev, 0) >= min_rank:
                fixed_in = extract_fixed_in(v, norm)
                findings.append(
                    {
                        "package": norm,
                        "version": version,
                        "id": v.get("id", "?"),
                        "summary": v.get("summary", "No summary"),
                        "severity": format_severity(v),
                        "fixed_in": fixed_in,
                        "url": f"https://osv.dev/vulnerability/{v.get('id', '')}",
                    }
                )

    if ctx.json_output:
        out.print_json(
            {
                "project": project.name,
                "total_checked": len(packages),
                "vulnerabilities_found": len(findings),
                "findings": findings,
            }
        )
        return 1 if findings else 0

    if not findings:
        out.print_ok(f"{len(packages)} packages checked — no known vulnerabilities found.")
        out.println()
        return 0

    sev_color = {
        "CRITICAL": out.red,
        "HIGH": out.red,
        "MEDIUM": out.yellow,
        "LOW": out.dim,
    }

    out.println(out.red(out.bold(f"  \u26a0  {len(findings)} VULNERABILITY/IES FOUND:\n")))

    seen_pkgs: set[str] = set()
    for f in findings:
        pkg_key = f["package"]
        if pkg_key not in seen_pkgs:
            seen_pkgs.add(pkg_key)
            out.println(f"  {out.bold(f['package'])} {out.dim(f['version'])}")

        sev = f["severity"].upper()
        color = sev_color.get(sev, out.dim)
        out.println(
            f"    {color(f['id'])}  {color(sev):<10}  {f['summary']}"
        )
        if f["fixed_in"]:
            out.println(f"    {out.dim('Fixed in:')}  {out.green(f['fixed_in'])}")
        out.println(f"    {out.dim(f['url'])}")
        out.println()

    out.println(
        out.dim(f"  \u2714 {len(packages) - len(seen_pkgs)} packages: no known vulnerabilities.")
    )
    out.println()
    return 1  # non-zero exit when vulns found


# ---------------------------------------------------------------------------
# Argument parser construction
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyxray",
        description=(
            "PyXRay — Python Dependency Investigation Tool\n"
            "Zero third-party runtime dependencies. All analysis is local and deterministic."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pyxray summary\n"
            "  python -m pyxray tree --depth 3\n"
            "  python -m pyxray why requests\n"
            "  python -m pyxray impact typing-extensions\n"
            "  python -m pyxray audit --json\n"
        ),
    )

    parser.add_argument(
        "--root",
        "-r",
        metavar="DIR",
        default=None,
        help="Project root directory (default: current working directory)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI color output (also respects NO_COLOR env var)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results as JSON",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress warnings",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version="PyXRay 0.1.0",
    )
    # R8: global --limit flag for list-style commands
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Limit list output to N items (0 = no limit). Applies to impact, hotspots, audit.",
    )

    # ── Graph source flags ────────────────────────────────────────────────
    source_group = parser.add_argument_group(
        "graph source",
        "Control where PyXRay reads dependency metadata from.\n"
        "Default: installed environment (importlib.metadata).\n"
        "Lock file (uv.lock / poetry.lock) is auto-detected if present.",
    )
    source_group.add_argument(
        "--from-lock",
        metavar="FILE",
        default=None,
        help=(
            "Explicit path to a lock file (uv.lock or poetry.lock). "
            "Analyses the graph without any packages needing to be installed."
        ),
    )
    source_group.add_argument(
        "--no-lock",
        action="store_true",
        default=False,
        help="Ignore any detected lock file; use the installed environment instead.",
    )
    source_group.add_argument(
        "--pypi",
        action="store_true",
        default=False,
        help=(
            "Fetch dependency metadata from PyPI JSON API (requires internet). "
            "Allows analysis of projects whose packages are not installed. "
            "Uses urllib.request (stdlib only)."
        ),
    )
    source_group.add_argument(
        "--max-packages",
        type=int,
        default=300,
        metavar="N",
        help="Maximum packages to fetch in --pypi mode (default: 300).",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # summary
    p_sum = sub.add_parser("summary", help="Project dependency summary")
    p_sum.set_defaults(func=cmd_summary)

    # tree
    p_tree = sub.add_parser("tree", help="Render dependency tree")
    p_tree.add_argument(
        "--depth",
        "-d",
        type=int,
        default=None,
        help="Maximum tree depth to render",
    )
    p_tree.add_argument(
        "--sort-by",
        dest="sort_by",
        choices=["alpha", "in-degree"],
        default="alpha",
        help="Sort children alphabetically (default) or by in-degree descending (most-depended-upon first)",
    )
    p_tree.set_defaults(func=cmd_tree)

    # why
    p_why = sub.add_parser("why", help="Explain why a package is installed")
    p_why.add_argument("package", help="Package name to explain")
    p_why.add_argument(
        "--max-paths",
        type=int,
        default=5,
        help="Maximum number of paths to show (default: 5)",
    )
    p_why.set_defaults(func=cmd_why)

    # impact
    p_impact = sub.add_parser(
        "impact", help="Show packages affected if a package disappeared"
    )
    p_impact.add_argument("package", help="Package name to analyse")
    p_impact.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Expand deep transitive dependents (3+ hops) in full",
    )
    p_impact.set_defaults(func=cmd_impact)

    # duplicates
    p_dup = sub.add_parser(
        "duplicates", help="Detect packages installed with multiple versions"
    )
    p_dup.set_defaults(func=cmd_duplicates)

    # cycles
    p_cyc = sub.add_parser("cycles", help="Detect circular dependencies")
    p_cyc.set_defaults(func=cmd_cycles)

    # stats
    p_stats = sub.add_parser("stats", help="Detailed graph statistics")
    p_stats.set_defaults(func=cmd_stats)

    # hotspots
    p_hot = sub.add_parser("hotspots", help="Packages with the most dependents")
    p_hot.add_argument(
        "--top",
        "-n",
        type=int,
        default=20,
        help="Number of results to show (default: 20)",
    )
    p_hot.set_defaults(func=cmd_hotspots)

    # longest-chain
    p_lc = sub.add_parser("longest-chain", help="Find the longest dependency path")
    p_lc.set_defaults(func=cmd_longest_chain)

    # imports
    p_imp = sub.add_parser("imports", help="Scan source code for import statements")
    p_imp.add_argument(
        "--no-unknown",
        action="store_true",
        default=False,
        help="Suppress unclassified import listing",
    )
    p_imp.set_defaults(func=cmd_imports)

    # audit
    p_audit = sub.add_parser(
        "audit",
        help="Compare declared dependencies with detected source imports",
    )
    p_audit.set_defaults(func=cmd_audit)

    # prune
    p_prune = sub.add_parser(
        "prune",
        help="Find packages that can be removed or reimplemented",
    )
    p_prune.add_argument(
        "--thin",
        type=int,
        default=3,
        help="Max transitive deps to consider 'thin' (default: 3)",
    )
    p_prune.add_argument(
        "--narrow",
        type=int,
        default=3,
        help="Max source files importing to consider 'narrow' (default: 3)",
    )
    p_prune.add_argument(
        "--shallow",
        type=int,
        default=5,
        help="Max symbols imported to consider 'shallow' (default: 5)",
    )
    p_prune.set_defaults(func=cmd_prune)

    # env
    p_env = sub.add_parser("env", help="Show Python environment and project info")
    p_env.set_defaults(func=cmd_env)

    # check
    p_check = sub.add_parser(
        "check",
        help="CI pass/fail gate: fail if cycles, missing, or depth exceeded",
    )
    p_check.add_argument(
        "--max-depth",
        type=int,
        default=10,
        metavar="N",
        help="Fail if dependency chain exceeds N hops (default: 10)",
    )
    p_check.add_argument(
        "--allow-cycles",
        action="store_true",
        default=False,
        help="Do not fail on detected cycles",
    )
    p_check.add_argument(
        "--allow-missing",
        action="store_true",
        default=False,
        help="Do not fail on missing packages",
    )
    p_check.set_defaults(func=cmd_check)

    # license
    p_lic = sub.add_parser("license", help="Show license inventory across all packages")
    p_lic.add_argument(
        "--show-packages",
        action="store_true",
        default=False,
        help="List every package under each license group",
    )
    p_lic.set_defaults(func=cmd_license)

    # export
    p_exp = sub.add_parser(
        "export", help="Export dependency graph as Mermaid or Graphviz DOT"
    )
    p_exp.add_argument(
        "--format",
        "-f",
        choices=["mermaid", "dot"],
        default="mermaid",
        help="Output format: mermaid (default) or dot",
    )
    p_exp.add_argument(
        "--depth",
        "-d",
        type=int,
        default=None,
        help="Maximum depth to export (default: full graph)",
    )
    p_exp.set_defaults(func=cmd_export)

    # compare
    p_cmp = sub.add_parser(
        "compare",
        help="Diff two lock files and show added/removed/changed packages",
    )
    p_cmp.add_argument("--old", required=True, metavar="FILE", help="Path to old lock file")
    p_cmp.add_argument(
        "--new",
        default=None,
        metavar="FILE",
        help="Path to new lock file (default: auto-detect current)",
    )
    p_cmp.add_argument(
        "--only-changed",
        action="store_true",
        default=False,
        help="Show only packages that changed (skip unchanged)",
    )
    p_cmp.set_defaults(func=cmd_compare)

    # unused-extras
    p_ue = sub.add_parser(
        "unused-extras",
        help="Find declared extras whose sub-dependencies are never imported",
    )
    p_ue.set_defaults(func=cmd_unused_extras)

    # outdated
    p_out = sub.add_parser(
        "outdated",
        help="Check installed/locked versions against PyPI latest (requires internet)",
    )
    p_out.add_argument(
        "--top",
        "-n",
        type=int,
        default=None,
        metavar="N",
        help="Show only the top N most outdated packages",
    )
    p_out.add_argument(
        "--min-delta",
        choices=["patch", "minor", "major"],
        default="patch",
        help="Minimum version delta to report (default: patch)",
    )
    p_out.set_defaults(func=cmd_outdated)

    # security
    p_sec = sub.add_parser(
        "security",
        help="Check for known CVEs via OSV.dev (requires internet)",
    )
    p_sec.add_argument(
        "--min-severity",
        choices=["low", "medium", "high", "critical"],
        default="low",
        help="Minimum severity to display (default: low)",
    )
    p_sec.add_argument(
        "--update-snapshot",
        action="store_true",
        help="Download latest vulnerabilities from OSV.dev and save to pyxray-security.json",
    )
    p_sec.add_argument(
        "--offline",
        action="store_true",
        help="Run offline using pyxray-security.json instead of querying OSV.dev",
    )
    p_sec.set_defaults(func=cmd_security)

    return parser



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _empty_graph():
    """Return an empty DependencyGraph (used on error paths)."""
    from pyxray.models import DependencyGraph

    return DependencyGraph()


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve graph source: --from-lock wins, then --pypi, then env default
    from_lock = getattr(args, "from_lock", None)
    use_pypi = getattr(args, "pypi", False)
    no_lock = getattr(args, "no_lock", False)
    max_packages = getattr(args, "max_packages", 300)

    ctx = Context(
        project_root=args.root,
        no_color=args.no_color,
        json_output=args.json,
        quiet=args.quiet,
        from_lock=from_lock,
        no_lock=no_lock,
        use_pypi=use_pypi,
        max_packages=max_packages,
    )

    try:
        return args.func(ctx, args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0
    except Exception as exc:
        from pyxray import output as out

        out.print_err(f"Unexpected error: {exc}")
        if not ctx.quiet:
            import traceback

            traceback.print_exc(file=sys.stderr)
        return 1
