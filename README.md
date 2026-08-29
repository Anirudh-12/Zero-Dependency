# PyXRay

**Python Dependency Investigation Tool**

> Zero third-party runtime dependencies. Every answer is traceable to project metadata, installed distribution metadata, and Python AST.

```
python -m pyxray summary
python -m pyxray tree --depth 3
python -m pyxray why requests
python -m pyxray impact certifi
python -m pyxray audit
```

---

## Zero Dependency

```
Runtime dependencies:  0
Third-party packages:  0
Network requests:      0
pip installs:          0
```

`pyproject.toml` has `dependencies = []`. Verify it yourself:

```bash
# Proof — one command
python -c "
import tomllib, pathlib
data = tomllib.load(open('pyproject.toml','rb'))
deps = data.get('project',{}).get('dependencies',[])
print('Runtime deps:', deps)
assert deps == [], 'FAIL: dependencies not empty'
print('PASS: zero dependencies confirmed')
"
```

See `deps-proof.txt` for recorded output.

---

## What It Does

Python projects accumulate dependency graphs that are impossible to reason about manually. A project declaring 5 dependencies may install 70 packages. Nobody knows why half of them exist.

PyXRay answers the questions that matter:

| Question | Command |
|---|---|
| How big is my dependency graph? | `summary` |
| What does the full tree look like? | `tree` |
| Why is package X installed? | `why X` |
| What breaks if X disappears? | `impact X` |
| Are there circular dependencies? | `cycles` |
| Which packages have multiple versions? | `duplicates` |
| Which packages are most-depended-upon? | `hotspots` |
| What does my source code actually import? | `imports` |
| Do my declarations match my imports? | `audit` |
| Which packages are good candidates for removal? | `prune` |
| What's the longest dep chain? | `longest-chain` |
| Detailed graph metrics? | `stats` |

---

## How It Works

```
Your project
     ↓
pyproject.toml / requirements.txt
     ↓
uv.lock / poetry.lock (Offline Mode - Default)
 OR importlib.metadata (Active Env Mode - Fallback)
     ↓
BFS graph traversal
     ↓
Graph algorithms (DFS, BFS, DFS colouring)
     ↓
AST source scan
     ↓
Deterministic output
```

No network. No ML. No guessing.

---

## Installation / Run

**No installation required.** Clone and run:

```bash
git clone https://github.com/Anirudh-12/Zero-Dependency
cd Zero-Dependency/pyxray
python -m pyxray --help
```

Requires **Python 3.11+** (for `tomllib`). Works on Python 3.12 and 3.13.

Run against your project:

```bash
python -m pyxray summary                    # summary of current directory
python -m pyxray --root /path/to/project summary
python -m pyxray --root /path/to/project tree --depth 4
python -m pyxray --root /path/to/project why fastapi
python -m pyxray --root /path/to/project audit
```

---

## Commands

### `summary`
Project-level overview. Direct deps, transitive deps, depth, cycles, hotspots.

```
python -m pyxray summary
python -m pyxray summary --json
```

### `tree [--depth N]`
Full ASCII dependency tree with box-drawing characters. Already-shown nodes are marked `[already shown]`. Depth-limited nodes are marked `[depth limit]`.

```
python -m pyxray tree
python -m pyxray tree --depth 3
```

### `why PACKAGE`
Find all dependency paths that explain why a package is installed. Uses BFS from project roots to target.

```
python -m pyxray why typing-extensions
python -m pyxray why requests --max-paths 3
```

### `impact PACKAGE`
Which packages depend on PACKAGE, transitively? Uses reverse graph traversal.

```
python -m pyxray impact certifi
```

### `cycles`
Detect circular dependencies using DFS node-colouring. Reports each cycle once.

```
python -m pyxray cycles
```

### `duplicates`
Detect packages installed with multiple versions (common in complex environments).

```
python -m pyxray duplicates
```

### `hotspots [--top N]`
Packages sorted by in-degree (number of dependents). Useful for identifying high-risk packages.

```
python -m pyxray hotspots --top 20
```

### `stats`
Detailed graph metrics: total nodes/edges, max/avg depth, fan-in/fan-out, cycles, missing packages.

```
python -m pyxray stats
```

### `longest-chain`
Find the longest dependency path from any root. Uses topological sort + DP on DAGs, falls back to cycle-safe DFS when cycles exist.

```
python -m pyxray longest-chain
```

### `imports`
Scan project source files with `ast` and classify imports as stdlib, third-party, or unknown.

```
python -m pyxray imports
python -m pyxray imports --no-unknown
```

### `audit`
Compare declared dependencies with detected source imports. Identifies potentially unused declarations and potentially undeclared imports.

```
python -m pyxray audit
python -m pyxray audit --json
```

