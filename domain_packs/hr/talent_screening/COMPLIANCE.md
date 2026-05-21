# Compliance Considerations — Talent Screening

**This pack produces assistive drafts only. It is not a hiring decision system.**

## Regulatory context (non-exhaustive)

| Framework | Relevance |
|-----------|-----------|
| **EU AI Act Annex III §4(a)** | AI for recruitment/candidate evaluation may qualify as **high-risk**. Operators may need technical documentation, bias monitoring, human oversight, EU registration, and CE marking. |
| **GDPR Art. 22** | Candidates may have the right not to be subject to solely automated decisions with legal/significant effects. |
| **Québec Law 25** | Automated decision-making may require transparency, explanation, and human review rights. |
| **NYC Local Law 144** | Automated employment decision tools may require annual bias audits and candidate notice. |

## What this template provides

- `human_review_required: true` on every API response (enforced server-side).
- Mandatory `disclaimer` injected server-side (LLM cannot omit it).
- `PackPolicy.human_review_required` in `control_plane/policies.py`.

## What operators must still implement

- Lawful basis and privacy notices for CV/resume processing (PII).
- Human-in-the-loop workflow before any adverse action.
- Bias/fairness testing appropriate to your jurisdiction.
- Audit logging, retention limits, and data subject request handling.
- Legal review before production use in regulated markets.

**For research and demo only unless you complete a full compliance programme.**
