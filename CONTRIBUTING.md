# Contributing to Agent Memory Governance (AMG)

Thank you for your interest in contributing to Agent Memory Governance (AMG).

AMG is a **governance-first infrastructure project**.  
Our primary goals are **correctness, determinism, and auditability** — not feature velocity.

Please read this document carefully before contributing.

---

## Guiding Principles

All contributions must respect the following principles:

1. **Governance precedes intelligence**
2. **Memory is a regulated data asset**
3. **Controls live outside the LLM**
4. **Deterministic behavior over cleverness**
5. **Auditability over convenience**

If a contribution weakens auditability, predictability, or policy enforcement, it will not be accepted.

---

## What We Welcome

We welcome contributions in the following areas:

- Bug fixes and hardening
- Storage adapters (Postgres, vector stores, etc.)
- Agent framework adapters (LangGraph, custom agents, etc.)
- Policy engine extensions (non-breaking)
- Documentation improvements
- Tests and benchmarks
- Example agents demonstrating governed behavior

---

## What We Do NOT Accept (V1)

The following are out of scope and will not be merged:

- Agent reasoning, planning, or learning logic
- Multi-agent memory sharing
- Self-modifying or self-learning systems
- UI dashboards
- Auto-PII detection logic
- Features that bypass governance layers

These exclusions are intentional.

---

## Development Workflow

1. Fork the repository
2. Create a feature branch (`feature/<short-description>`)
3. Make focused, minimal changes
4. Add or update tests where applicable
5. Ensure all checks pass
6. Open a pull request with a clear description

---

## Pull Request Guidelines

All PRs must include:

- A clear problem statement
- A description of the change
- Explicit governance impact (if any)
- Confirmation that no policies are bypassed
- Tests or justification if tests are not applicable

PRs without sufficient context may be closed.

---

## Coding Standards

- Favor explicit over implicit behavior
- Avoid hidden side effects
- Prefer configuration over code where possible
- All critical paths must be testable
- All breaking changes require discussion

---

## Review Process

AMG uses a **conservative review process**:

- All changes are reviewed by maintainers
- Governance-impacting changes require deeper scrutiny
- Maintainers may request design clarification before approval

---

## Project Governance

AMG currently follows a **BDFL (Benevolent Dictator for Life)** model.

- Roadmaps are public
- Breaking changes require discussion
- Security issues follow responsible disclosure (see SECURITY.md)

---

Thank you for helping build trustworthy agent infrastructure.
