# PyXRay 🔍

**The Zero-Dependency Python Dependency Investigation Tool**

![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

> Zero third-party runtime dependencies. Every answer is traceable to project metadata, installed distribution metadata, and Python AST.

Python projects accumulate dependency graphs that are impossible to reason about manually. A project declaring 5 dependencies may install 70 packages. Nobody knows why half of them exist. PyXRay answers the questions that matter without muddying your environment with more dependencies.

---

## 🏆 Hackathon Context

**Track A — Developer Tools & CLI**

We successfully targeted and achieved the following bonus challenges:
- **Package Killer (+3):** Replaced `networkx`, `pipdeptree`, `packaging`, `rich`, `colorama`, and `click` with pure standard library equivalents.
- **STDLIB Log (+3):** See `STDLIB.md` for a detailed log of standard library usage.
- **Reproducible Build:** Achieved byte-identical builds. See the *Reproducible Build Proof* section below.
- **Zero Dependencies:** Strictly 0 runtime dependencies. See the *Dependency Proof* section below.

---

## 🚀 Installation & Quick Start

**No installation required!** PyXRay works entirely offline out-of-the-box. 
Requires **Python 3.11+** (for `tomllib`). Works flawlessly on Python 3.12 and 3.13.

```bash
git clone https://github.com/Anirudh-12/Zero-Dependency
cd Zero-Dependency
```

Run PyXRay against any project (defaults to current directory):
```bash
python -m pyxray summary
python -m pyxray tree --depth 3
python -m pyxray why requests
python -m pyxray impact certifi
python -m pyxray audit
```

### Developer Setup
If you want to run the test suite (101 tests) or package the project:
```bash
make test   # Runs: uv run python -m unittest discover tests
make build  # Runs: uv build
```

---

## 🛠️ Features & Commands

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

*(All commands support `--json` for scripting and pipeline integration, and `--root DIR` to target specific projects).*

### Command Details

* **`summary`**: Project-level overview. Direct deps, transitive deps, depth, cycles, hotspots.
* **`tree [--depth N]`**: Full ASCII dependency tree with box-drawing characters. 
* **`why PACKAGE`**: Find all dependency paths that explain why a package is installed. Uses BFS from project roots to target.
* **`impact PACKAGE`**: Which packages depend on PACKAGE, transitively? Uses reverse graph traversal.
* **`cycles`**: Detect circular dependencies using DFS node-colouring. Reports each cycle once.
* **`duplicates`**: Detect packages installed with multiple versions (common in complex environments).
* **`hotspots [--top N]`**: Packages sorted by in-degree (number of dependents). Useful for identifying high-risk packages.
* **`stats`**: Detailed graph metrics: total nodes/edges, max/avg depth, fan-in/fan-out, cycles, missing packages.
* **`longest-chain`**: Find the longest dependency path from any root. Uses topological sort + DP on DAGs, falls back to cycle-safe DFS.
* **`imports [--no-unknown]`**: Scan project source files with `ast` and classify imports as stdlib, third-party, or unknown.
* **`audit`**: Compare declared dependencies with detected source imports. Identifies potentially unused declarations and undeclared imports.
* **`prune [--thin N] [--narrow N] [--shallow N]`**: Find packages that are good candidates for removal or reimplementation.

---

## 🧠 How It Works & Architecture

```text
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
*No network. No ML. No guessing.*

### Architecture
* `models.py` — Package, DependencyGraph, Requirement, SourceImport, AnalysisResult
* `requirements.py` — PEP 508 parser + environment marker evaluator
* `metadata.py` — `importlib.metadata` discovery layer
* `manifest.py` — `pyproject.toml` / `requirements.txt` reader
* `graph.py` — BFS graph builder
* `analysis.py` — Graph algorithms (BFS, DFS, cycles, depths, hotspots)
* `source.py` — AST import extractor + import→distribution mapper
* `output.py` — ANSI terminal output (no rich/colorama)
* `cli.py` — `argparse` CLI + command dispatch

---

## ⚠️ Limitations

**Be honest:** PyXRay has explicit limits you should know about.

* **Environment scope**: By default, PyXRay auto-detects `uv.lock` or `poetry.lock` files and reconstructs the dependency graph **entirely offline**. If no lockfile is found, it falls back to analyzing the **currently active Python environment**.
* **Import name ↔ distribution name**: Python import names are not always identical to distribution names (e.g., `import cv2` → `opencv-python`). PyXRay uses `top_level.txt` and heuristics to build this mapping.
* **Dynamic imports**: `importlib.import_module("requests")` and `__import__("requests")` are not detected by `audit`.
* **Requirement markers**: Environment markers are evaluated for the **current environment** only.
* **Performance**: PyXRay's graph construction is O(n) over installed packages. On large environments (500+ packages), initial graph build may take 1-3 seconds. By design: correct and clear, not hyper-optimised.

---

## 🛡️ Proofs

### Dependency Proof

```bash
python -c "
import tomllib
data = tomllib.load(open('pyproject.toml','rb'))
deps = data['project']['dependencies']
print('dependencies:', deps)
"
# Output: dependencies: []
```
*See `deps-proof.txt` for timestamped proof.*

### Reproducible Build Proof

We've achieved byte-identical builds! By enforcing a fixed `SOURCE_DATE_EPOCH`, `uv build` deterministically generates the exact same artifact on every run.

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
