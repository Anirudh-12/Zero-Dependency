"""
requirements.py — Scoped PEP 508 requirement string parser.

Replaces: ``packaging`` library (specifically packaging.requirements).

We implement a deliberately scoped parser that handles the vast majority
of real-world Requires-Dist strings:

    requests
    requests>=2.0
    requests==2.31.0
    requests>=2,<3
    foo[extra,security]>=1.2
    foo; python_version < "3.12"
    foo>=1.0; sys_platform == "win32"

Unsupported forms (URL requirements, PEP 440 arbitrary == with ===, etc.)
are returned with parse_error set rather than raising.

Limitations documented in STDLIB.md:
- Marker evaluation is partial (sys_platform, python_version, platform_machine)
- ~= (compatible release) operator is stored but NOT evaluated for filtering
- Very exotic Unicode names are not tested
"""

from __future__ import annotations

import platform
import re
import sys
from typing import Optional

from pyxray.models import Requirement, Specifier, normalize_name

# ---------------------------------------------------------------------------
# Regex building blocks
# ---------------------------------------------------------------------------

# Package name: PEP 508 §  name = letter (letter | digit | "-" | "_" | ".")*
_NAME_RE = re.compile(r"([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)", re.ASCII)

# Extras: [extra1, extra2]
_EXTRAS_RE = re.compile(r"\[([^\]]*)\]")

# Version specifier operators
_OP_RE = re.compile(r"(===|~=|==|!=|>=|<=|>|<)")

# Version string (including epoch, local segment)
_VER_RE = re.compile(r"([A-Za-z0-9._!+*]+)")

# URL marker (@ https://...) — unsupported, used only for detection
_URL_RE = re.compile(r"@\s*\S+")


def fast_extract_normalized_name(raw: str) -> Optional[str]:
    """Extremely fast extraction of the normalized package name from a PEP 508 string.
    
    Used during graph construction to avoid fully parsing Requirements.
    Interns the resulting string for O(1) dict lookups.
    """
    if " #" in raw:
        raw = raw[: raw.index(" #")]
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
        
    m = _NAME_RE.match(raw)
    if m:
        return sys.intern(normalize_name(m.group(1)))
        
    if _URL_RE.search(raw):
        s = raw.split("@")[0].strip()
        m2 = _NAME_RE.match(s)
        if m2:
            return sys.intern(normalize_name(m2.group(1)))
            
    return None



def parse_requirement(raw: str) -> Requirement:
    """Parse a PEP 508 dependency string into a ``Requirement``.

    On parse failure sets ``parse_error`` rather than raising.
    """
    original = raw
    s = raw.strip()

    # Strip inline comments
    if " #" in s:
        s = s[: s.index(" #")].rstrip()
    if s.startswith("#"):
        return Requirement(
            raw=original,
            name="",
            normalized_name="",
            extras=frozenset(),
            specifiers=[],
            parse_error="comment line",
        )

    if not s:
        return Requirement(
            raw=original,
            name="",
            normalized_name="",
            extras=frozenset(),
            specifiers=[],
            parse_error="empty",
        )

    # Detect URL requirements (foo @ https://…) — not supported
    if _URL_RE.search(s):
        # Extract name best-effort
        m = _NAME_RE.match(s)
        name = m.group(1) if m else s.split("@")[0].strip()
        return Requirement(
            raw=original,
            name=name,
            normalized_name=normalize_name(name),
            extras=frozenset(),
            specifiers=[],
            parse_error=f"URL requirements not supported: {s!r}",
        )

    # ---- Name -------------------------------------------------------
    m = _NAME_RE.match(s)
    if not m:
        return Requirement(
            raw=original,
            name=s,
            normalized_name=normalize_name(s),
            extras=frozenset(),
            specifiers=[],
            parse_error=f"could not parse name from {s!r}",
        )

    name = m.group(1)
    pos = m.end()

    # ---- Extras -----------------------------------------------------
    extras: frozenset[str] = frozenset()
    em = _EXTRAS_RE.match(s, pos)
    if em:
        extras = frozenset(e.strip() for e in em.group(1).split(",") if e.strip())
        pos = em.end()

    # ---- Marker split: everything after ';' -------------------------
    marker: Optional[str] = None
    if ";" in s[pos:]:
        idx = s.index(";", pos)
        marker = s[idx + 1 :].strip() or None
        spec_part = s[pos:idx].strip()
    else:
        spec_part = s[pos:].strip()

    # ---- Specifiers --------------------------------------------------
    specifiers: list[Specifier] = []
    parse_error: Optional[str] = None

    if spec_part:
        for chunk in spec_part.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            op_m = _OP_RE.match(chunk)
            if not op_m:
                parse_error = f"unrecognised specifier {chunk!r}"
                break
            op = op_m.group(1)
            ver_m = _VER_RE.match(chunk, op_m.end())
            if not ver_m:
                parse_error = f"could not parse version in {chunk!r}"
                break
            specifiers.append(Specifier(operator=op, version=ver_m.group(1)))

    return Requirement(
        raw=original,
        name=name,
        normalized_name=normalize_name(name),
        extras=extras,
        specifiers=specifiers,
        marker=marker,
        parse_error=parse_error,
    )


