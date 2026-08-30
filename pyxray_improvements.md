# PyXRay — Improvement Analysis

## 🆕 Missing Features Worth Adding

### 1. `compare` Command — Before/After Diff
Show what changed between two lock files (or two environments).

```bash
python -m pyxray compare --old uv.lock.bak --new uv.lock
```

**Output:**
```
+ added:   httpx 0.29.0  (was 0.28.1)
- removed: certifi 2024.6.2  →  certifi 2025.1.1 (version bump)
~ changed: anyio 4.11 → 4.12.1
```

**Why:** Reviewers live in PRs. Knowing *what changed* in a lockfile is far more useful than a static snapshot. No external tools needed — just diff two graphs.

---

### 2. `license` Command — License Inventory
Scan `METADATA` / `dist-info` for the `License` field across the full graph.

```bash
python -m pyxray license
python -m pyxray license --json
```

**Output:**
```
License Inventory — fastapi
──────────────────────────────────────────────────
  MIT               132 packages
  Apache-2.0         54 packages
  BSD-3-Clause       12 packages
  Unknown             7 packages
```

**Why:** Legal compliance is a real concern and the data is already in `importlib.metadata`. Zero extra deps needed.

---

### 3. `outdated` Command — Version Staleness Check
Compare installed/locked versions against PyPI's latest.

```bash
python -m pyxray outdated
python -m pyxray outdated --top 10
```

**Output:**
```
Outdated Packages
  requests  2.28.0  →  2.32.3  (2 major behind)
  certifi   2023.5.7 → 2025.1.31
```

**Why:** Currently the `--pypi` flag fetches the graph from PyPI but has no "am I current?" report. This adds direct value. Uses the existing `pypi.py` infrastructure.

---

### 4. `unused-extras` Command — Declared Extras Analysis
Detect when a dependency is declared with extras (e.g. `pydantic[email]`) but the extra's sub-deps are never used in source.

**Why:** Extras bloat the install set. This is a natural extension of `prune` that targets a specific common waste pattern.

---

### 5. `dot` / `mermaid` Export Command
Export the dependency graph in Graphviz DOT or Mermaid format.

```bash
python -m pyxray dot > graph.dot
python -m pyxray mermaid > graph.md
```

**Why:** Visual graph exploration complements the ASCII tree. Both formats are plain text — zero-dep friendly. Users can paste Mermaid output directly into GitHub markdown.

---

### 6. `security` / `vuln` Command — CVE Advisory Check
Cross-reference installed package versions against a bundled or fetched advisory database (OSV.dev public API).

```bash
python -m pyxray security
```

**Why:** `pip audit` needs pip. PyXRay can do a lightweight version using `urllib.request` (stdlib only) against `https://api.osv.dev/v1/query` — staying true to the zero-dep principle.

---

### 7. `env` Command — Python Environment Summary
Report interpreter version, virtual env path, site-packages location, and pip/uv version — in machine-readable form.

```bash
python -m pyxray env
python -m pyxray env --json
```

**Why:** Useful for CI triage and bug reports. All data is available via `sys`, `sysconfig`, and `importlib.metadata`.

---

### 8. `check` / `health` Command — Actionable OK/FAIL Gate
An opinionated pass/fail gate that checks: no cycles, no missing packages, no high-severity unused declarations. Returns exit code 1 on failure for CI integration.

```bash
python -m pyxray check
# → exits 0 or 1
```

---

## ⚡ Speed Improvements

### 1. Cache the Full Graph Object (not just AST)
**Current:** `lockfile.py` caches the raw `(packages, warnings)` dict. Every invocation still re-runs `build_graph_from_lockfile` (BFS + edge construction).

**Fix:** Serialize and cache the entire `DependencyGraph` object in `.pyxray_cache/graph.pkl` keyed by lockfile mtime. On cache hit, skip graph construction entirely.

**Files:** [`lockfile.py`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/lockfile.py), [`cli.py`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/cli.py) → `Context.get_graph()`

**Impact:** On large environments (200+ packages), graph construction is dominated by `parse_requirement` calls. Caching the graph object would make second+ runs near-instant.

---

### 2. Lazy `parse_requirement` — `fast_extract_normalized_name` is Already There
**Current:** `build_graph_from_lockfile` calls `fast_extract_normalized_name(raw)` for edge construction — good. But `Package.requires` (the full parsed `Requirement` list) is lazily computed via `parse_requirement`. This lazy path is only triggered if `Package.requires` is accessed — which the graph builder does not do.

**Verify:** Confirm that `cmd_tree`, `cmd_why`, `cmd_impact` never read `pkg.requires` (they only use `graph.forward` edges). If any command accidentally accesses `.requires`, it triggers O(n) full parsing unnecessarily.

---

### 3. Parallelize AST File Scanning
**Current:** [`source.py`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/source.py) scans files sequentially in `scan_source_roots` / `scan_with_usage`. On projects with thousands of `.py` files, this is the bottleneck.

**Fix:** Use `concurrent.futures.ThreadPoolExecutor` (stdlib) to scan files in parallel. The AST parse is CPU-bound but GIL-friendly enough that threads provide meaningful speedup on I/O-heavy reads.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
    futures = {ex.submit(extract_imports_with_symbols, fpath): fpath for fpath in py_files}
    for fut in as_completed(futures):
        ...
