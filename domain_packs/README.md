# Domain packs

Built-in pipelines registered via `pack_kernel/builtin_packs.py` (Approach B — explicit).

## Layout by business domain

```
domain_packs/
├── research/       research_analysis, research_only, analysis_only
├── productivity/   summariser, meeting_prep, rfp_assistant, support_triage, executive_brief
├── hr/             talent_screening, job_description_writer, hr_policy_qa
├── finance/        financial_memo
├── legal/          contract_reviewer
└── common/         shared helpers (structured_llm, compliance, prompt_safety, …)
```

URLs use flat `pack_id` values — e.g. `POST /packs/talent_screening/run`, not `/packs/hr/talent_screening/run`.

## Research (`domain_packs/research/`)

| `pack_id` | Class | Use case |
|-----------|--------|----------|
| `research_analysis` | `ResearchAnalysisPack` | Default — Research → Analysis |
| `research_only` | `ResearchOnlyPack` | Research phase only |
| `analysis_only` | `AnalysisOnlyPack` | Analysis on pre-supplied research |

## Productivity (`domain_packs/productivity/`)

| `pack_id` | Route | Description |
|-----------|-------|-------------|
| `summariser` | `POST /packs/summariser/run` | Bullet-point summary |
| `meeting_prep` | `POST /packs/meeting_prep/run` | Sales meeting brief |
| `rfp_assistant` | `POST /packs/rfp_assistant/run` | RFP analysis + response plan |
| `support_triage` | `POST /packs/support_triage/run` | Ticket triage + draft reply |
| `executive_brief` | `POST /packs/executive_brief/run` | C-level brief from long text |

## HR (`domain_packs/hr/`)

Regulated vertical packs — require `REGULATED_PACKS_ENABLED=true` at runtime. See each pack's `COMPLIANCE.md`.

| `pack_id` | Description |
|-----------|-------------|
| `talent_screening` | CV vs job description — fit score, questions, red flags |
| `job_description_writer` | Inclusive JD + rubric + bias notes |
| `hr_policy_qa` | Employee policy Q&A with citations |

## Finance (`domain_packs/finance/`)

| `pack_id` | Route | Description |
|-----------|-------|-------------|
| `financial_memo` | `POST /packs/financial_memo/run` | SCQA strategy memo |

## Legal (`domain_packs/legal/`)

| `pack_id` | Route | Description |
|-----------|-------|-------------|
| `contract_reviewer` | `POST /packs/contract_reviewer/run` | Contract risk review |

## Examples

```bash
curl -X POST http://localhost:8000/packs/meeting_prep/run \
  -H 'Content-Type: application/json' \
  -d '{"company": "Acme", "person": "Jane", "meeting_goal": "discovery"}'

curl -X POST http://localhost:8000/packs/talent_screening/run \
  -H 'Content-Type: application/json' \
  -d '{"job_description": "...", "resume_text": "..."}'
```

## RAG / connectors

Packs whose constructor accepts `connector=` receive the shared connector when
`CONNECTOR_ENABLED=true` (see `api/dependencies.py` → `pack_runtime_kwargs`).
Useful for `rfp_assistant`, `contract_reviewer`, `hr_policy_qa`, `meeting_prep`,
`support_triage`, and `research_analysis`.

## Authoring a new pack

1. Create `domain_packs/<domain>/<pack_id>/` with `pack.py` and `schemas.py`.
2. Subclass `StructuredLLMPack` in `domain_packs/common/structured_llm.py` for single-LLM verticals, or `BaseDomainPack` for multi-agent graphs.
3. Register the class in `pack_kernel/builtin_packs.py`.
4. Add a policy row in `control_plane/__init__.py`.
5. Add tests in `tests/test_vertical_packs.py` (or a dedicated file).

Minimal second-pack example: `domain_packs/research/research_only/`.
