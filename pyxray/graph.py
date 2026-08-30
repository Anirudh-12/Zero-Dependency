"""
graph.py — Build the dependency graph from installed metadata.

This is the heart of PyXRay.

Algorithm
---------
Starting from the project's declared requirements, we BFS through installed
distribution metadata (importlib.metadata) to discover the full transitive
dependency graph.  We use only:

    collections.deque     — BFS queue
    importlib.metadata    — distribution lookup
    pyxray.models         — our own data types
    pyxray.requirements   — marker evaluation

Replaces: networkx, pipdeptree, graphlib (limited), packaging
"""

from __future__ import annotations

from collections import deque

from pyxray.models import (
    DependencyGraph,
    Package,
    Project,
)
from pyxray.requirements import evaluate_marker

# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


class GraphBuilder:
    """Build a DependencyGraph from a Project and the installed environment.

    Parameters
    ----------
    installed:
        Pre-loaded dict of normalized_name → Package for *all* installed
        distributions.  Pass ``discover_all_installed()`` output here.
    project:
        The project whose declared dependencies are the graph roots.
    """

    def __init__(
        self,
        installed: dict[str, Package],
        project: Project,
    ) -> None:
        self._installed = installed
        self._project = project
        self._warnings: list[str] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def build(self) -> tuple[DependencyGraph, list[str]]:
        """BFS from project roots → full transitive graph.

        Returns (graph, warnings).
        """
        graph = DependencyGraph()
        queue: deque[str] = deque()
        visited: set[str] = set()

        # ---- Seed with project declared deps -------------------------
        for req in self._project.declared:
            if not req.name:
                continue
            norm = req.normalized_name
            graph.roots.add(norm)
            if norm not in visited:
                queue.append(norm)
                visited.add(norm)

        # ---- BFS through transitive deps ----------------------------
        while queue:
            norm_name = queue.popleft()
            pkg = self._installed.get(norm_name)

            if pkg is None:
                graph.missing.add(norm_name)
                self._warn(
                    f"'{norm_name}' is declared/required but not installed "
                    f"in the current environment."
                )
                # Still add a stub node so the graph stays connected
                stub = Package(
                    name=norm_name,
                    normalized_name=norm_name,
                    version="?",
                )
                graph.add_package(stub)
                continue

            graph.add_package(pkg)

            # Process each Requires-Dist
            for req in pkg.requires:
                if not req.name:
                    continue
                # Evaluate environment markers — skip if not applicable
                if req.marker and not evaluate_marker(req.marker):
                    continue

                dep_norm = req.normalized_name
                graph.add_edge(norm_name, dep_norm)

                if dep_norm not in visited:
                    visited.add(dep_norm)
                    queue.append(dep_norm)

        return graph, self._warnings

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _warn(self, msg: str) -> None:
        self._warnings.append(msg)


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def build_graph(
    project: Project,
    installed: dict[str, Package],
) -> tuple[DependencyGraph, list[str]]:
    """Build and return the full dependency graph for *project*.

    This is the main entry point used by CLI commands.

    Returns (DependencyGraph, warnings).
    """
    builder = GraphBuilder(installed=installed, project=project)
    return builder.build()
