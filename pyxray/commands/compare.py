from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



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
    from pathlib import Path

    from pyxray import output as out
    from pyxray.lockfile import load_lockfile

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
