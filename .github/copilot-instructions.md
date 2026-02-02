# AI Agent Instructions for AMG

## Project Purpose & Scope
**Agent Memory Governance (AMG)** is a governance-first control plane for AI agent memory—not an agent framework. It mediates all memory access and ensures deterministic, auditable agent behavior. Never contribute features that improve reasoning, planning, or LLM intelligence; AMG stays strictly below intelligence and above storage.

### Core Principle
> **Governance precedes intelligence. Controls live outside the LLM.**

---

## Architecture Orientation
```
Agent/LLM (untrusted)
    ↓
AMG (governance plane)
    • Policy Engine
    • Context Guard
    • Memory Store
    • Audit Log
    • Kill Switch
    ↓
Tools/Systems
```

AMG's design assumes:
- **Agent code is untrusted**
- **LLMs cannot be trusted** with policy enforcement
- **All governance must be externalized** and non-bypassable
- **Every action must be auditable** with immutable logs

---

## Memory Model (Core Abstraction)
Every memory item has these attributes (see [POLICY_SCHEMA.md](../POLICY_SCHEMA.md)):
- **Type**: short_term | long_term | episodic
- **TTL**: Retention duration in seconds
- **Sensitivity**: pii | non_pii
- **Scope**: agent | tenant
- **Provenance**: Source event
- **Usage constraints**: read/write permissions

Key insight: Memory is not a blob—it's a **regulated data asset** with explicit governance contracts.

---

## Critical Contributions & Patterns

### ✅ Welcome (In-Scope for V1)
- Policy engine extensions (non-breaking)
- Storage adapters (Postgres, vector stores, etc.)
- Agent framework adapters (LangGraph, custom agents)
- Memory lifecycle management (TTL, decay, deletion)
- Audit log enhancements
- Kill switch & incident response controls
- Tests and governance-focused examples

### ❌ Out of Scope (Will Not Be Merged)
- Agent reasoning, planning, or learning logic
- Multi-agent memory sharing protocols
- Self-modifying or self-learning systems
- UI dashboards or visualization tools
- Automatic PII detection (declarative policies only)
- Features that bypass governance layers

---

## Development Philosophy

### Code Decisions
1. **Explicit > Implicit**: Hidden side effects make auditing impossible
2. **Configuration > Code**: Governance should be declarative where possible
3. **Deterministic > Flexible**: Agents must behave predictably
4. **Auditability > Performance**: Every critical decision must be loggable
5. **Conservative > Clever**: When in doubt, enforce stricter controls

### Critical Paths
All critical paths must be:
- Fully testable
- Independently verifiable
- Non-bypassable by agent code
- Accompanied by immutable audit records

---

## Contribution Workflow

### PR Requirements
All pull requests must include:
1. **Problem statement**: What governance gap does this solve?
2. **Governance impact**: Does this affect policy enforcement, auditability, or access control?
3. **Proof of non-bypass**: Confirm agents cannot circumvent new controls
4. **Tests**: Critical paths require test coverage
5. **No aspirational code**: Only document patterns that already exist

### Review Criteria
- Does this strengthen or weaken auditability?
- Can agents bypass this control?
- Is behavior deterministic?
- Does it follow the six core principles?
  1. Memory is a regulated data asset
  2. Governance precedes intelligence
  3. Context must be curated, not accumulated
  4. All controls live outside the LLM
  5. Every agent action must be explainable
  6. Agents must be stoppable instantly

---

## Key Documentation Files
- [README.md](../README.md): Why AMG exists, core concepts, memory model
- [ARCHITECTURE.md](../ARCHITECTURE.md): High-level design, planes, data flows
- [POLICY_SCHEMA.md](../POLICY_SCHEMA.md): Governance contract definitions
- [CONTRIBUTING.md](../CONTRIBUTING.md): Contribution guidelines and scope
- [GOVERNANCE_MODEL.md](../GOVERNANCE_MODEL.md): Decision principles, change policy
- [SECURITY.md](../SECURITY.md): Security scope, responsible disclosure

---

## Test Structure & Patterns

### Critical Path Tests
Every critical path must have tests verifying:
1. **Policy enforcement**: Memory write/read respects policy rules
2. **Non-bypassability**: Agents cannot circumvent governance via direct storage access
3. **Audit completeness**: Every decision is logged with immutable record
4. **TTL correctness**: Memory expires at correct time (not early, not late)
5. **Isolation**: Agent scope isolation and tenant isolation maintained

