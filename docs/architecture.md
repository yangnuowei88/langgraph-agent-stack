# Architecture: Platform Kernel

## Overview

The platform kernel is a thin abstraction layer that sits above the existing LangGraph agent infrastructure. Its purpose is to make multi-agent pipelines deployable as self-contained units called **domain packs**, each with a stable identity, a uniform runtime interface, and explicit registry membership.

Before the platform kernel, the Research + Analysis pipeline was implemented directly in `core/graph.py` as `MultiAgentGraph`. Adding a second pipeline would have required duplicating that pattern with no standard contract between implementations. The platform kernel defines that contract once so that future domain packs can be built, registered, and swapped without touching the API layer.

## Sprint 1 target vs what shipped

**Original Sprint 1 goal** was: `BaseDomainPack`, static explicit registration in `pack_kernel/__init__.py`, `PackRegistry` with `register` / `get` / `list_packs`, `ResearchAnalysisPack` owning the graph, `core/graph.py` as alias, `DEFAULT_PACK_ID`, and contract tests.

**Additionally implemented in code** (same release line, not a separate doc sprint): **multiple versions per `pack_id`** with **traffic-split weights**, **`get_schemas`** / **`list_packs_with_metadata`** for discovery, **class-level `version`** and **Pydantic `input_schema` / `output_schema`** on packs, **`budget_usd`** on `BaseDomainPack`, and **HTTP routes** for listing packs, versions, and updating weights (`api/main.py`). The registry remains **Approach B** (explicit registration only; no filesystem or entry-point discovery).

## Directory Structure

```
pack_kernel/
  __init__.py           # Imports and registers all built-in packs at package import time
  base_pack.py          # BaseDomainPack ABC — schemas, optional version, budget_usd
  registry.py           # PackRegistry — explicit registry + PackVersion entries

domain_packs/
  __init__.py
  research_analysis/
    __init__.py
    pack.py             # ResearchAnalysisPack — graph + BaseDomainPack implementation
    schemas.py          # Typed input/output models for this pack (optional pattern)

core/
  config.py             # Includes DEFAULT_PACK_ID, pack budgets, etc.
  graph.py              # Backward-compat alias: MultiAgentGraph = ResearchAnalysisPack
```

## Core Concepts

### BaseDomainPack

`BaseDomainPack` (in `pack_kernel/base_pack.py`) is an abstract base class that defines the runtime contract for all domain packs. Every concrete pack must:

- Declare **class-level metadata**: `pack_id`, `name`, `description`.
- Optionally declare **`version`** (defaults to `"1.0"` — used when multiple implementations share the same `pack_id`).
- Optionally override **`input_schema`** / **`output_schema`** (`ClassVar[type[BaseModel]]`) for API discovery and validation on pack routes.
- Implement three **abstract methods**: `run(query)`, `arun(query)`, and `stream_events(query)`.
- Accept constructor args: `run_id`, `llm`, `checkpointer`, and optional **`budget_usd`** (per-agent ceiling; see docstring in `base_pack.py`).

The optional `close()` method is a lifecycle hook for releasing resources such as thread pool executors. It is called automatically when the pack is used as a context manager.

### PackRegistry

`PackRegistry` lives in `pack_kernel/registry.py`. Registration is **explicit** in `pack_kernel/__init__.py` — there is **no** auto-discovery or filesystem scanning.

Internally, each `pack_id` maps to a **list of `PackVersion`** entries (`dataclass` in `registry.py`): each entry holds a **`version`** string, the **`pack_cls`**, and a **`weight`** used when more than one version exists and no explicit version is requested.

| Symbol / method | Description |
|-----------------|-------------|
| `PackVersion` | Dataclass: `version`, `pack_cls`, `weight` (≥ 0). |
| `register(pack_cls)` | Registers the class under `pack_cls.pack_id`. Reads optional `pack_cls.version` (default `"1.0"`). Replaces the entry for the same `(pack_id, version)` with a warning; appends if the version is new. Validates non-empty `pack_id`, `name`, and `description`. |
| `get(pack_id, version=None)` | Returns `type[BaseDomainPack]`. If **`version`** is set, returns that exact version’s class. If **`version`** is `None` and only one version exists, returns that class. If multiple versions exist and **`version`** is `None`, selects one via **weighted random choice** (`random.choices`) using each entry’s **`weight`**. Raises **`KeyError`** if `pack_id` or version is unknown, or if all weights are zero. |
| `set_weights(pack_id, weights)` | Updates **`weight`** for named versions (`dict[version_str, float]`). Versions omitted are unchanged. Raises **`KeyError`** / **`ValueError`** on invalid input. |
| `list_packs()` | Sorted list of registered **`pack_id`** strings. |
| `get_schemas(pack_id)` | Returns `(input_schema, output_schema)` Pydantic model classes; uses `get(pack_id)` to resolve the class. |
| `list_packs_with_metadata()` | List of dicts: `pack_id`, `name`, `description`, `input_schema`, `output_schema` as **JSON Schema** dicts (`model_json_schema()`). |
| `_get_versions(pack_id)` | Returns the list of **`PackVersion`** for a `pack_id`. Intended for callers that need full version metadata (e.g. HTTP handlers). Leading underscore: treat as **internal** unless you know you need it. |
| `_reset()` | Clears the registry — **tests only**. |

