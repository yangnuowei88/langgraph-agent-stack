# Architecture: Platform Kernel

## Overview

The platform kernel is a thin abstraction layer that sits above the existing LangGraph agent infrastructure. Its purpose is to make multi-agent pipelines deployable as self-contained units called **domain packs**, each with a stable identity, a uniform runtime interface, and explicit registry membership.

Before the platform kernel, the Research + Analysis pipeline was implemented directly in `core/graph.py` as `MultiAgentGraph`. Adding a second pipeline would have required duplicating that pattern with no standard contract between implementations. The platform kernel defines that contract once so that future domain packs can be built, registered, and swapped without touching the API layer.

## Directory Structure

```
platform/
  __init__.py           # Imports and registers all built-in packs at package import time
  base_pack.py          # BaseDomainPack ABC — the interface every domain pack must satisfy
  registry.py           # PackRegistry — explicit, dict-based registry of available packs

domain_packs/
  __init__.py
  research_analysis/
    __init__.py
    pack.py             # ResearchAnalysisPack — the first domain pack, migrated from core/graph.py

core/
  config.py             # Unchanged except for the DEFAULT_PACK_ID setting addition
  graph.py              # Backward-compat alias: MultiAgentGraph = ResearchAnalysisPack
```

## Core Concepts

### BaseDomainPack

`BaseDomainPack` (in `platform/base_pack.py`) is an abstract base class that defines the runtime contract for all domain packs. Every concrete pack must:

- Declare three **class-level attributes**: `pack_id` (stable string identifier), `name` (human-readable label), and `description` (one sentence).
- Implement three **abstract methods**: `run(query)`, `arun(query)`, and `stream_events(query)`.
- Accept the same constructor signature: `(run_id=None, llm=None, checkpointer=None)`.

The optional `close()` method is a lifecycle hook for releasing resources such as thread pool executors. It is called automatically when the pack is used as a context manager.

```python
from platform.base_pack import BaseDomainPack
from collections.abc import AsyncGenerator
from typing import Any

class MyPack(BaseDomainPack):
    pack_id = "my_pack"
    name = "My Pack"
    description = "Does something useful."

    def run(self, query: str) -> Any:
        ...

    async def arun(self, query: str) -> Any:
        ...

    async def stream_events(self, query: str) -> AsyncGenerator[dict, None]:
        yield {"event": "done", "data": {}}
```

### PackRegistry

`PackRegistry` (in `platform/registry.py`) is a class-level dict. Packs are registered explicitly — there is no auto-discovery or filesystem scanning.

| Method | Description |
|---|---|
| `PackRegistry.register(pack_cls)` | Register a pack by its `pack_id`. Raises `ValueError` if `pack_id` is missing. |
| `PackRegistry.get(pack_id)` | Return the registered class. Raises `KeyError` with the list of available packs if not found. |
| `PackRegistry.list_packs()` | Return a sorted list of registered pack IDs. |
| `PackRegistry._reset()` | Clear the registry. For use in tests only. |

### Domain Packs

A domain pack is a self-contained implementation of `BaseDomainPack`. It owns its LangGraph graph, its agent instances, and its output schema. The first pack, `ResearchAnalysisPack`, implements the Research → Analysis pipeline that was previously in `core/graph.py`.

## How to Add a New Domain Pack

**Step 1 — Create the pack module.**

Create `domain_packs/my_pack/pack.py` and implement `BaseDomainPack`:

```python
# domain_packs/my_pack/pack.py
from platform.base_pack import BaseDomainPack
from collections.abc import AsyncGenerator
from typing import Any

class MyPack(BaseDomainPack):
    pack_id = "my_pack"
    name = "My Pack"
    description = "A one-sentence description of what this pack does."

    def run(self, query: str) -> Any:
        # Synchronous execution
        ...

    async def arun(self, query: str) -> Any:
        # Async execution — offload blocking calls to a thread pool
        ...

    async def stream_events(self, query: str) -> AsyncGenerator[dict, None]:
        # Yield dicts with at least {"event": str, "data": dict}
        yield {"event": "pipeline_completed", "data": {...}}
```

**Step 2 — Register the pack.**

Open `platform/__init__.py` and add two lines:

```python
from domain_packs.my_pack.pack import MyPack
PackRegistry.register(MyPack)
```

**Step 3 — Verify registration.**

```python
import platform  # triggers __init__.py
from platform.registry import PackRegistry

assert "my_pack" in PackRegistry.list_packs()
```

**Step 4 — Activate the pack.**

Set `DEFAULT_PACK_ID=my_pack` in your `.env` file (or the deployment environment) before starting the API server. The FastAPI lifespan resolves `PackRegistry.get(default_pack_id)` at startup.

**Step 5 — Add tests.**

Write unit tests in `tests/` that mock the LLM and checkpointer. Use `PackRegistry._reset()` in a fixture to isolate registry state between test runs.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_PACK_ID` | `research_analysis` | The pack resolved by the API at startup. Must match a registered `pack_id`. |

The API reads this value once during the FastAPI lifespan via `get_settings()`. If the specified `pack_id` is not registered, `PackRegistry.get()` raises `KeyError` and startup fails with a clear error message listing available packs.

## Backward Compatibility

`core/graph.py` retains a module-level alias:

```python
MultiAgentGraph = ResearchAnalysisPack
```

This means all existing call sites continue to work without modification:

```python
from core.graph import MultiAgentGraph  # still valid

with MultiAgentGraph(run_id="abc", llm=llm, checkpointer=cp) as g:
    report = g.run(query)
```

All tests in `tests/` pass without changes. All endpoints (`/run`, `/run/stream`, `/research`, `/health`) are unchanged. The `examples/` directory is untouched.

## What Is Not Here Yet (Sprint 2+)

The following capabilities are explicitly out of scope for this sprint and will be addressed later:

- **Dynamic pack loading** — loading packs from filesystem paths or installed packages at runtime without modifying `platform/__init__.py`.
- **Control plane API** — endpoints for listing available packs, switching the active pack at runtime, or inspecting pack metadata.
- **Inter-pack connectors** — a standard mechanism for one pack to consume the output of another.
- **Pack versioning** — versioned `pack_id` strings and compatibility matrices.
- **Hot reload** — reloading a pack's implementation without restarting the process.