### Test Organization
```
tests/
├── governance/         # Policy engine, rule evaluation
│   ├── policy_evaluation_test.py
│   ├── ttl_enforcement_test.py
│   └── isolation_test.py
├── memory/            # Memory lifecycle (write, read, delete, decay)
│   ├── lifecycle_test.py
│   ├── sensitivity_filtering_test.py
│   └── context_builder_test.py
├── audit/             # Audit log immutability and completeness
│   ├── audit_integrity_test.py
│   └── replay_test.py
├── incident/          # Kill switch, freeze, disable
│   ├── kill_switch_test.py
│   └── freeze_test.py
└── adapters/          # Storage and framework adapter contracts
    ├── storage_adapter_test.py
    └── framework_adapter_test.py
```

### Example Test Pattern
```python
def test_policy_prevents_unauthorized_read():
    """Agent cannot read memory it lacks permission for"""
    # Setup: Create memory with allow_read=false
    # Execute: Agent attempts read
    # Assert: Request denied, audit log records attempt
    # Verify: Memory unchanged, no side effects
```

---

## Storage Adapter Pattern

Storage adapters must implement the core interface contract. Adapters should be **deterministic, versioned, and never opaque** about what is stored.

### Required Interface
```python
class StorageAdapter:
    # Write with full provenance (no side effects)
    def write(self, memory_id, content, policy_metadata) -> AuditRecord
    
    # Read enforces policy at retrieval time
    def read(self, memory_id, agent_id, policy_check) -> (Content, AuditRecord)
    
    # Delete is permanent (no soft deletes for compliance)
    def delete(self, memory_id) -> AuditRecord
    
    # Retrieval guard: always filters by policy before returning
    def query(self, filters, agent_id, policy_check) -> List[Memory]
```

### Adapter Responsibilities
- **No hidden behavior**: Every operation must be loggable
- **Policy-aware reads**: Enforce sensitivity/scope filters at retrieval time
- **TTL enforcement**: Respect memory expiration (delete or mark expired)
- **Append-only audit**: Write-once audit trail, never modified
- **Isolation guarantees**: Agent scope and tenant scope must be non-bypassable

### Example: Postgres Adapter
```
adapters/postgres/
├── __init__.py
├── connection.py       # Connection pooling, timeouts
├── schema.py          # Table definitions (memory, audit, policy)
├── write.py           # INSERT with audit record
├── read.py            # SELECT with policy filtering
├── query.py           # Retrieval guard: enforce filters
└── test_postgres_adapter.py
```

### Configuration (Declarative, Not Algorithmic)
Adapters should be configured via policy-as-config, not code logic:
```yaml
storage:
  engine: postgres
  ttl_enforcement: strict  # strict = delete at TTL, lazy = mark expired
  isolation: tenant       # agent | tenant
  audit: append_only
  connection_pool:
    min: 5
    max: 20
```

---

## Agent Framework Adapter Pattern

Framework adapters integrate AMG into LLM frameworks (LangGraph, CrewAI, custom agents) **without modifying their core logic**. Adapters must be transparent governance proxies—adding control without changing reasoning.

### Required Interface
```python
class FrameworkAdapter:
    # Intercept memory reads before passing to agent
    def build_context(self, agent_id, memory_filters) -> GovernedContext:
        """Apply governance: TTL check, sensitivity filter, token budget"""
        
    # Intercept memory writes before storage
    def record_memory(self, agent_id, content, memory_type, sensitivity) -> AuditRecord:
        """Apply policy: type validation, TTL assignment, scope enforcement"""
        
    # Expose kill switch state to framework
    def check_agent_enabled(self, agent_id) -> bool:
        """Return True if writes allowed, False if frozen/disabled"""
        
    # Provide audit context for framework logs
    def audit_context(self, agent_id, request_id) -> AuditContext:
        """Return immutable context for framework to include in its own logs"""
```

### Adapter Responsibilities
- **Non-invasive**: Framework code remains unaware of governance
- **Interception points**: Hook at memory read/write boundaries only
- **No policy logic in framework**: All decisions delegated to AMG
- **Deterministic passthrough**: Framework sees same behavior regardless of governance state
- **Audit integration**: All framework actions traceable in AMG audit log

### Example: LangGraph Adapter Integration
```
adapters/langgraph/
├── __init__.py
├── context_builder.py      # Wraps graph state → governed context
├── memory_callback.py      # Intercepts graph.put_memory() calls
├── kill_switch_check.py    # Checks agent state before execution
├── audit_integration.py    # Ensures graph execution is audit-logged
└── test_langgraph_adapter.py
```

