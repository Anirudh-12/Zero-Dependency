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

<details>
<summary><b>Example Output (fastapi: `summary`)</b></summary>

```text
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
```

</details>

* **`tree [--depth N]`**: Full ASCII dependency tree with box-drawing characters.

<details>
<summary><b>Example Output (fastapi: `tree --depth 2`)</b></summary>

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

  typing-extensions 4.16.0

  typing-inspection 0.4.2
  └── typing-extensions 4.16.0
```

</details>

* **`why PACKAGE`**: Find all dependency paths that explain why a package is installed. Uses BFS from project roots to target.

<details>
<summary><b>Example Output (fastapi: `why pydantic`)</b></summary>

```text
Why is 'pydantic' installed? (2.13.4)
──────────────────────────────────────────────────

  Path 1
    pydantic (2.13.4)
```

</details>

* **`impact PACKAGE`**: Which packages depend on PACKAGE, transitively? Uses reverse graph traversal.

<details>
<summary><b>Example Output (fastapi: `impact typing-extensions`)</b></summary>

```text
Impact of 'typing-extensions' (4.16.0)
──────────────────────────────────────────────────
  If 'typing-extensions' disappeared, 67 package(s) would be affected:

          a2wsgi 1.10.10
          anthropic 0.109.0
          anyio 4.12.1
          authlib 1.7.2
          black 26.5.1
          cross-web 0.7.0
          cryptography 50.0.0
          exceptiongroup 1.3.1
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
          mkdocstrings-python 2.0.3
          mypy 2.3.0
          openai 2.52.0
          opentelemetry-api 1.39.1
          opentelemetry-exporter-otlp-proto-http 1.39.1
          opentelemetry-instrumentation 0.60b1
          opentelemetry-instrumentation-httpx 0.60b1
          opentelemetry-sdk 1.39.1
          opentelemetry-semantic-conventions 0.60b1
          playwright 1.61.0
          py-key-value-aio 0.4.4
    ⊕ root  pydantic 2.13.4
          pydantic-ai 2.18.0
          pydantic-ai-slim 2.18.0
          pydantic-core 2.46.4
          pydantic-evals 2.18.0
          pydantic-extra-types 2.11.0
          pydantic-graph 2.18.0
          pydantic-settings 2.14.2
          pyee 13.0.0
... (truncated for brevity)
```

</details>

* **`cycles`**: Detect circular dependencies using DFS node-colouring. Reports each cycle once.

<details>
<summary><b>Example Output (fastapi: `cycles`)</b></summary>

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

* **`duplicates`**: Detect packages installed with multiple versions (common in complex environments).

<details>
<summary><b>Example Output (fastapi: `duplicates`)</b></summary>

```text
Duplicate Package Versions
──────────────────────────────────────────────────
✓ No duplicate versions detected.
```

</details>

* **`hotspots [--top N]`**: Packages sorted by in-degree (number of dependents). Useful for identifying high-risk packages.

<details>
<summary><b>Example Output (fastapi: `hotspots --top 5`)</b></summary>

```text
Dependency Hotspots (top 5)
──────────────────────────────────────────────────
  Packages with the most reverse dependencies (in-degree).

  typing-extensions 4.16.0
  ████████████████████  37 dependents

  pydantic 2.13.4
  ███████░░░░░░░░░░░░░  14 dependents

  anyio 4.12.1
  █████░░░░░░░░░░░░░░░  11 dependents

  httpx 0.28.1
  █████░░░░░░░░░░░░░░░  10 dependents

  pyyaml 6.0.3
  ████░░░░░░░░░░░░░░░░  9 dependents
```

</details>

* **`stats`**: Detailed graph metrics: total nodes/edges, max/avg depth, fan-in/fan-out, cycles, missing packages.

<details>
<summary><b>Example Output (fastapi: `stats`)</b></summary>

```text
Graph Statistics — fastapi
──────────────────────────────────────────────────
  Packages (total)                 205           # nodes
  Direct dependencies              5             # root nodes
  Transitive dependencies          200           # non-root nodes
  Dependency edges                 403           # edges
  Leaf packages                    89            # no outgoing edges
  Missing packages                 0             # not installed

  Maximum depth                    4             # hops from a root
  Average depth                    1.63          # BFS from roots
  Maximum fan-out                  23            # direct deps of one package
  Maximum fan-in                   37            # dependents of one package

  Cycle count                      2             # strongly connected
  Largest subtree                  starlette (12 pkgs)  # from one root
  Most depended upon               typing-extensions (37 deps)  # highest in-degree
