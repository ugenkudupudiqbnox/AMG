# Governance Quickstart

> **Goal:** Help new users understand how to apply governance correctly when using Agent Memory Governance (AMG).

This quickstart focuses on **governance behavior**, not agent intelligence.

---

## 1. What AMG Governs (and What It Doesn’t)

### AMG Governs

* Agent memory (what is stored, for how long)
* Context construction (what the agent sees)
* Access control (who/what can read or write memory)
* Auditability (what happened, when, and why)
* Incident response (how to stop agents)

### AMG Does NOT Govern

* Agent reasoning or planning
* Prompt design
* Learning or adaptation
* Multi-agent collaboration
* UI workflows

> Think of AMG as a **control plane**, not an agent framework.

---

## 2. Governance Roles (Minimal Model)

Before running any agent, define these roles conceptually:

| Role                 | Responsibility                    |
| -------------------- | --------------------------------- |
| **Agent Owner**      | Accountable for agent behavior    |
| **Governance Admin** | Defines policies                  |
| **Operator**         | Handles incidents (pause/disable) |

No UI or RBAC is required in V1 — roles are enforced via API and process.

---

## 3. Define a Basic Memory Policy (First Step)

AMG requires **explicit policies** before memory can be stored.

### Example: Episodic Memory with TTL

```yaml
policy_id: support-episodic
memory_type: episodic
ttl_seconds: 604800   # 7 days
sensitivity: pii
scope: tenant
allow_read: true
allow_write: true
```

**Key rules**

* Persistent memory MUST have a TTL
* Memory without a valid policy is rejected
* Policies are versioned and logged

---

## 4. Writing Memory (Governed by Default)

When an agent attempts to write memory:

```
Agent → AMG → Policy Check → Store or Reject → Audit Log
```

If the policy fails:

* the write is rejected
* a governance event is recorded
* no silent failures occur

---

## 5. Building Context for an Agent

Agents **never query memory directly**.

Instead, they request governed context:

```
Agent → Context Builder → Filtered Memory → Agent
```

AMG enforces:

* memory type filters
* TTL validity
* sensitivity rules
* token budgets

This ensures agents receive **only approved, minimal context**.

---

## 6. Audit & Replay (Critical for Trust)

Every agent request produces an audit record containing:

* Agent ID
* Policy version
* Memory IDs used
* Output hash
* Timestamp

You can always answer:

> “What did the agent know when it responded?”

---

## 7. Incident Response (When Things Go Wrong)

If an agent behaves unexpectedly:

### Immediate Actions

1. Disable the agent

   ```
   POST /agent/disable
   ```
2. Freeze memory writes (optional)
3. Switch to read-only mode if needed

### Investigation

* Replay audit logs
* Verify policy versions
* Inspect memory TTLs

AMG is designed to **stop harm first**, investigate second.

---

## 8. Policy Changes (Safe by Design)

When policies change:

* changes are versioned
* changes are logged
* enforcement is **prospective**, not retroactive

Optional re-evaluation can be triggered explicitly.

This prevents unexpected behavior changes.

---

## 9. Common Mistakes to Avoid

❌ Letting agents store memory without TTL
❌ Bypassing AMG for “performance”
❌ Treating audit logs as optional
❌ Mixing governance with reasoning logic
❌ Enabling learning in V1

---

## 10. Governance Success Checklist

Before production use, confirm:

* [ ] All persistent memory has TTL
* [ ] Policies are versioned
* [ ] Agent Owner is defined
* [ ] Kill switch tested
* [ ] Audit replay verified
* [ ] No direct memory access by agents

If all boxes are checked, you’re using AMG correctly.

---

## Philosophy Reminder

> **Governance is not a feature.
> It is a constraint that makes deployment possible.**

AMG exists to make AI agents **safe, explainable, and enterprise-ready**.

---

# First 15 Minutes with Agent Memory Governance (AMG)

> **Goal:** Safely run your first governed AI agent and prove it is auditable, stoppable, and compliant.

This walkthrough focuses on **governance correctness**, not intelligence.

---

## Minute 0–2: Understand the Boundary

Before touching code, internalize this:

* The agent is **untrusted**
* The LLM is **untrusted**
* AMG is the **control plane**

Agents **never**:

* read memory directly
* write memory directly
* call tools directly

Everything goes through AMG.

If this boundary is unclear, stop here.

---

## Minute 2–5: Define Your First Governance Policy

Create a minimal policy file for episodic memory.

### `policy-support-episodic.yaml`

```yaml
policy_id: support-episodic-v1
memory_type: episodic
ttl_seconds: 604800        # 7 days
sensitivity: pii
scope: tenant
allow_read: true
allow_write: true
```

Key governance checks:

* ✅ TTL is mandatory
* ✅ Sensitivity is explicit
* ✅ Scope is defined

Without this policy, memory writes will be rejected.

---

## Minute 5–7: Register an Agent (Conceptually)

Every agent must have:

* an **Agent ID**
* an **Agent Owner**
* a defined scope

Example (conceptual):

```
agent_id: support-agent-001
owner: customer-support-team
policies:
  - support-episodic-v1
```

You don’t need a UI in V1.
This can live in config or code.

---

## Minute 7–9: Attempt a Memory Write

The agent attempts to store a memory:

```
POST /memory/write
```

Payload (simplified):

```json
{
  "agent_id": "support-agent-001",
  "policy_id": "support-episodic-v1",
  "content": "Customer phone number shared during support chat"
}
```

### What AMG does

1. Validates agent identity
2. Evaluates policy
3. Enforces TTL
4. Stores memory
5. Writes audit log

If anything fails → **write is rejected and logged**

---

## Minute 9–11: Build Context for a Response

The agent now requests context:

```
POST /context/build
```

AMG:

* filters by memory type
* checks TTL
* applies sensitivity rules
* enforces token limits

The agent receives **only approved memory IDs**, not raw stores.

This is **context engineering with governance**.

---

## Minute 11–13: Inspect the Audit Log

Retrieve the audit record:

```
GET /audit/{request_id}
```

You should see:

* agent ID
* policy version
* memory IDs used
* timestamp
* output hash

Ask yourself:

> “Can I explain exactly why the agent responded the way it did?”

If yes → governance is working.

---

## Minute 13–14: Test the Kill Switch (Mandatory)

Disable the agent:

```
POST /agent/disable
```

Now attempt:

* a memory write
* a context build

Both **must fail**.

If they don’t, **do not proceed to production**.

---

## Minute 14–15: Delete Data (Right to Forget)

Trigger manual deletion:

```
POST /memory/delete
```

Confirm:

* memory is removed
* deletion is logged
* future context builds no longer include it

This satisfies data subject deletion expectations.

---

## What You’ve Proven in 15 Minutes

✔ Memory cannot be written without policy
✔ Retention is enforced
✔ Context is curated
✔ Behavior is auditable
✔ Agents are stoppable
✔ Deletion is provable

This is **enterprise-grade governance**.

---

## Common Early Mistakes

❌ Skipping TTLs “for now”
❌ Letting agents cache memory outside AMG
❌ Treating audit logs as optional
❌ Testing only happy path
❌ Confusing governance with prompt design

---

## If This Feels Strict — That’s the Point

> **Loose systems fail audits.
> Strict systems get deployed.**

AMG is intentionally conservative.

---

## Next Steps After the First 15 Minutes

* Add a second policy (non-PII memory)
* Simulate a policy change
* Run an incident drill
* Map governance events to SOC 2 evidence
* Invite a security reviewer to break it

---
