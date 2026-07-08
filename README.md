# langgraph-agent-stack

> Production-grade **template** for multi-agent LangGraph systems — hardened FastAPI API, domain packs, Helm, Terraform stubs, CI, and observability. Multi-tenant identity is **your** layer ([Security guide](docs/security.md)).

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet)](https://github.com/astral-sh/uv)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-orange)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/brescou/langgraph-agent-stack/actions/workflows/ci.yml/badge.svg)](https://github.com/brescou/langgraph-agent-stack/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-757%2B%20passing-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-87%25-brightgreen)](tests/)

## What is this?

A deployable starting point for ML / data engineers who want a **real** agent stack—not a notebook demo. The default pipeline is Research → Analysis (`ResearchAgent` + `AnalystAgent`), exposed over FastAPI with SSE streaming, session history, cost tracking, and pack-based routing.

**Included:** Docker, Helm chart, Terraform entry points (GKE / EKS / AKS), rate limiting, input validation, structured logging, Prometheus metrics, CI security scans, GHCR images with SBOM + Cosign on `main`.

**Not included:** OAuth2/OIDC, per-tenant API keys, or billing. The built-in `API_KEY` is a single shared Bearer secret for internal / single-tenant use.

## Why this instead of…

**…LangGraph Platform?** LangGraph Platform is a legitimate, well-supported managed option — use it if you want a hosted control plane and don't want to run infrastructure yourself. This repo is for the opposite case: you self-host on your own Kubernetes cluster, keep full control of observability (Prometheus/OTel) and per-run cost data, and ship under the MIT license with zero vendor lock-in. Neither is objectively "better" — it's a build-vs-buy trade-off, and this template is for teams who'd rather own the stack.

**…a generic agent-service-toolkit template?** Beyond the usual FastAPI-around-LangGraph scaffolding, this repo ships production concerns already wired in: per-run USD budgets that return HTTP `402` on overrun, multi-version pack routing with canary traffic weights, and a supply chain that signs container images with Cosign and publishes an SBOM on every release.

## Quick start

**Prerequisites:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (package manager).

```bash
git clone https://github.com/brescou/langgraph-agent-stack.git
cd langgraph-agent-stack
uv sync --extra anthropic
cp .env.example .env   # set ANTHROPIC_API_KEY
uv run uvicorn api.main:app --reload
```

> **Try it without any API key.** Set `LLM_PROVIDER=mock` in `.env` (or `LLM_PROVIDER=mock uv run uvicorn api.main:app --reload`) to get deterministic, zero-cost responses from every endpoint — useful for exploring the API, running the test suite, or CI, before wiring up a real provider. Web search is also mocked by default (`SEARCH_PROVIDER=mock`); set `SEARCH_PROVIDER=tavily` (or `serpapi`) for real results.

```bash
# Legacy default pipeline (research_analysis pack)
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the latest advances in quantum computing?"}'

# Pack registry
curl http://localhost:8000/packs
curl -X POST http://localhost:8000/packs/meeting_prep/run \
  -H "Content-Type: application/json" \
  -d '{"company": "Acme", "person": "Jane", "meeting_goal": "discovery"}'
```

Interactive API docs: `http://localhost:8000/docs` (disabled when `ENVIRONMENT=production`).

**Cost:** with a real provider, a `research_analysis` run (6 LLM calls) costs roughly **$0.01–0.05** on Claude Sonnet 5 pricing ($0.003 / $0.015 per 1K input/output tokens) — a rough order of magnitude from the pricing table in `core/cost.py`, not a measured benchmark. Set `PACK_DEFAULT_BUDGET_USD=0.50` to cap spend per run; requests over budget return HTTP `402`.

## Architecture

```
Client → FastAPI (auth · rate limit · validation)
              → PackRegistry / control_plane policies
              → domain_packs/* (LangGraph workflows)
              → agents/* (reusable agent nodes)
              → core/* (LLM · memory · security · cost · observability)
              → connectors/* (optional retrieval)
```

| Layer | Path | Role |
|-------|------|------|
| HTTP | `api/` | FastAPI app (`app.py`), middlewares, endpoints, pack router factory |
| Kernel | `pack_kernel/` | `BaseDomainPack`, `PackRegistry`, versioning, traffic split |
| Workflows | `domain_packs/` | Packs grouped by domain — see [domain_packs/README.md](domain_packs/README.md) |
| Agents | `agents/` | Reusable LangGraph agents (`ResearchAgent`, `AnalystAgent`, …) |
| Policies | `control_plane/` | Per-pack limits (query size, budget, stream timeout) — [control_plane/README.md](control_plane/README.md) |
| Connectors | `connectors/` | Retrieval adapters — [connectors/README.md](connectors/README.md) (`core/connectors.py` is a compat shim) |
| Foundation | `core/` | Config, LLM factory, memory, security, cost, observability |
| Ops | `infra/` | Dockerfile, Compose, Helm, Terraform |

`core/graph.py` is a **compatibility shim** (`MultiAgentGraph` → `ResearchAnalysisPack`). New orchestration belongs in a domain pack.

## Domain packs

13 built-in packs registered in `pack_kernel/builtin_packs.py`:

| Category | Examples |
|----------|----------|
| Research (`domain_packs/research/`) | `research_analysis`, `research_only`, `analysis_only` |
| Productivity (`domain_packs/productivity/`) | `summariser`, `meeting_prep`, `rfp_assistant`, `support_triage`, `executive_brief` |
| HR (`domain_packs/hr/`) | `talent_screening`, `job_description_writer`, `hr_policy_qa` |
| Finance (`domain_packs/finance/`) | `financial_memo` |
| Legal (`domain_packs/legal/`) | `contract_reviewer` |

Each pack gets typed `POST /packs/{pack_id}/run` and `/run/stream` when schemas are declared. Versioning, traffic weights, and sticky sessions: `GET /packs`, `GET /packs/{id}/versions`, headers `X-Pack-Version` / `X-Pack-Version-Used`.

Full catalogue and authoring guide: **[domain_packs/README.md](domain_packs/README.md)**.

The HR, legal, and finance packs demonstrate the pack system on regulated-adjacent use cases, but they are **off by default** (`REGULATED_PACKS_ENABLED=false`) — calling them returns HTTP `403` until you complete the pack's `COMPLIANCE.md` checklist and explicitly opt in.

### Distributable packs (plugins)

Third-party packs ship as regular Python packages declaring an entry point in
the `langgraph_agent_stack.packs` group:

```toml
[project.entry-points."langgraph_agent_stack.packs"]
sentiment = "acme_packs.sentiment:SentimentPack"
```

Discovery is **opt-in and allowlisted** (`PACK_PLUGINS_ENABLED=true` +
`PACK_PLUGINS_ALLOWLIST=sentiment`): loading a plugin executes third-party
code, so nothing loads by default. At load time each class is validated
against the pack contract — `BaseDomainPack` subclass, complete metadata, and
**strict** (`extra="forbid"`) input/output schemas — and a broken plugin is
logged and skipped, never crashing startup. Built-in pack ids cannot be
overridden. Registered plugins get the same typed `/packs/{id}/run` routes,
versioning, and canary weights as built-ins. Packaging walkthrough:
[examples/custom_pack/README.md](examples/custom_pack/README.md).

## API (summary)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/packs` | List registered packs and metadata |
| `POST` | `/packs/{pack_id}/run` | Run a pack (typed body per pack schema) |
| `POST` | `/packs/{pack_id}/run/stream` | SSE stream for a pack |
| `POST` | `/run`, `/run/stream` | Legacy routes → `DEFAULT_PACK_ID` (`research_analysis`) |
| `POST` | `/research` | Research phase only |
| `GET` | `/health`, `/ready` | Probes |
| `GET` | `/sessions/{id}/history` | Session run history |
| `GET` | `/metrics` | Prometheus (with `observability` extra) |

Responses include `cost_usd` when cost tracking is active; HTTP **402** on budget exceed. See `/docs` for request/response schemas.

## LLM providers

Set `LLM_PROVIDER` and install the matching extra. Details and gateway overrides: `.env.example`.

| Provider | Value | Extra | Key env vars |
|----------|-------|-------|--------------|
| Anthropic | `anthropic` | `--extra anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `--extra openai` | `OPENAI_API_KEY` |
| Google | `google` | `--extra google` | `GOOGLE_API_KEY` |
| Bedrock | `bedrock` | `--extra bedrock` | `AWS_REGION`, `BEDROCK_MODEL` |
| Azure OpenAI | `azure` | `--extra openai` | `AZURE_OPENAI_*` |
| Ollama | `ollama` | `--extra ollama` | `OLLAMA_BASE_URL` |
| Mock (CI/dev) | `mock` | *(none)* | — |

## Run & deploy

**Docker Compose**

```bash
docker compose -f infra/docker-compose.yml up
docker compose -f infra/docker-compose.yml --profile redis up   # Redis memory backend
```

**Helm**

```bash
helm install langgraph ./infra/helm/langgraph-agent-stack \
  -f infra/helm/langgraph-agent-stack/values.prod.yaml \
  --namespace langgraph-agents --create-namespace
```

Production: set `secrets.existingSecret` (External Secrets Operator), `config.environment=production`, `networkPolicy.enabled=true`. Autoscaling defaults to **KEDA** on `active_pipelines` (not CPU). See chart `values.yaml` / `values.prod.yaml`.

> **Scaling note.** `MEMORY_BACKEND=sqlite` (default) is for development and single-replica deployments only — it's a local file, so state is not shared across pods. For production, multi-replica deployments, switch to `MEMORY_BACKEND=redis` or `MEMORY_BACKEND=postgres` so checkpointing and session history are consistent across replicas.

**Terraform** — entry points under `infra/terraform/{gke,eks,aks}/` (no shared root module). Configure a remote backend before production apply. GKE module expects [External Secrets Operator](docs/security.md#3-secret-management) installed before `ClusterSecretStore` resources.

**Infra CI locally:** `make infra-check` (template Checkov profile). Before production hardening: `make infra-check-prod` ([checklist](docs/security.md#before-going-to-production-checkov)).

## Security

Rate limiting (memory or Redis), request body cap, prompt-injection / SSRF input validation, security headers, optional `API_KEY` Bearer auth, graceful shutdown drain. Full model, env vars, K8s hardening, and scanning pipeline: **[docs/security.md](docs/security.md)**.

## Development

```bash
make help          # all targets
make check         # ruff + pyright (CI lint)
make test          # 757+ tests, mocked by default — no network, no API key required
make eval          # golden-dataset pack evaluations (deterministic)
make infra-check   # helm lint + kubeconform + checkov
```

### Pack evaluation

`evals/` runs golden datasets (`evals/datasets/<pack_id>.yaml`) through the
real pack code with scripted LLM responses — deterministic, no network. Each
case declares an input, the scripted responses, and checks
(`required_fields`, `contains`, `min_length`, `numeric_range`, or
`expect_error` for guard rejections). Compare two registered versions of a
pack before shifting canary weights:

```bash
uv run python -m evals --pack summariser            # one pack
uv run python -m evals --pack summariser --version 1.0 --compare 2.0
uv run python -m evals --all --json                 # CI-friendly output
```

Contributor workflow, pre-commit, and PR expectations: **[CONTRIBUTING.md](CONTRIBUTING.md)**.

**LangGraph patterns** (standalone scripts, not served by the API): [examples/README.md](examples/README.md).

## Project structure

```
langgraph-agent-stack/
├── api/                 # FastAPI (app.py, middleware, endpoints, router_factory)
├── pack_kernel/         # Pack contract + PackRegistry
├── domain_packs/        # research/, productivity/, hr/, finance/, legal/, common/
├── agents/              # Reusable LangGraph agents
├── connectors/          # Retrieval connector implementations
├── control_plane/       # Pack policies
├── core/                # Config, LLM, memory, security, cost, observability
├── infra/               # Dockerfile, compose, helm/, terraform/
├── examples/            # LangGraph pattern demos
├── tests/
├── docs/                # security.md, architecture.md, …
└── scripts/             # infra-devsecops.sh, …
```

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/security.md](docs/security.md) | Auth, secrets, K8s hardening, CI scans, supply chain, Checkov prod gate |
| [domain_packs/README.md](domain_packs/README.md) | Pack catalogue and authoring |
| [connectors/README.md](connectors/README.md) | Connector contract and wiring |
| [control_plane/README.md](control_plane/README.md) | Policy registry |
| [examples/README.md](examples/README.md) | Sequential, parallel, supervisor, human-in-loop |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, tests, PR process |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## License

MIT © [brescou](https://github.com/brescou)
