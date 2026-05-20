# Connectors (foundation)

This package defines a **small, explicit contract** for code that pulls data from outside the LLM—SQL, REST APIs, object stores, search engines, etc. It is **not** a plugin system and **not** wired into the FastAPI app or `PackRegistry` by default.

## What a connector is

- An **adapter** with a stable id (`connector_id`) and a single async entry point: `fetch(ConnectorRequest) -> ConnectorResult`.
- A place to encapsulate **transport and backend specifics** (connection strings, auth, query translation) so domain packs stay focused on orchestration.
- **Optional**: packs can ignore connectors entirely.

## What it is not

- **Not** a LangGraph node or tool replacement — use LangChain tools inside agents when you need LLM-facing tools; use connectors when you need a thin retrieval layer the pack calls directly.
- **Not** auto-discovered or registered globally — no entry points, no scanning; packs instantiate or inject what they need.
- **Not** production integrations — this repository ships only `BaseConnector` and an example; real drivers belong in future PRs.

## How domain packs should use connectors

1. Accept optional `BaseConnector` instances (or a factory) in the pack constructor **when** you add retrieval features.
2. Call `await connector.fetch(ConnectorRequest(query=..., limit=..., filters=...))` from a graph node or helper.
3. Map `ConnectorResult.records` into prompts, citations, or `ResearchResult` fields — the connector does **not** format final user-facing text.

Keep imports **local** to the pack module to avoid loading unused backends at API startup.

### Wired in this repository

`ResearchAnalysisPack` (`domain_packs/research_analysis/pack.py`) accepts an optional `connector=` constructor argument. During the research graph node, it calls `fetch()` and merges records into `ResearchResult.findings` and `metadata["connector"]`.

**API (production):** set in `.env`:

```env
CONNECTOR_ENABLED=true
CONNECTOR_ID=example_memory
```

The FastAPI lifespan resolves the connector via `core/connectors.py` and passes it into every `research_analysis` pack instance (`POST /run`, `/packs/research_analysis/run`, and stream routes). Other packs (e.g. `research_only`) are unaffected.

See `connectors/examples/example_connector.py`, `tests/test_connector_pack.py`, and `tests/test_api_connector.py`.

## Layout

| Path | Role |
|------|------|
| `base.py` | `ConnectorRequest`, `ConnectorResult`, `BaseConnector` |
| `examples/example_connector.py` | Runnable stub for docs/tests |

## Minimalism rationale

A single `fetch` method plus two dataclasses stays easy to implement for SQL, HTTP, or vector search without prescribing wire formats beyond “list of dict rows”. Registries and plugins can wait until multiple connectors exist and shared wiring is justified.
