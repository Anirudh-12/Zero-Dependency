from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_security(ctx: Context, args: argparse.Namespace) -> int:
    """Check for known CVEs via OSV.dev batch API."""
    from pyxray import output as out
    from pyxray.osv import extract_fixed_in, format_severity, query_osv_batch

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
        vuln_results = query_osv_batch(packages, verbose=ctx.verbose)
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
