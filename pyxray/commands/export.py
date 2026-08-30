from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_export(ctx: Context, args: argparse.Namespace) -> int:
    """Export the dependency graph in Mermaid or Graphviz DOT format (stdout)."""

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
