"""
cli.py — Argument parsing and command dispatch for PyXRay.

Uses only: argparse (stdlib)
Replaces: click, typer, docopt
"""

from __future__ import annotations

import argparse
import sys

# ---------------------------------------------------------------------------
# Shared context (loaded once, shared across commands)
# ---------------------------------------------------------------------------


class Context:
    """Lazy-loaded analysis context shared across subcommands."""

    def __init__(
        self,
        project_root: str | None,
        no_color: bool,
        json_output: bool,
        quiet: bool,
        verbose: bool,
        from_lock: str | None = None,
        no_lock: bool = False,
        use_pypi: bool = False,
        max_packages: int = 300,
    ) -> None:
        self.project_root = project_root
        self.json_output = json_output
        self.quiet = quiet
        self.verbose = verbose
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

                from pyxray import output as out
                from pyxray.lockfile import build_graph_from_lockfile

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

                from pyxray.lockfile import build_graph_from_lockfile, detect_lockfile

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


























# R2: helper to classify a file path as test vs production
_TEST_SEGMENTS = frozenset({"tests", "test", "testing", "spec", "specs"})








# ---------------------------------------------------------------------------
# F1 — env
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# F2 — check
# ---------------------------------------------------------------------------




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








# ---------------------------------------------------------------------------
# F4 — export (mermaid / dot)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# F5 — compare
# ---------------------------------------------------------------------------








# ---------------------------------------------------------------------------
# F6 — unused-extras
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# F7 — outdated
# ---------------------------------------------------------------------------








# ---------------------------------------------------------------------------
# F8 — security
# ---------------------------------------------------------------------------




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
        help="Suppress progress output",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output / stack traces for errors",
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
    
    def run_cmd_summary(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.summary")
        return getattr(mod, "cmd_summary")(ctx, args)
    
    p_sum.set_defaults(func=run_cmd_summary)

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
    
    def run_cmd_tree(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.tree")
        return getattr(mod, "cmd_tree")(ctx, args)
    
    p_tree.set_defaults(func=run_cmd_tree)

    # why
    p_why = sub.add_parser("why", help="Explain why a package is installed")
    p_why.add_argument("package", help="Package name to explain")
    p_why.add_argument(
        "--max-paths",
        type=int,
        default=5,
        help="Maximum number of paths to show (default: 5)",
    )
    
    def run_cmd_why(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.why")
        return getattr(mod, "cmd_why")(ctx, args)
    
    p_why.set_defaults(func=run_cmd_why)

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
    
    def run_cmd_impact(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.impact")
        return getattr(mod, "cmd_impact")(ctx, args)
    
    p_impact.set_defaults(func=run_cmd_impact)

    # duplicates
    p_dup = sub.add_parser(
        "duplicates", help="Detect packages installed with multiple versions"
    )
    
    def run_cmd_duplicates(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.duplicates")
        return getattr(mod, "cmd_duplicates")(ctx, args)
    
    p_dup.set_defaults(func=run_cmd_duplicates)

    # cycles
    p_cyc = sub.add_parser("cycles", help="Detect circular dependencies")
    
    def run_cmd_cycles(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.cycles")
        return getattr(mod, "cmd_cycles")(ctx, args)
    
    p_cyc.set_defaults(func=run_cmd_cycles)

    # stats
    p_stats = sub.add_parser("stats", help="Detailed graph statistics")
    
    def run_cmd_stats(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.stats")
        return getattr(mod, "cmd_stats")(ctx, args)
    
    p_stats.set_defaults(func=run_cmd_stats)

    # hotspots
    p_hot = sub.add_parser("hotspots", help="Packages with the most dependents")
    p_hot.add_argument(
        "--top",
        "-n",
        type=int,
        default=20,
        help="Number of results to show (default: 20)",
    )
    
    def run_cmd_hotspots(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.hotspots")
        return getattr(mod, "cmd_hotspots")(ctx, args)
    
    p_hot.set_defaults(func=run_cmd_hotspots)

    # longest-chain
    p_lc = sub.add_parser("longest-chain", help="Find the longest dependency path")
    
    def run_cmd_longest_chain(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.longest_chain")
        return getattr(mod, "cmd_longest_chain")(ctx, args)
    
    p_lc.set_defaults(func=run_cmd_longest_chain)

    # imports
    p_imp = sub.add_parser("imports", help="Scan source code for import statements")
    p_imp.add_argument(
        "--no-unknown",
        action="store_true",
        default=False,
        help="Suppress unclassified import listing",
    )
    
    def run_cmd_imports(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.imports")
        return getattr(mod, "cmd_imports")(ctx, args)
    
    p_imp.set_defaults(func=run_cmd_imports)

    # audit
    p_audit = sub.add_parser(
        "audit",
        help="Compare declared dependencies with detected source imports",
    )
    
    def run_cmd_audit(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.audit")
        return getattr(mod, "cmd_audit")(ctx, args)
    
    p_audit.set_defaults(func=run_cmd_audit)

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
    
    def run_cmd_prune(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.prune")
        return getattr(mod, "cmd_prune")(ctx, args)
    
    p_prune.set_defaults(func=run_cmd_prune)

    # env
    p_env = sub.add_parser("env", help="Show Python environment and project info")
    
    def run_cmd_env(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.env")
        return getattr(mod, "cmd_env")(ctx, args)
    
    p_env.set_defaults(func=run_cmd_env)

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
    
    def run_cmd_check(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.check")
        return getattr(mod, "cmd_check")(ctx, args)
    
    p_check.set_defaults(func=run_cmd_check)

    # license
    p_lic = sub.add_parser("license", help="Show license inventory across all packages")
    p_lic.add_argument(
        "--show-packages",
        action="store_true",
        default=False,
        help="List every package under each license group",
    )
    
    def run_cmd_license(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.license")
        return getattr(mod, "cmd_license")(ctx, args)
    
    p_lic.set_defaults(func=run_cmd_license)

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
    
    def run_cmd_export(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.export")
        return getattr(mod, "cmd_export")(ctx, args)
    
    p_exp.set_defaults(func=run_cmd_export)

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
    
    def run_cmd_compare(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.compare")
        return getattr(mod, "cmd_compare")(ctx, args)
    
    p_cmp.set_defaults(func=run_cmd_compare)

    # unused-extras
    p_ue = sub.add_parser(
        "unused-extras",
        help="Find declared extras whose sub-dependencies are never imported",
    )
    
    def run_cmd_unused_extras(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.unused_extras")
        return getattr(mod, "cmd_unused_extras")(ctx, args)
    
    p_ue.set_defaults(func=run_cmd_unused_extras)

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
    
    def run_cmd_outdated(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.outdated")
        return getattr(mod, "cmd_outdated")(ctx, args)
    
    p_out.set_defaults(func=run_cmd_outdated)

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
    
    def run_cmd_security(ctx, args):
        import importlib
        mod = importlib.import_module("pyxray.commands.security")
        return getattr(mod, "cmd_security")(ctx, args)
    
    p_sec.set_defaults(func=run_cmd_security)

    return parser



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _empty_graph():
    """Return an empty DependencyGraph (used on error paths)."""
    from pyxray.models import DependencyGraph

    return DependencyGraph()


def main(argv: list[str] | None = None) -> int:
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
        verbose=getattr(args, "verbose", False),
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