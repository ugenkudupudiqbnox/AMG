# Security Policy

Agent Memory Governance (AMG) is designed for use in **security- and compliance-sensitive environments**.

We take security issues seriously.

---

## Supported Versions

Only the latest released version of AMG is supported with security fixes.

Early development branches may not receive patches.

---

## Reporting a Security Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, report issues privately by emailing:

📧 ugen@qbnox.com

Please include:
- A detailed description of the issue
- Steps to reproduce (if applicable)
- Potential impact
- Any suggested mitigation

We aim to acknowledge reports within **72 hours**.

---

## Responsible Disclosure

We follow responsible disclosure practices:

- Issues are investigated privately
- Fixes are prepared before public disclosure
- Credit is given to reporters (if desired)

---

## Security Scope

The following are considered **in-scope** security issues:

- Memory isolation failures
- Policy enforcement bypasses
- Unauthorized memory access
- Audit log tampering
- Kill switch bypass
- Tenant isolation violations
- Privilege escalation

The following are **out of scope**:

- Vulnerabilities in third-party LLM providers
- Model hallucinations
- Prompt injection inside the LLM itself
- Issues caused by misconfiguration outside AMG

---

## Security Design Assumptions

AMG assumes:

- LLMs are untrusted
- Agent code is untrusted
- Governance layers must not be bypassable
- All critical actions are logged

Security contributions must preserve these assumptions.

---

Thank you for helping keep AMG secure.
