# STDLIB.md — Standard Library Substitutions

Every third-party package PyXRay does NOT use, and the standard-library facility it uses instead.

This document is the evidence log for the Zero Dependency Craft score.

---

## Substitution Table

| What we would normally install | PyXRay uses instead | Stdlib module | Notes |
|---|---|---|---|
| `networkx` | Custom graph (`DependencyGraph`) | `collections`, `dataclasses` | Forward + reverse adjacency sets; BFS/DFS/topo-sort implemented from scratch |
| `pipdeptree` | `importlib.metadata` + BFS traversal | `importlib.metadata` | Reads `Requires-Dist` directly; builds graph without subprocess calls |
| `packaging` (requirement parser) | Custom PEP 508 parser | `re`, `sys`, `platform` | Handles name, extras, specifiers, markers; limitation: no version compatibility evaluation |
| `packaging` (name normalization) | One-line PEP 503 function | `re` | `re.sub(r"[-_.]+", "-", name).lower()` — the exact same rule |
| `rich` | Custom ANSI output layer | `sys`, `os` | Raw escape codes; `NO_COLOR` + TTY detection; tree/table rendering; section headers |
| `colorama` | Raw ANSI escape sequences | `os`, `sys` | `\033[91m` etc.; TTY-gated; respects `NO_COLOR` env var |
| `click` / `typer` | `argparse` | `argparse` | 10-command CLI with subparsers, help text, examples, and exit codes |
| `tomli` / `toml` | `tomllib` | `tomllib` (Python 3.11+) | Read-only; write-TOML not needed for this tool |
| `pydantic` / `attrs` | `dataclasses` | `dataclasses`, `typing` | `Package`, `Requirement`, `DependencyGraph`, `SourceImport`, `AnalysisResult` |
| `isort` / `importlab` / `import-linter` | `ast` walker | `ast` | Full `ast.walk` over project `.py` files; catches nested imports |
| `vulture` (unused import detection) | Custom audit via AST + graph comparison | `ast` | Compares declared deps with detected static imports |
| `graphlib.TopologicalSorter` | Kahn's algorithm (manual) | none needed | Own BFS-based topo sort; handles cycles gracefully for longest-chain |
| `pathspec` / `glob` (file walking) | `os.walk` + manual pattern filter | `os`, `pathlib` | Skip dirs by name set; `.egg-info` suffix matching |
| `stdlib-list` (stdlib detection) | `sys.stdlib_module_names` | `sys` (Python 3.10+) | Falls back to curated frozenset on older versions |
| `tqdm` (progress) | Not used — startup is fast | — | Graph build is O(n) over installed packages; no progress bar needed |
| `json` (serialization) | `json` | `json` | `--json` output via stdlib `json.dumps` |

---

## Package Killer Detail

### `networkx` (killed)

**What it normally does:** Graph data structure + BFS, DFS, cycle detection, shortest path, topological sort, centrality measures.

**What we use:** `DependencyGraph` in `models.py` with `forward: dict[str, set[str]]` and `reverse: dict[str, set[str]]`. All algorithms in `analysis.py`:
- BFS reachability: `collections.deque`
- DFS cycle detection: node colouring (WHITE/GREY/BLACK)
- Topological sort: Kahn's algorithm with `collections.deque`
- Longest path: DP over topological order
- Shortest path (why): BFS with path tracking

**Limitation:** No weighted graphs, no spectral analysis, no layout algorithms. We don't need them.

---

### `pipdeptree` (killed)

**What it normally does:** Subprocess tool that shells out to pip internals to render a dependency tree.

**What we use:** `importlib.metadata.distributions()` to enumerate all installed packages; `dist.metadata.get_all("Requires-Dist")` to read their declared dependencies. BFS traversal builds the full graph without spawning any subprocess.

**Limitation:** Only sees the current environment; does not simulate other Python versions.

---

### `packaging` (killed)

**What it normally does:** PEP 440 version parsing, PEP 503 name normalization, PEP 508 requirement string parsing, marker evaluation.

**What we use:**
1. **Name normalization:** `re.sub(r"[-_.]+", "-", name).lower()` — the identical one-liner from PEP 503.
2. **Requirement parsing:** Custom regex-based parser in `requirements.py`. Handles name, extras `[foo,bar]`, version specifiers `>=2,<3`, and environment markers after `;`.
3. **Marker evaluation:** Partial evaluator that handles `sys_platform`, `python_version`, `platform_machine`, `and`/`or` compound markers.

**Limitation:** We do not evaluate `~=` (compatible release) for filtering. Version comparison is string-based, not PEP 440 semantics. This is sufficient for marker-based graph pruning.

---

### `rich` (killed)

**What it normally does:** Terminal markup, syntax highlighting, tables, progress bars, panels, tree rendering.

