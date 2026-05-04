# Control plane (foundation — Sprint 2)

This folder holds **types and documentation only**. There is no evaluator, no tenant model, no feature-flag service, and no integration with FastAPI or `PackRegistry` beyond naming compatibility (`pack_id` aligns with registered packs).

## What the control plane will own (directional)

| Area | Intent (future) |
|------|-----------------|
| **Pack-level policies** | Named bundles keyed by `pack_id` — caps, labels, extension metadata. |
| **Execution constraints** | Advisory limits (`ExecutionConstraints`) that orchestration or packs may honour. |
| **Governance hooks** | Labels and `extensions` dict reserved for audit, cost centres, or routing hints — **not interpreted here**. |
| **Feature flags / policy engine** | Explicitly **out of scope** for this skeleton; strings like `labels` are placeholders only. |

## What this is **not**

- Not a dynamic policy DSL or OPA integration.
- Not multi-tenant isolation or quota enforcement.
- Not a replacement for `DEFAULT_PACK_ID` or `PackRegistry.register()`.

## Compatibility with `PackRegistry`

Policies use the same **`pack_id`** strings as `platform.registry.PackRegistry`. Registration remains **explicit and static** in `platform/__init__.py`. This package does **not** register packs or duplicate the registry.

## Files

| File | Role |
|------|------|
| `policies.py` | `ExecutionConstraints`, `PackPolicy` dataclasses. |
| `__init__.py` | Public exports for imports: `from control_plane import PackPolicy`. |

## Minimalism

Two frozen dataclasses avoid inventing interfaces before call sites exist. Enforcement belongs in API middleware or pack code in a later sprint.
