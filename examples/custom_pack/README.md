# Custom pack walkthrough

Tutorial for authoring a **self-contained** domain pack outside `domain_packs/`.
The `EchoPack` in this folder is deterministic (no LLM) so you can run it locally
without API keys.

## Step 1 — Define Pydantic schemas

Create `schemas.py` with `input_schema` / `output_schema` models:

- `EchoInput` — fields the API and `run_from_input()` accept
- `EchoOutput` — structured result returned to callers

See [`schemas.py`](schemas.py).

## Step 2 — Implement the pack class

Subclass `BaseDomainPack` from `pack_kernel/base_pack.py` and set class attributes:

| Attribute | Purpose |
|-----------|---------|
| `pack_id` | Stable registry key (used in URLs: `/packs/{pack_id}/run`) |
| `name`, `description` | Discovery metadata |
| `input_schema`, `output_schema` | Typed I/O |
| `primary_field` | Name of the main string field for `run(query: str)` |

Implement:

- `run_from_input(body)` — typed entry point (used by generated API routes)
- `run(query)` — legacy string API
- `arun(query)` — async wrapper
- `_iter_stream_events(query)` — SSE stream for `/run/stream`

See [`pack.py`](pack.py).

For **LLM-backed vertical packs**, subclass `StructuredLLMPack` instead, set
`primary_field`, and implement `build_prompt()` — see `domain_packs/README.md`.

## Step 3 — Register the pack

Registration is explicit (Approach B). In your app startup or a one-off script:

```python
from pack_kernel.registry import PackRegistry
from examples.custom_pack import EchoPack

PackRegistry.register(EchoPack)
```

Built-in packs are registered in `pack_kernel/builtin_packs.py`; custom packs are
usually registered in your deployment entrypoint after importing the class.

## Step 4 — Run locally (Python)

```python
from examples.custom_pack import EchoInput, EchoPack

pack = EchoPack(run_id="demo-1")
result = pack.run_from_input(EchoInput(text="hello custom pack"))
print(result.echoed)  # HELLO CUSTOM PACK
print(result.word_count)  # 3
```

Or the string API:

```python
result = pack.run("hello custom pack")
```

## Step 5 — Expose via HTTP (optional)

After `PackRegistry.register(EchoPack)` and API lifespan wiring, call:

```bash
curl -X POST http://localhost:8000/packs/echo_tutorial/run \
  -H 'Content-Type: application/json' \
  -d '{"text": "hello from curl"}'
```

Add a policy row in `control_plane/` before production traffic.

## Step 6 — Tests and policies

1. Add unit tests (mirror `tests/test_vertical_packs.py`).
2. Register in your environment's pack list if you use allowlists.
3. For regulated domains, follow compliance hooks in `domain_packs/common/compliance.py`.

## Layout

```
examples/custom_pack/
  schemas.py   # Pydantic I/O
  pack.py      # EchoPack implementation
  README.md    # This walkthrough
```

No imports from `domain_packs/summariser` — this tree is the reference starting point.
