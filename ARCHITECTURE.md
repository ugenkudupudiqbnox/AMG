# Architecture

## Overview
Agent Memory Governance (AMG) is a governance-first control plane for AI agent memory and context.
It enforces policy, auditability, and deterministic behavior outside of LLMs and agent code.

AMG is part of the **agentic canvas**: the foundational infrastructure that governs how agents
remember, recall, and act — without participating in reasoning or planning.

---

## Design Goals

- Treat memory as a regulated enterprise data asset
- Enforce governance before intelligence
- Ensure deterministic, explainable agent behavior
- Remain LLM- and framework-agnostic
- Enable immediate incident response (kill switch)

---

## High-Level Architecture

```
┌──────────────────┐
│   Agent / LLM    │   ← reasoning & generation (untrusted)
└────────┬─────────┘
         │
┌────────▼─────────┐
│       AMG        │   ← governance & memory control plane
│ ─────────────── │
│  • Policy Engine │
│  • Context Guard │
│  • Memory Store  │
│  • Audit Log     │
│  • Kill Switch   │
└────────┬─────────┘
         │
┌────────▼─────────┐
│ Tools / Systems  │
└──────────────────┘
```

Agents never access memory or tools directly.
All access is mediated by AMG.

---

## Core Planes

### 1. Governance Control Plane

Responsible for:
- Policy enforcement
- Access control
- Retention rules
- Incident response
- Compliance alignment

Key components:
- Policy engine (policy-as-config)
- Agent identity & role model
- Kill switch & memory freeze
- Immutable audit logging

---

### 2. Memory Management Plane

Responsible for the full memory lifecycle:

- Memory classification
- Sensitivity tagging
- TTL enforcement
- Retrieval filtering
- Deletion and decay

Supported memory types:
- Short-term (request-scoped)
- Long-term (TTL enforced)
- Episodic (TTL + decay)

Memory is never exposed directly to agents.

---

### 3. Agent Execution Plane (Untrusted)

Includes:
- LLMs
- Agent frameworks
- Tool logic
- Workflow orchestration

This plane:
- Cannot bypass governance
- Cannot write memory without policy checks
- Cannot access raw audit logs

AMG assumes this plane is untrusted by default.

---

## Governed Context Builder

Before context is passed to an agent, AMG enforces:

- Agent identity validation
- Memory-type filtering
- TTL validation
- Sensitivity filtering
- Token budget limits

This ensures agents receive **short, focused, policy-compliant context**.

---

## Audit & Replay

Every request produces an append-only audit record:

- Request ID
- Agent ID
- Prompt hash
- Memory IDs used
- Policy decisions
- Output hash
- Timestamp

This enables deterministic replay and post-incident analysis.

---

## Incident Response & Kill Switch

AMG supports:
- Per-agent disable
- Memory write freeze
- Read-only mode
- Global shutdown

If an agent cannot be stopped, it should not be deployed.

---

## Deployment Models

AMG can be deployed as:
- Standalone service
- Sidecar to agent runtime
- Internal platform component

Designed for zero-trust environments.

---

## Non-Goals (Intentional)

AMG does NOT:
- Perform reasoning or planning
- Implement agentic patterns
- Learn or adapt behavior
- Coordinate multi-agent memory
- Provide dashboards or UI

These exclusions preserve auditability and trust.

---

## Architectural Philosophy

> Intelligence belongs in agents.
> Governance belongs in infrastructure.

AMG exists to make agent deployments **safe, explainable, and enterprise-ready**.