```

**Impact:** On large monorepos (500+ `.py` files), this can cut `audit`/`prune`/`imports` command time significantly.

---

### 4. `compute_stats` Calls `find_cycles` — Duplicate Work
**Current:** [`analysis.py`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/analysis.py#L346-L398) — `compute_stats()` calls `find_cycles()` internally. `cmd_longest_chain` also calls `find_cycles()` separately. If both run in the same invocation (e.g. from `summary`), cycles are computed twice.

**Fix:** Cache the cycle result on the graph object, or pass it as an optional param:
```python
def compute_stats(graph, cycles=None):
    if cycles is None:
        cycles = find_cycles(graph)
```

---

### 5. `reachable_from` Called Per-Root in `compute_stats`
**Current:** `largest_subtree` calculation calls `reachable_from(graph, root)` once per root. For large graphs with many roots, this is O(roots × nodes).

**Fix:** Run a single multi-source BFS from all roots simultaneously to compute subtree sizes.

---

## 📖 Output Readability Improvements

### 1. `impact` — Group by Depth Layer
**Current:** `impact` prints a flat sorted list of all affected packages.

**Improvement:** Group by how many hops away they are:

```
Impact of 'typing-extensions'
  Direct dependents (1 hop):   pydantic, anyio, starlette
  Transitive (2 hops):         pydantic-core, httpx, ...
  Deep transitive (3+ hops):   27 packages
```

**File:** [`cli.py`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/cli.py#L357-L406) → `cmd_impact`

---

### 2. `audit` — Distinguish "test-only" vs "production" Undeclared Imports
**Current:** All undeclared imports are listed together. `dirty-equals` (a test util) is listed alongside `httpx` (used in production).

**Improvement:** Detect if a file is under a `tests/` or `test_*.py` directory and tag imports accordingly:

```
  ✗ Imported but not declared:
    • httpx    [production]  fastapi/routing.py:4
    • pytest   [tests only]  tests/test_main.py:1
```

---

### 3. `prune` — Show Replacement Suggestion
**Current:** `REIMPLEMENT` candidates are listed with signal counts but no actionable hint.

**Improvement:** For known thin packages, add a stdlib alternative hint:

```
  ✎ typing-inspection  —  REIMPLEMENT
      Suggestion: inspect.get_annotations() (Python 3.10+) covers is_typealiastype
```

---

### 4. `hotspots` — Add Risk Score Column
**Current:** Hotspots shows in-degree (dependents count) only.

**Improvement:** Add a composite risk score = `in_degree × (1 + transitive_subtree_size)`. A package depended on by 5 others AND pulling 30 transitive deps is riskier than one depended on by 5 with 0 transitive.

---

### 5. `summary` — Add Health Score / Grade
Give the project a single letter grade (A–F) based on: cycle count, missing packages, unused declarations, deepest chain.

```
  Health Score: B+  (no cycles, 0 missing, 2 unused declarations)
```

**Why:** Makes the summary actionable at a glance for CI dashboards.

---

### 6. `tree` — Configurable Sort Order
**Current:** Children are always sorted alphabetically (`sorted(graph.forward.get(n, set()))`).

**Improvement:** Add `--sort-by {alpha,version,size}` flag. Sorting by subtree size puts the heaviest deps first — much more useful for triage.

---

### 7. `why` — Show Version Constraint Along Each Edge
**Current:** Path shows just package names.

**Improvement:** Show the version specifier that caused the dependency:

```
  fastapi (5.0.0)
    └── requires starlette>=1.0  →  starlette (1.3.1)
      └── requires anyio>=4.0   →  anyio (4.12.1)
```

---

### 8. Paged / `--limit` Output for Large Lists
**Current:** `impact certifi` on a 200-package env can dump 100+ lines with no pagination.

**Improvement:** Add `--limit N` flag to cap list output, with a trailing `  … and N more` line. Already partially done for `audit` (cap at 5 locations).

---

## 🧹 Code Quality / Architecture

| Issue | Location | Fix |
|---|---|---|
| `scan_with_usage` uses `__import__("os").walk` | [`source.py:667`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/source.py#L667) | Use top-level `import os` (already imported) |
| `find_cycles` uses recursive DFS | [`analysis.py:153`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/analysis.py#L153) | Deep graphs can hit Python's recursion limit. Use iterative DFS with an explicit stack |
| Two separate AST caches (`ast_cache.pkl`, `ast_usage_cache.pkl`) | [`source.py:388`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/source.py#L388), [`source.py:652`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/source.py#L652) | Merge into one cache file to avoid double I/O |
| `cmd_tree` calls `ctx.get_installed()` even in lockfile mode | [`cli.py:231`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/cli.py#L231) | Guard with `if not ctx.from_lock` to avoid unnecessary `importlib.metadata` scan |
| `_normalize_name_local` in `analysis.py` duplicates `normalize_name` in `models.py` | [`analysis.py:253`](file:///c:/Users/aksha/OneDrive/Documents/Zero%20Dependency/pyxray/analysis.py#L253) | Import and reuse `normalize_name` from `models` |
