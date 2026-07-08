---
name: Bug report
about: Report something that doesn't work as expected
title: ''
labels: bug
assignees: ''

---

> **Security vulnerability?** Do not open a public issue — follow the private
> reporting process in [SECURITY.md](../../SECURITY.md) instead.

**Describe the bug**
A clear and concise description of what the bug is.

**To reproduce**
Steps to reproduce the behavior, ideally with `LLM_PROVIDER=mock` (no API key
required) so it's easy for a maintainer to run:

1. Set `...` in `.env`
2. Run `...` (e.g. `uv run uvicorn api.main:app --reload`, `make test`)
3. Call `...` (e.g. `curl -X POST /run -d '...'`)
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Environment**
- Version / commit: [e.g. `v0.6.0`, or `git rev-parse HEAD`]
- Python version: [e.g. 3.12.4]
- `LLM_PROVIDER`: [e.g. `mock`, `anthropic`, `openai`]
- `MEMORY_BACKEND`: [e.g. `sqlite`, `redis`, `postgres`]
- Deployment: [e.g. local `uv run`, Docker Compose, Helm/Kubernetes]
- OS: [e.g. Ubuntu 24.04, macOS 15, Windows 11 + WSL2]

**Logs / traceback**
Paste relevant structured log output or a traceback. Redact any secrets,
API keys, or tokens before pasting (`sanitize_log_data` should already
redact known-sensitive keys, but double-check).

**Additional context**
Add any other context about the problem here.
