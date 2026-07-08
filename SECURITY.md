# Security Policy

Full security model, hardening details, and the automated scanning pipeline
are documented in **[docs/security.md](docs/security.md)**.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report privately via either channel:

1. [GitHub Security Advisories](https://github.com/brescou/langgraph-agent-stack/security/advisories/new)
   for this repository (preferred).
2. Email the maintainer listed on the [GitHub profile](https://github.com/brescou)
   if you cannot use Security Advisories.

Include a description of the vulnerability and its potential impact, steps to
reproduce (or a proof-of-concept, if safe to share), affected files/versions,
and any suggested mitigations.

**What to expect:** acknowledgement within 48 hours, and an initial
assessment and severity rating within 5 business days. See
[docs/security.md § 9](docs/security.md#9-reporting-vulnerabilities) for the
full process.

## Supported Versions

This is a template repository, not a versioned library with a long-term
support matrix. Security fixes are applied to the latest release on `main`;
older tagged releases are not backported.