### Pattern: Minimal Intrusion
Framework adapters should not:
- Add reasoning steps to agent workflows
- Modify agent messages or tool outputs
- Implement policy decisions (delegate to AMG)
- Cache governance decisions (always check current state)

---

## Kill Switch & Incident Response Pattern

The kill switch is a **mandatory enterprise control**. It must be:
- **Instant** (no queues, no async)
- **Idempotent** (safe to call multiple times)
- **Non-bypassable** (enforcement happens outside agent code)
- **Audited** (every invocation recorded with actor and reason)

### API Contract
```http
POST /agent/{agent_id}/disable
  Headers: Authorization, X-Reason
  Response: 
    {
      "status": "disabled",
      "timestamp": "2025-02-02T...",
      "audit_id": "...",
      "mode": "read_only | frozen | shutdown"
    }

POST /agent/{agent_id}/status
  Response:
    {
      "agent_id": "...",
      "state": "enabled | disabled | frozen",
      "memory_write": "allowed | frozen",
      "disabled_at": "...",
      "disabled_by": "..."
    }
```

### Implementation Pattern
```python
class KillSwitch:
    # Check state before ANY memory operation
    def check_allowed(self, agent_id, operation_type) -> bool:
        """Returns True if operation permitted, False otherwise"""
        
    # Disable agent (audit recorded first, then enforcement)
    def disable(self, agent_id, reason, actor_id) -> AuditRecord:
        """Disable and return immutable audit record"""
        
    # Freeze writes but allow reads (human-in-the-loop)
    def freeze_writes(self, agent_id, reason, actor_id) -> AuditRecord
        
    # Emergency: global shutdown
    def global_shutdown(self, reason, actor_id) -> AuditRecord
```

### Enforcement Guarantees
- Disable check happens **before** any memory operation (not after)
- State is read from persistent store, not in-memory (prevents timing races)
- Every state change is immutable and audit-logged
- Read operations allowed after disable (for reflection/analysis)
- Write operations fail fast with clear error

---

## Governed Context Builder Pattern

The context builder is the **single gateway** through which agents receive memory. It enforces all governance before context reaches the agent.

### Request/Response Contract
```http
POST /context/build
  Body:
    {
      "agent_id": "agent-123",
      "request_id": "req-abc...",
      "filters": {
        "memory_types": ["long_term", "episodic"],
        "scope": "agent",
        "max_items": 50
      }
    }
  
  Response:
    {
      "context": [
        {
          "memory_id": "mem-xyz",
          "content": "...",
          "type": "long_term",
          "created_at": "2025-02-01T...",
          "expires_at": "2025-02-15T..."
        }
      ],
      "metadata": {
        "token_count": 1234,
        "filtered_count": 5,
        "audit_id": "audit-...",
        "policy_version": "1.2.0"
      }
    }
```

### Enforcement Layer (In Order)
1. **Agent identity validation**: Confirm agent exists and is enabled
2. **Kill switch check**: Reject if agent is disabled/frozen
3. **Memory-type filtering**: Return only requested types
4. **TTL enforcement**: Exclude expired memory, mark expiring soon
5. **Sensitivity filtering**: Exclude memory agent has no permission to read
6. **Scope isolation**: Respect agent vs. tenant boundaries
7. **Token budget**: Cap context size to prevent prompt injection
8. **Audit logging**: Record what was requested, what was filtered, why

### Key Invariants
- **Never returns unauthorized memory**: Policy filtering is non-optional
- **Deterministic filtering**: Same agent + same request = same context (for reproducibility)
- **Visible filtering**: Metadata includes `filtered_count` so agent can know governance acted
- **No caching of decisions**: Always re-evaluate TTL, sensitivity, scope at retrieval time
- **Immutable response**: Once returned, context must not be invalidated retroactively (timestamp immutability)

---

## Audit Log Requirements

Audit logs are the **source of truth** for compliance, replay, and incident analysis. They must be immutable, complete, and queryable.

### AuditRecord Schema
```python
class AuditRecord:
    audit_id: str                    # Unique, immutable identifier
    timestamp: datetime              # When decision was made (UTC, server time)
    agent_id: str                    # Which agent took action
    request_id: str                  # Request context for tracing
    operation: str                   # write | read | query | disable | freeze
    memory_id: str                   # What memory was affected (nullable for queries)
    policy_version: str              # Which policy ruled this action
    decision: str                    # allowed | denied | filtered
    reason: str                      # Why decision was made (e.g., "pii_sensitivity", "expired_ttl")
    actor_id: str                    # Who triggered this (agent_id for normal ops, admin_id for kill switch)
    metadata: dict                   # Extra context (e.g., filtered_count, token_budget_remaining)
    signature: str                   # HMAC/signature (prevents tampering)
```