```

</details>

* **`longest-chain`**: Find the longest dependency path from any root. Uses topological sort + DP on DAGs, falls back to cycle-safe DFS.

<details>
<summary><b>Example Output (fastapi: `longest-chain`)</b></summary>

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

* **`imports [--no-unknown]`**: Scan project source files with `ast` and classify imports as stdlib, third-party, or unknown.

<details>
<summary><b>Example Output (fastapi: `imports --no-unknown`)</b></summary>

```text
Source Import Summary — fastapi
──────────────────────────────────────────────────
  Source roots              C:\Users\aksha\OneDrive\Documents\fastapi, C:\Users\aksha\OneDrive\Documents\fastapi\fastapi
  Total import statements   3362
  Third-party detected      30
  Standard library          44
  Unclassified              12


  Third-party imports detected:
    • a2wsgi
    • annotated-doc
    • anyio
    • dirty-equals
    • email-validator
    • fastapi
    • fastapi-cli
    • flask
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
    • pytest
    • python-multipart
    • rich
    • ruff
    • sqlalchemy
    • sqlmodel
    • starlette
    • typer
    • typing-extensions
    • typing-inspection
    • uvicorn
```

</details>

* **`audit`**: Compare declared dependencies with detected source imports. Identifies potentially unused declarations and undeclared imports.

<details>
<summary><b>Example Output (fastapi: `audit`)</b></summary>

```text
Dependency Audit — fastapi
──────────────────────────────────────────────────
  Declared dependencies               5
  Third-party imports detected        30
  Potentially unused declarations     0
  Potentially undeclared imports      25

  ✗  Imported but not in declared dependencies  (may be a transitive dep being imported directly)
    • a2wsgi
        docs_src\wsgi\tutorial001_py310.py:1
    • anyio
        docs_src\custom_response\tutorial007_py310.py:1
        fastapi\concurrency.py:6
        fastapi\concurrency.py:7
        fastapi\routing.py:42
        fastapi\routing.py:44
    • dirty-equals
        tests\test_filter_pydantic_sub_model_pv2.py:2
        tests\test_multi_body_errors.py:3
        tests\test_nested_annotated_in_sequence.py:3
        tests\test_pydanticv2_dataclasses_uuid_stringified_annotations.py:6
        tests\test_request_param_model_by_alias.py:1
    • email-validator
        fastapi\openapi\models.py:17
    • fastapi
        docs_src\additional_responses\tutorial001_py310.py:1
        docs_src\additional_responses\tutorial001_py310.py:2
        docs_src\additional_responses\tutorial002_py310.py:1
        docs_src\additional_responses\tutorial002_py310.py:2
        docs_src\additional_responses\tutorial003_py310.py:1
    • fastapi-cli
        fastapi\cli.py:2
    • flask
        docs_src\wsgi\tutorial001_py310.py:3
    • httpx
        docs_src\async_tests\app_a_py310\test_main.py:2
        scripts\notify_translations.py:8
        scripts\sponsors.py:8
        scripts\playwright\cookie_param_models\image01.py:4
        scripts\playwright\header_param_models\image01.py:4
    • inline-snapshot
        tests\test_additional_properties.py:3
        tests\test_additional_properties_bool.py:3
        tests\test_additional_responses_custom_model_in_callback.py:3
        tests\test_additional_responses_custom_validationerror.py:4
        tests\test_additional_responses_default_validationerror.py:3
    • jinja2
        scripts\docs.py:15
    • markupsafe
        docs_src\wsgi\tutorial001_py310.py:4
... (truncated for brevity)
```

</details>

* **`prune [--thin N] [--narrow N] [--shallow N]`**: Find packages that are good candidates for removal or reimplementation.

<details>
<summary><b>Example Output (fastapi: `prune --thin 3 --narrow 3 --shallow 5`)</b></summary>

```text
Prune Candidates — fastapi
──────────────────────────────────────────────────
  ✎ typing-inspection (0.4.2)  —  REIMPLEMENT
      Confidence: MEDIUM
      Only 1 transitive dep(s); used in 1 file(s); only 1 symbol(s)
      imported: is_typealiastype

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
