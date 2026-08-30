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
If you want to run the test suite (125 tests) or package the project:
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
| Show Python environment and project info? | `env` |
| CI pass/fail gate (cycles/depth/missing)? | `check` |
| Show license inventory across all packages? | `license` |
| Export dependency graph as Mermaid/Graphviz? | `export` |
| Diff two lock files? | `compare` |
| Find unused extras? | `unused-extras` |
| Check for outdated packages vs PyPI? | `outdated` |
| Check for CVEs via OSV.dev? | `security` |

*(All commands support `--json` for scripting and pipeline integration, and `--root DIR` to target specific projects).*

### Command Details

All commands support `--json` for scripting and pipeline integration, and `--root DIR` to target specific projects.

* **`summary ===`**: Provides detailed output for summary ===.

<details>
<summary><b>Example Output (fastapi: `summary ===`)</b></summary>

```text
____       __  ____             
 |  _ \ _   _\ \/ /  _ \ __ _ _   _
 | |_) | | | |\  /| |_) / _` | | | |
 |  __/| |_| |/  \|  _ < (_| | |_| |
 |_|    \__, /_/\_\_| \_\__,_|\__, |
        |___/                  |___/ 
  Python Dependency Investigation Tool


Project: fastapi
──────────────────────────────────────────────────
  Direct dependencies            5
  Transitive dependencies        200
  Total packages                 205

  Dependency edges               403
  Leaf packages                  89
  Maximum depth                  4
  Average depth                  1.63
  Cycles detected                2
  Missing packages               0

  Largest subtree                starlette → 12 packages
  Most depended upon             typing-extensions → 37 dependents

  Health                         D  (2 cycle(s))
```

</details>

* **`tree ===`**: Provides detailed output for tree ===.

<details>
<summary><b>Example Output (fastapi: `tree ===`)</b></summary>

```text
Dependency Tree — fastapi
──────────────────────────────────────────────────
  annotated-doc 0.0.4

  pydantic 2.13.4
  ├── annotated-types 0.7.0
  ├── email-validator 2.3.0
  │   ├── dnspython 2.8.0
  │   └── idna 3.18
  ├── pydantic-core 2.46.4
  │   └── typing-extensions 4.16.0
  ├── typing-extensions 4.16.0 [already shown]
  └── typing-inspection 0.4.2
      └── typing-extensions 4.16.0 [already shown]

  starlette 1.3.1
  ├── anyio 4.12.1
  │   ├── exceptiongroup 1.3.1
  │   │   └── typing-extensions 4.16.0 [depth limit]
  │   ├── idna 3.18
  │   ├── trio 0.32.0
  │   │   ├── attrs 25.4.0 [depth limit]
  │   │   ├── cffi 2.0.0 [depth limit]
  │   │   ├── exceptiongroup 1.3.1 [already shown]
  │   │   ├── idna 3.18 [already shown]
  │   │   ├── outcome 1.3.0.post0 [depth limit]
  │   │   ├── sniffio 1.3.1 [depth limit]
  │   │   └── sortedcontainers 2.4.0 [depth limit]
  │   └── typing-extensions 4.16.0
  └── typing-extensions 4.16.0 [already shown]
...
```

</details>

* **`why ===`**: Provides detailed output for why ===.

<details>
<summary><b>Example Output (fastapi: `why ===`)</b></summary>

```text
Why is 'requests' installed? (2.33.0)
──────────────────────────────────────────────────
  No path found from project roots to 'requests'.
  It may be installed but not reachable from declared dependencies.
```

</details>

* **`impact ===`**: Provides detailed output for impact ===.

<details>
<summary><b>Example Output (fastapi: `impact ===`)</b></summary>

```text
Impact of 'typing-extensions' (4.16.0)
──────────────────────────────────────────────────
  If 'typing-extensions' disappeared, 67 package(s) would be affected:

  Direct dependents                      ── 65 package(s)
          a2wsgi 1.10.10
          anthropic 0.109.0
          anyio 4.12.1
          authlib 1.7.2
          black 26.5.1
          cross-web 0.7.0
          cryptography 50.0.0
          fastapi ?
          fastapi-cli 0.0.32
          fastapi-cloud-cli 0.11.0
          fastmcp-slim 3.3.1
          genai-prices 0.0.71
          google-auth 2.49.2
          google-genai 1.73.1
          griffe-typingdoc 0.3.1
          httpx 0.28.1
          httpx2 2.9.1
          inline-snapshot 0.35.2
          joserfc 1.6.8
          jsonschema 4.26.0
          jsonschema-specifications 2025.9.1
          keyring 25.7.0
          logfire 4.22.0
          mcp 1.26.0
          mkdocstrings 1.0.4
...
```

</details>

* **`cycles ===`**: Provides detailed output for cycles ===.

<details>
<summary><b>Example Output (fastapi: `cycles ===`)</b></summary>

```text
Circular Dependencies
──────────────────────────────────────────────────
  2 cycle(s) detected:

  Cycle 1
    mkdocstrings
      └── mkdocstrings-python
        └── mkdocstrings

  Cycle 2
    pydantic-ai-slim
      └── pydantic-evals
        └── pydantic-ai-slim
```

</details>

* **`duplicates ===`**: Provides detailed output for duplicates ===.

<details>
<summary><b>Example Output (fastapi: `duplicates ===`)</b></summary>

```text
Duplicate Package Versions
──────────────────────────────────────────────────
✓ No duplicate versions detected.
```

</details>

* **`hotspots ===`**: Provides detailed output for hotspots ===.

<details>
<summary><b>Example Output (fastapi: `hotspots ===`)</b></summary>

```text
Dependency Hotspots (top 20)
──────────────────────────────────────────────────
  Packages with the most reverse dependencies (in-degree).  Risk = dependents × (1 + subtree_size)

  typing-extensions 4.16.0
  ████████████████████  37 dependents  subtree: 0  risk: 37

  pydantic 2.13.4
  ███████░░░░░░░░░░░░░  14 dependents  subtree: 7  risk: 112

  anyio 4.12.1
  █████░░░░░░░░░░░░░░░  11 dependents  subtree: 10  risk: 121

  httpx 0.28.1
  █████░░░░░░░░░░░░░░░  10 dependents  subtree: 14  risk: 150

  pyyaml 6.0.3
  ████░░░░░░░░░░░░░░░░  9 dependents  subtree: 0  risk: 9

  tomli 2.4.0
  ████░░░░░░░░░░░░░░░░  8 dependents  subtree: 0  risk: 8

  rich 14.3.2
  ████░░░░░░░░░░░░░░░░  8 dependents  subtree: 3  risk: 32

  markdown 3.10.1
  ███░░░░░░░░░░░░░░░░░  7 dependents  subtree: 0  risk: 7

  opentelemetry-api 1.39.1
  ███░░░░░░░░░░░░░░░░░  7 dependents  subtree: 3  risk: 28
...
```

</details>

* **`longest-chain ===`**: Provides detailed output for longest-chain ===.

<details>
<summary><b>Example Output (fastapi: `longest-chain ===`)</b></summary>

```text
Longest Dependency Chain
──────────────────────────────────────────────────

  Chain length: 5 packages

  starlette (1.3.1)
    └── anyio (4.12.1)
      └── trio (0.32.0)
        └── cffi (2.0.0)
          └── pycparser (3.0)
```

</details>

* **`imports ===`**: Provides detailed output for imports ===.

<details>
<summary><b>Example Output (fastapi: `imports ===`)</b></summary>

```text
Source Import Summary — fastapi
──────────────────────────────────────────────────
  Source roots              c:\Users\aksha\OneDrive\Documents\fastapi, c:\Users\aksha\OneDrive\Documents\fastapi\fastapi
  Total import statements   3362
  Third-party detected      36
  Standard library          44
  Unclassified              5


  Third-party imports detected:
    • a2wsgi
    • annotated-doc
    • anyio
    • dirty-equals
    • email-validator
    • fastapi
    • fastapi-cli
    • flask
    • gitpython
    • httpx
    • inline-snapshot
    • jinja2
    • markupsafe
    • playwright
    • pwdlib
    • pydantic
    • pydantic-ai
    • pydantic-core
    • pydantic-extra-types
    • pydantic-settings
...
```

</details>

* **`audit ===`**: Provides detailed output for audit ===.

<details>
<summary><b>Example Output (fastapi: `audit ===`)</b></summary>

```text
Dependency Audit — fastapi
──────────────────────────────────────────────────
  Declared dependencies               5
  Third-party imports detected        36
  Potentially unused declarations     0
  Potentially undeclared imports      31

  ✗  Imported but not in declared dependencies  (may be a transitive dep being imported directly)
```

</details>

* **`prune ===`**: Provides detailed output for prune ===.

<details>
<summary><b>Example Output (fastapi: `prune ===`)</b></summary>

```text
Prune Candidates — fastapi
──────────────────────────────────────────────────
  ✎ typing-inspection (0.4.2)  —  REIMPLEMENT
      Confidence: MEDIUM
      Only 1 transitive dep(s); used in 1 file(s); only 1 symbol(s)
      imported: is_typealiastype
      Suggestion: inspect.get_annotations() covers most use cases (Python 3.10+)

  ✓ annotated-doc (0.0.4)  —  KEEP
      Confidence: LOW
      0 transitive dep(s), used in 13 file(s), 1 symbol(s) — not a strong
      removal candidate

  ✓ pydantic (2.13.4)  —  KEEP
      Confidence: LOW
      7 transitive dep(s), used in 233 file(s), 39 symbol(s) — not a strong
      removal candidate

  ✓ starlette (1.3.1)  —  KEEP
      Confidence: LOW
      11 transitive dep(s), used in 44 file(s), 64 symbol(s) — not a strong
      removal candidate

  ✓ typing-extensions (4.16.0)  —  KEEP
      Confidence: LOW
      0 transitive dep(s), used in 8 file(s), 4 symbol(s) — not a strong
      removal candidate
```

</details>

* **`env ===`**: Provides detailed output for env ===.

<details>
<summary><b>Example Output (fastapi: `env ===`)</b></summary>

```text
Python Environment
──────────────────────────────────────────────────
  Python version         3.11.9  (CPython)
  Executable             C:\Users\aksha\OneDrive\Documents\fastapi\.venv\Scripts\python.exe
  Virtual env            C:\Users\aksha\OneDrive\Documents\fastapi\.venv
  Site-packages          C:\Users\aksha\OneDrive\Documents\fastapi\.venv\Lib\site-packages
  Platform               win32  (Windows-10-10.0.26200-SP0)
  Lock file              uv.lock
  Project root           C:\Users\aksha\OneDrive\Documents\fastapi
```

</details>

* **`check ===`**: Provides detailed output for check ===.

<details>
<summary><b>Example Output (fastapi: `check ===`)</b></summary>

```text
Dependency Health Check — fastapi
──────────────────────────────────────────────────
  ✗  cycles         2 cycle(s) detected
  ✓  missing        0 missing packages
  ✓  depth          4 (limit: 10)

  Result: FAIL  (1 check(s) failed)
```

</details>

* **`license ===`**: Provides detailed output for license ===.

<details>
<summary><b>Example Output (fastapi: `license ===`)</b></summary>

```text
License Inventory — fastapi
──────────────────────────────────────────────────
  205 packages analysed

  MIT                     104 packages  ██████████████████
  Apache-2.0               33 packages  █████░░░░░░░░░░░░░
  BSD                      22 packages  ███░░░░░░░░░░░░░░░
  BSD-3-Clause             18 packages  ███░░░░░░░░░░░░░░░
  ISC                       6 packages  █░░░░░░░░░░░░░░░░░
  BSD-2-Clause              3 packages  ░░░░░░░░░░░░░░░░░░
  Mozilla Public License 2.0 (MPL 2.0)    2 packages  ░░░░░░░░░░░░░░░░░░
  Python Software Foundation License    2 packages  ░░░░░░░░░░░░░░░░░░
  ISC License (ISCL)        2 packages  ░░░░░░░░░░░░░░░░░░
  LGPL-3.0-or-later         1 packages  ░░░░░░░░░░░░░░░░░░
  Apache-2.0 OR BSD-3-Clause    1 packages  ░░░░░░░░░░░░░░░░░░
  The Unlicense (Unlicense)    1 packages  ░░░░░░░░░░░░░░░░░░
  MIT AND Python-2.0        1 packages  ░░░░░░░░░░░░░░░░░░
  MIT-CMU                   1 packages  ░░░░░░░░░░░░░░░░░░
  3-Clause BSD License      1 packages  ░░░░░░░░░░░░░░░░░░
  GNU Library or Lesser General Public License (LGPL)    1 packages  ░░░░░░░░░░░░░░░░░░
  DFSG approved             1 packages  ░░░░░░░░░░░░░░░░░░
  Apache-2.0 AND CNRI-Python    1 packages  ░░░░░░░░░░░░░░░░░░
  Artistic License          1 packages  ░░░░░░░░░░░░░░░░░░
  MPL-2.0 AND MIT           1 packages  ░░░░░░░░░░░░░░░░░░
  MIT OR Apache-2.0         1 packages  ░░░░░░░░░░░░░░░░░░
  PSF-2.0                   1 packages  ░░░░░░░░░░░░░░░░░░
```

</details>

* **`export ===`**: Provides detailed output for export ===.

<details>
<summary><b>Example Output (fastapi: `export ===`)</b></summary>

```text
digraph dependencies {
    rankdir=TB;
    "pydantic" -> "annotated-types";
    "pydantic" -> "email-validator";
    "pydantic" -> "pydantic-core";
    "pydantic" -> "typing-extensions";
    "pydantic" -> "typing-inspection";
    "starlette" -> "anyio";
    "starlette" -> "typing-extensions";
    "typing-inspection" -> "typing-extensions";
    "email-validator" -> "dnspython";
    "email-validator" -> "idna";
    "pydantic-core" -> "typing-extensions";
    "anyio" -> "exceptiongroup";
    "anyio" -> "idna";
    "anyio" -> "trio";
    "anyio" -> "typing-extensions";
    "exceptiongroup" -> "typing-extensions";
    "trio" -> "attrs";
    "trio" -> "cffi";
    "trio" -> "exceptiongroup";
    "trio" -> "idna";
    "trio" -> "outcome";
    "trio" -> "sniffio";
    "trio" -> "sortedcontainers";
    "cffi" -> "pycparser";
    "outcome" -> "attrs";
}
```

</details>


---

## 🧠 Modular Architecture

PyXRay operates on a highly modular architecture while strictly adhering to standard library limits.

```text
Your project
     ↓
pyproject.toml / requirements.txt
     ↓
uv.lock / poetry.lock (Offline Mode - Default)
 OR importlib.metadata (Active Env Mode - Fallback)
 OR PyPI JSON API (--pypi flag for remote resolution)
     ↓
BFS graph traversal via collections.deque
     ↓
AST source code analysis (ast module)
     ↓
Commands loaded lazily via pyxray/commands/*.py
```

### Key Modules:
- **`commands/`**: Contains 20 separate commands (e.g., `license.py`, `security.py`, `summary.py`). These are lazy-loaded via `importlib` so PyXRay boots in milliseconds regardless of the number of commands.
- **`osv.py`**: Interacts with the Open Source Vulnerability API using `urllib.request`.
- **`pypi.py`**: Resolves uninstalled packages via the PyPI JSON API.
- **`graph.py`**: Builds directed acyclic dependency graphs in a single O(N) pass.
- **`source.py`**: Parses every source file via the `ast` module to extract precise imports.
- **`lockfile.py`**: Parses `pyproject.toml` and `uv.lock` safely using `tomllib`.

*No network (unless requested). No ML. No guessing.*

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
- Build 1 SHA256: `5E162E120F752B4C93A95928C491D5804440306DC5BBC94C1ABCF5494AA3C023`
- Build 2 SHA256: `5E162E120F752B4C93A95928C491D5804440306DC5BBC94C1ABCF5494AA3C023`

**Result:** `Match!`
