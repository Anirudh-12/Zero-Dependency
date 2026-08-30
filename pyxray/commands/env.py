from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_env(ctx: Context, args: argparse.Namespace) -> int:
    """Print Python environment and project information."""
    import platform
    import sys
    import sysconfig

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