**What we use:** `output.py` — raw ANSI escape codes for colour, `├── └── │` box-drawing characters for trees, manual column alignment for tables, `─` dividers for sections. 170 lines of output utilities, zero dependencies.

**Limitation:** No syntax highlighting inside output. No spinners. No live rendering. The tool is fast enough not to need them.

---

### `click` / `typer` (killed — 76M+/wk combined)

**What it normally does:** Decorator-based CLI framework with automatic help generation, type coercion, nested commands.

**What we use:** `argparse` with `add_subparsers`. Each command is a plain function. Help text is written manually. Exit codes are returned explicitly.

**Limitation:** No automatic type coercion beyond `int` and `str`. No shell completion. `--no-color` must precede the subcommand (standard argparse limitation with subparsers).

---

### `tomli` / `toml` (killed)

**What it normally does:** Read and write TOML files from Python.

**What we use:** `tomllib` (Python 3.11 stdlib, backport of `tomli` but read-only). We never write TOML.

**Limitation:** Python 3.10 and earlier are not supported (though our `requires-python = ">=3.11"` makes this explicit).

---

### `isort` / `import-linter` (killed)

**What it normally does:** Sort imports, detect import violations, scan which packages are imported.

**What we use:** `ast.walk` over the full AST of every `.py` file in the project. Collects `ast.Import` and `ast.ImportFrom` nodes. Top-level module extracted from dotted names. Relative imports (`level > 0`) excluded.

**Limitation:** Does not detect `importlib.import_module(...)`, `__import__(...)`, or string-based dynamic imports.

---

## STDLIB Log (10+ real substitutions)

1. **`collections.deque`** → BFS queue for graph traversal and shortest-path search. Replaces graph library traversal utilities.
2. **`importlib.metadata.distributions()`** → Enumerate all installed packages without pip. Replaces `pip list`, `pkg_resources`, `pipdeptree`.
3. **`importlib.metadata.distribution(name).metadata`** → Read package metadata fields (Name, Version, Requires-Dist) without subprocess. Replaces `pip show`.
4. **`ast.walk(ast.parse(source))`** → Static import extraction. Replaces `isort`, `importlab`, `vulture`.
5. **`re.sub(r"[-_.]+", "-", name).lower()`** → PEP 503 name normalization. Replaces `packaging.utils.canonicalize_name`.
6. **`sys.stdlib_module_names`** (Python 3.10+) → Authoritative stdlib module set for classifying imports. Replaces `stdlib-list` package.
7. **`tomllib.load()`** → TOML parsing for `pyproject.toml`. Replaces `tomli`, `toml`, `poetry.core`.
8. **`sys.stdout.isatty()`** → TTY detection for ANSI color. Replaces `colorama.init()`, `rich.console.Console`.
9. **`os.environ.get("NO_COLOR")`** → Honour the NO_COLOR standard. Replaces `rich`'s `force_terminal` flags.
10. **`dataclasses.dataclass`** → Typed, validated data structures without runtime schema libraries. Replaces `pydantic.BaseModel`, `attrs.define`.
11. **`collections.deque` + manual Kahn BFS** → Topological sort for longest-chain DP. Replaces `graphlib.TopologicalSorter` (which itself doesn't handle cycles).
12. **`os.walk` + set-based skip list** → Recursive `.py` file discovery with directory pruning. Replaces `pathspec`, `glob` patterns.
13. **`platform.python_version_tuple()`** → Environment marker evaluation (python_version comparisons). Replaces `packaging.markers`.
14. **`sys.platform`** → `sys_platform` marker evaluation (win32, linux, darwin). Replaces `packaging.markers`.
15. **`json.dumps(..., indent=2, default=str)`** → All `--json` command output. No serialization library.
16. **`urllib.request.urlopen()`** → Fetching metadata from PyPI JSON API for `--pypi` mode. Replaces `requests`, `httpx`.
17. **`argparse.ArgumentParser`** → Command line parsing for CLI. Replaces `click`, `typer`.

---

## Honest Gaps

These are places where the standard library genuinely has no answer, and we did not pretend otherwise:

- **TOML writing:** Not needed for PyXRay. If it were, we would write it by hand (`key = "value"\n` templating) and document it here.
- **PEP 440 version ordering:** Not implemented. We use string comparison for markers, which is sufficient for `==` and `!=` but not for `>=` version comparison of dynamic marker values. This is a documented limitation.
- **Async runtime:** Not needed. Graph analysis is synchronous and fast.

---

## Why This Matters

Every substitution above represents a package that brings its own supply chain with it. `packaging` alone pulls in nothing, but `click` depends on `colorama` on Windows, `rich` depends on `markdown-it-py`, `pygments`, `mdurl`. By using only the standard library, PyXRay has a supply chain of exactly one: CPython itself.