# ---------------------------------------------------------------------------
# Environment marker evaluation
# ---------------------------------------------------------------------------

_MARKER_VAR_MAP = {
    "python_version": ".".join(platform.python_version_tuple()[:2]),
    "python_full_version": platform.python_version(),
    "sys_platform": sys.platform,
    "platform_machine": platform.machine(),
    "platform_system": platform.system(),
    "os_name": "nt" if sys.platform == "win32" else "posix",
    "os.name": "nt" if sys.platform == "win32" else "posix",
    "platform_python_implementation": platform.python_implementation(),
    "implementation_name": platform.python_implementation().lower(),
}

_MARKER_EXPR_RE = re.compile(
    r'([a-z_]+(?:\.[a-z_]+)?)\s*(==|!=|<|<=|>|>=|in|not\s+in)\s*"([^"]*)"'
    r'|"([^"]*)"\s*(==|!=|<|<=|>|>=|in|not\s+in)\s*([a-z_]+(?:\.[a-z_]+)?)',
    re.IGNORECASE,
)


def _compare(lhs: str, op: str, rhs: str) -> bool:
    op = op.strip()
    if op == "==":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    if op == "<":
        return lhs < rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">":
        return lhs > rhs
    if op == ">=":
        return lhs >= rhs
    if op in ("in",):
        return lhs in rhs
    if op in ("not in",):
        return lhs not in rhs
    return True  # unknown → include


def evaluate_marker(marker: Optional[str], extra: str = "") -> bool:
    """Return True if *marker* passes for the current environment.

    This is a best-effort partial evaluator. Unknown variables → include.
    Compound markers with ``and``/``or`` are evaluated left-to-right with
    correct short-circuit (simple split on ``and``/``or`` keywords).

    Returns True (include) on any parse failure — safe default.
    """
    if not marker:
        return True
    marker = marker.strip()

    # Handle compound markers (and / or) with basic recursive split.
    # Split on ' and ' first (higher precedence in PEP 508).
    if " and " in marker.lower():
        parts = re.split(r"\s+and\s+", marker, flags=re.IGNORECASE)
        return all(evaluate_marker(p, extra) for p in parts)
    if " or " in marker.lower():
        parts = re.split(r"\s+or\s+", marker, flags=re.IGNORECASE)
        return any(evaluate_marker(p, extra) for p in parts)

    # Strip surrounding parens
    stripped = marker.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return evaluate_marker(stripped[1:-1], extra)

    m = _MARKER_EXPR_RE.match(stripped)
    if not m:
        return True  # unrecognised → include

    env_map = dict(_MARKER_VAR_MAP)
    env_map["extra"] = extra

    if m.group(1):  # var op "value"
        var_name, op, value = m.group(1), m.group(2), m.group(3)
        env_val = env_map.get(var_name)
        if env_val is None:
            return True
        return _compare(env_val, op, value)
    else:  # "value" op var
        value, op, var_name = m.group(4), m.group(5), m.group(6)
        env_val = env_map.get(var_name)
        if env_val is None:
            return True
        return _compare(value, op, env_val)
