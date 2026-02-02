# Threat Model

## Assumptions
- LLMs are untrusted
- Agent code is untrusted
- Memory contains sensitive data

## In-Scope Threats
- Unauthorized memory access
- Policy bypass
- Audit log tampering
- Tenant data leakage

## Mitigations
- Retrieval guard
- Policy engine
- Append-only logs
- Kill switch

## Out of Scope
- LLM hallucinations
- Third-party model vulnerabilities