### `prune`
Find packages that are good candidates for removal or reimplementation. It flags dependencies that are "thin" (few transitive deps), "narrow" (imported in very few files), and "shallow" (very few symbols used).

```bash
python -m pyxray prune
python -m pyxray prune --thin 3 --narrow 3 --shallow 5
```

---

## Global Flags

```
--root DIR        Project root (default: current directory)
--no-color        Disable ANSI colour (also: NO_COLOR env var)
--json            Machine-readable JSON output
--quiet, -q       Suppress warnings
--version         Print version
```

All commands support `--json` for scripting.

---

## Limitations

**Be honest:** PyXRay has explicit limits you should know about.

### Environment scope
By default, PyXRay auto-detects `uv.lock` or `poetry.lock` files and reconstructs the dependency graph **entirely offline** without needing the packages installed. In this mode, it can analyze any environment.

However, if no lockfile is found (or if `--no-lock` is passed), PyXRay falls back to analyzing the **currently active Python environment**. In this fallback mode, it does not simulate other environments or platforms, and you must run it inside the virtualenv you actually use.

### Import name ↔ distribution name
Python import names are not always identical to distribution names:
- `import bs4` → distribution `beautifulsoup4`
- `import sklearn` → distribution `scikit-learn`
- `import cv2` → distribution `opencv-python`

PyXRay uses `top_level.txt` metadata and fallback heuristics to build this mapping. When it cannot confidently map an import, it reports it as "unknown" rather than guessing.

### Dynamic imports not detected
The following patterns are **not** detected by `audit`:

```python
importlib.import_module("requests")   # not detected
__import__("requests")                 # not detected
plugin_registry.load("foo")           # not detected
```

PyXRay reports "no static import detected" rather than "definitely unused".

### Requirement marker evaluation
Environment markers are evaluated for the **current environment** only. Cross-platform analysis is not supported.

### Optional/extras
`foo[security]` extras are parsed but extra-specific transitive deps are only followed when the package is already installed.

### Cycle count
Cycle detection uses DFS node-colouring. In highly cyclic graphs (e.g. setuptools dev deps), many variants of the same cycle root may be reported. They are real edges in the metadata graph.

### Slower than pip
PyXRay's graph construction is O(n) over installed packages and allocates Python objects for each. On large environments (500+ packages), initial graph build may take 1-3 seconds. By design: correct and clear, not hyper-optimised.

---

## Architecture

```
pyxray/
  models.py       — Package, DependencyGraph, Requirement, SourceImport, AnalysisResult
  requirements.py — PEP 508 parser + environment marker evaluator
  metadata.py     — importlib.metadata discovery layer
  manifest.py     — pyproject.toml / requirements.txt reader
  graph.py        — BFS graph builder
  analysis.py     — Graph algorithms (BFS, DFS, cycles, depths, hotspots)
  source.py       — AST import extractor + import→distribution mapper
  output.py       — ANSI terminal output (no rich/colorama)
  cli.py          — argparse CLI + command dispatch
```

---

## Testing

```bash
python -m unittest discover -s tests -v
```

65 tests. Standard library `unittest` only. Synthetic package graphs — no real packages required.

---

## Track

**Track A — Developer Tools & CLI**

Bonus challenges targeted:
- **Package Killer (+3):** `networkx`, `pipdeptree`, `packaging`, `rich`, `colorama`, `click`
- **STDLIB Log (+3):** See `STDLIB.md`
- **Reproducible Build:** See Reproducible Build Proof below

---

## Dependency Proof

```bash
python -c "
import tomllib
data = tomllib.load(open('pyproject.toml','rb'))
deps = data['project']['dependencies']
print('dependencies:', deps)
"
# Output: dependencies: []
```

See `deps-proof.txt` for timestamped proof.

---

## Reproducible Build Proof

We've achieved byte-identical builds! By enforcing a fixed `SOURCE_DATE_EPOCH`, `uv build` deterministicly generates the exact same artifact on every run.

```bash
# Build 1
$env:SOURCE_DATE_EPOCH = "1704067200"
uv build
$hash1 = (Get-FileHash -Algorithm SHA256 dist/zero_dependency-0.1.0-py3-none-any.whl).Hash

# Delete and build again
rm dist/zero_dependency-0.1.0-py3-none-any.whl
uv build
$hash2 = (Get-FileHash -Algorithm SHA256 dist/zero_dependency-0.1.0-py3-none-any.whl).Hash
```

**Byte-Identical Hashes:**
- Build 1 SHA256: `F6784650B4F5EAFA8B23A5C334AF20DB1411E7B0430D2AD1D17693E4FFC5E970`
- Build 2 SHA256: `F6784650B4F5EAFA8B23A5C334AF20DB1411E7B0430D2AD1D17693E4FFC5E970`

**Result:** `Match!`