### Immutability Guarantees
- **Write-once**: Audit records are inserted, never updated or deleted
- **Append-only**: New records only added to end, never reordered
- **Timestamped**: All times are server UTC, monotonically increasing
- **Signed**: Each record includes cryptographic signature preventing tampering
- **Queryable but not mutable**: Agents can read audit logs for reflection, never modify

### Retention & Compliance
```yaml
audit_retention:
  default_ttl: 2592000  # 30 days
  pii_operations: 7776000  # 90 days (GDPR: right to audit)
  incident_related: 31536000  # 1 year (incident forensics)
  deletion_policy: hard_delete  # Not soft-delete (compliance requirement)
```

### Audit Query API
```http
GET /audit?agent_id=agent-123&start=2025-02-01&end=2025-02-02
  Response:
    {
      "records": [...],
      "count": 245,
      "earliest": "2025-02-01T...",
      "latest": "2025-02-02T...",
      "signature_verified": true
    }

POST /audit/replay
  Body:
    {
      "start_audit_id": "audit-abc",
      "end_audit_id": "audit-xyz"
    }
  Response:
    {
      "decisions": [...]
    }
```

### Testing Audit Integrity
Every implementation must verify:
1. **No silent failures**: Every decision produces audit record
2. **No gaps**: Audit IDs are sequential (no missing records)
3. **Immutability**: Records cannot be altered after creation
4. **Completeness**: All critical paths (write, read, filter, disable) logged
5. **Queryability**: Audit logs can be retrieved for compliance audits

---

## Policy Engine Extension Pattern

Policy extensions customize governance rules **without changing core enforcement**. Extensions are **declarative and schema-compliant**.

### Non-Bypassable Design
- Agents cannot define or modify policy
- Policy is applied at governance boundary, not in application logic
- Extensions validate against POLICY_SCHEMA (no custom shapes in V1)

### Extension Points (Conservative)
1. **Memory classification**: Custom logic to assign type/sensitivity to new memory
2. **TTL calculation**: Custom rules for retention (e.g., "PII expires in 7 days, non-PII in 90")
3. **Sensitivity tagging**: Declare what is PII without auto-detection
4. **Retention decay**: Schedule memory for deletion (episodic memory patterns)
5. **Context filtering**: Custom filters in governed context builder (per-agent rules)

### Example: TTL Policy Extension
```python
class TTLPolicyExtension:
    """Custom TTL rules without bypassing core enforcement"""
    
    def calculate_ttl(self, memory, sensitivity, scope) -> int:
        """Return TTL in seconds. Core engine enforces regardless."""
        if sensitivity == "pii" and scope == "tenant":
            return 604800  # 7 days
        elif sensitivity == "non_pii":
            return 2592000  # 30 days
        else:
            return 86400   # 1 day default
```

### Pattern: Policy-as-Config
Extensions should expose configuration, not code:
```yaml
policies:
  ttl:
    pii_agent_scope: 86400        # 1 day
    pii_tenant_scope: 604800      # 7 days
    non_pii_agent_scope: 2592000  # 30 days
    non_pii_tenant_scope: 7776000 # 90 days
    default: 86400
    
  context_budget:
    max_tokens: 4000
    max_memory_items: 50
    
  sensitivity_tags:
    pii_patterns:
      - email_address
      - credit_card
      - phone_number
    non_pii_patterns:
      - timestamp
      - user_count
```

### Extension Testing
Every policy extension must test:
1. **Determinism**: Same input always produces same output
2. **Auditability**: Decisions are loggable
3. **Non-bypass**: Agents cannot circumvent the rule
4. **Scope isolation**: Rules respect agent vs. tenant boundaries

---

## When in Doubt
1. Check if the feature improves agent reasoning → Out of scope, will be rejected
2. Check if it requires hiding behavior from audit logs → Out of scope
3. Check if agents can bypass it → Needs redesign
4. Check if it changes policy semantics → Requires discussion/RFC
5. Ask: *Does governance get stronger or weaker?* → Use that as your north star

---

## Non-Goals (Explicitly Intentional)
- Reasoning, planning, or learning
- Multi-agent coordination
- Dashboards or UIs
- Auto-detection of sensitive data
- Breaking changes without RFCs