### Domain Packs

A domain pack is a self-contained implementation of `BaseDomainPack`. It owns its LangGraph graph, its agents, and its wire/schema surface.

Built-in packs registered in `pack_kernel/__init__.py`:

| `pack_id` | Class | Role |
|-----------|--------|------|
| `research_analysis` | `ResearchAnalysisPack` | Research → Analysis (default; former `MultiAgentGraph`) |
| `research_only` | `ResearchOnlyPack` | Research phase only — second pack illustrating multi-pack registration |

`ResearchAnalysisPack` optionally accepts a `connector=` (`BaseConnector`) to merge external retrieval snippets into the research phase. Enable via `CONNECTOR_ENABLED=true` and `CONNECTOR_ID` (default `example_memory`) — the API injects the connector at startup; see `connectors/README.md` and `core/connectors.py`.

## How to Add a New Domain Pack

**Step 1 — Create the pack module.**

Create `domain_packs/my_pack/pack.py` and implement `BaseDomainPack` (see `domain_packs/research_analysis/` for a full example including optional `schemas.py`).

**Step 2 — Register the pack.**

Open `pack_kernel/__init__.py` and add:

```python
from domain_packs.my_pack.pack import MyPack
PackRegistry.register(MyPack)
```

**Step 3 — Verify registration.**

```python
import pack_kernel  # noqa: F401 — ensure kernel package is importable
from pack_kernel.registry import PackRegistry

assert "my_pack" in PackRegistry.list_packs()
```

**Step 4 — Activate the pack.**

Set `DEFAULT_PACK_ID=my_pack` in your `.env` (or deployment env) before starting the API server. The FastAPI lifespan resolves `PackRegistry.get(settings.default_pack_id)` at startup.

**Step 5 — Add tests.**

Write unit tests in `tests/` that mock the LLM and checkpointer. Use `PackRegistry._reset()` in a fixture to isolate registry state between tests when needed.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_PACK_ID` | `research_analysis` | Pack used for legacy routes and as the default class when resolving `_active_pack_cls` at startup. Must match a registered `pack_id`. |

The API reads this during the FastAPI lifespan. If the id is not registered, startup fails with a clear error.

## Backward Compatibility

`core/graph.py` keeps a module-level alias:

```python
MultiAgentGraph = ResearchAnalysisPack
```

Existing imports `from core.graph import MultiAgentGraph` remain valid. The FastAPI app also imports `MultiAgentGraph` for **test patching** and combines it with **`PackRegistry.get(settings.default_pack_id)`** (`_active_pack_cls`) when executing `/run` and `/run/stream`, so the default pipeline class matches the configured pack while mocks can still target `api.main.MultiAgentGraph`.

Per-pack routes under `/packs/{pack_id}/...` use the registry and pack schemas directly.

**Legacy vs default pack:** `DEFAULT_PACK_ID` selects `_active_pack_cls` at startup. `MultiAgentGraph` in `core/graph.py` always aliases `ResearchAnalysisPack`. If you point `DEFAULT_PACK_ID` at another pack, legacy `/run` uses `_legacy_pipeline_pack_cls()` (registry class unless tests patch `api.main.MultiAgentGraph`). Prefer `/packs/{pack_id}/run` when the target pack is not `research_analysis`.

## Sprint 3 (delivered)

- **Connectors:** `http` and `rag` ids in `core/connectors.py`; `RagConnector` uses `get_vectorstore()` when `RAG_ENABLED=true`.
- **Control plane:** `PolicyRegistry` + `control_plane/enforce.py` applied in `api/main.py` (query limits, budget, stream timeout).
- **Sticky sessions:** Redis and Postgres run-history backends implement `get_pack_version_for_session` (session + `pack_id` index).

## What Is Not Here Yet (later work)

Capabilities **not** implemented as of this documentation:

- **Dynamic pack loading** — loading packs from arbitrary paths or third-party packages without editing `pack_kernel/__init__.py`.
- **Full control plane** — no cluster-wide “activate pack for all tenants” separate from process config; **read-only discovery** and **weight adjustment** exist via HTTP for registered packs.
- **Inter-pack connectors** — no standard mechanism for one pack to consume another pack’s output as a first-class API.
- **Hot reload** — no reloading pack code without process restart.
