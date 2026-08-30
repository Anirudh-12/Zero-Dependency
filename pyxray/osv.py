"""
osv.py — Query the OSV.dev vulnerability database.

Uses only:
    urllib.request  (stdlib)
    json            (stdlib)

API: POST https://api.osv.dev/v1/querybatch
     Single request for all packages — zero N+1 fetching.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
_TIMEOUT = 30  # seconds — batch request can be slow


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_osv_batch(
    packages: list[tuple[str, str]],
) -> dict[str, list[dict]]:
    """Query OSV.dev for all (name, version) pairs in a single batched POST.

    Parameters
    ----------
    packages:
        List of (normalized_name, version) tuples.

    Returns
    -------
    dict mapping normalized_name → list of vulnerability dicts.
    An empty list means no known vulnerabilities for that package.
    """
    if not packages:
        return {}

    # OSV uses PyPI ecosystem name matching; send as-is (normalized works fine)
    queries = [
        {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
        for name, version in packages
    ]
    payload = json.dumps({"queries": queries}).encode("utf-8")

    try:
        req = urllib.request.Request(
            OSV_BATCH_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "pyxray/0.1.0 (stdlib-only; https://github.com/pyxray)",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Network failure → return empty (silent fail, non-blocking)
        return {}

    results = data.get("results", [])
    output: dict[str, list[dict]] = {}

    for (name, _version), result in zip(packages, results):
        vulns = result.get("vulns", [])
        output[name] = vulns

    return output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def format_severity(vuln: dict) -> str:
    """Extract the highest severity label from a vulnerability object."""
    # Try database_specific.severity first (GitHub / PyPA format)
    db_sev = vuln.get("database_specific", {}).get("severity", "")
    if db_sev:
        return db_sev.upper()

    # Try severity[] array (CVSS format)
    for sev_entry in vuln.get("severity", []):
        score_str = sev_entry.get("score", "")
        if score_str.startswith("CVSS:"):
            # Parse base score from CVSS vector: CVSS:3.1/AV:.../...
            # Score is the numeric value in the 'score' field separately
            pass
        # Some entries have 'type' and 'score'
        sev_type = sev_entry.get("type", "")
        if "CVSS_V3" in sev_type or "CVSS_V2" in sev_type:
            try:
                score = float(sev_entry.get("score", 0))
                if score >= 9.0:
                    return "CRITICAL"
                elif score >= 7.0:
                    return "HIGH"
                elif score >= 4.0:
                    return "MEDIUM"
                else:
                    return "LOW"
            except (ValueError, TypeError):
                pass

    return "LOW"


def extract_fixed_in(vuln: dict, pkg_name: str) -> Optional[str]:
    """Extract the 'fixed in version' string from an OSV vulnerability.

    Returns None if no fix is known.
    """
    for affected in vuln.get("affected", []):
        pkg = affected.get("package", {})
        if pkg.get("ecosystem", "").lower() != "pypi":
            continue
        for rng in affected.get("ranges", []):
            if rng.get("type") not in ("ECOSYSTEM", "SEMVER"):
                continue
            for event in rng.get("events", []):
                fixed = event.get("fixed")
                if fixed:
                    return fixed
    return None
