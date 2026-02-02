# Phase 5: HTTP API Layer

## Overview

Phase 5 delivers a complete REST API for Agent Memory Governance, enabling language-agnostic integration and out-of-process access to AMG governance controls.

The API exposes all core AMG operations through HTTP endpoints:
- **Memory Management** (write, query)
- **Context Building** (governed context assembly)
- **Audit Logs** (retrieve governance decisions)
- **Kill Switch** (disable/freeze agents, get status)
- **Health Checks** (service monitoring)

## Quick Start

### Running the Server

```bash
# Install dependencies
pip install fastapi uvicorn pydantic httpx

# Run the server
python3 run_api.py
# or
python3 run_api.py --host 0.0.0.0 --port 8080
```

The API will be available at:
- **Interactive Docs**: http://localhost:8000/docs (Swagger UI)
- **OpenAPI Schema**: http://localhost:8000/openapi.json
- **API Root**: http://localhost:8000

### Testing the API

```bash
# Health check
curl http://localhost:8000/health

# Write memory
curl -X POST http://localhost:8000/memory/write \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-123",
    "content": "Important data",
    "memory_type": "long_term",
    "sensitivity": "non_pii"
  }'

# Query memories
curl -X POST http://localhost:8000/memory/query \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-123"
  }'

# Build context
curl -X POST http://localhost:8000/context/build \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-123",
    "max_tokens": 4000
  }'
```

## API Reference

### Health Check

**GET /health**

Service health status.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2025-02-02T14:30:00Z"
}
```

---

### Memory Write

**POST /memory/write**

Write memory with automatic policy enforcement and TTL assignment.

**Request:**
```json
{
  "agent_id": "agent-123",
  "content": "User provided email: user@example.com",
  "memory_type": "episodic",
  "sensitivity": "pii",
  "scope": "agent",
  "ttl_seconds": 604800  // optional, auto-assigned if not provided
}
```

**Parameters:**
- `agent_id` (string, required): Agent identifier
- `content` (string, required): Memory content
- `memory_type` (string, required): `short_term` | `long_term` | `episodic`
- `sensitivity` (string, required): `pii` | `non_pii`
- `scope` (string, optional, default: "agent"): `agent` | `tenant`
- `ttl_seconds` (integer, optional): Custom TTL in seconds. If omitted, auto-assigned based on sensitivity/scope

**TTL Assignment (auto):**
| Sensitivity | Scope  | TTL       |
|-------------|--------|-----------|
| pii         | agent  | 86400 (1d)|
| pii         | tenant | 604800 (7d)|
| non_pii     | agent  | 2592000 (30d)|
| non_pii     | tenant | 7776000 (90d)|

**Response (200 OK):**
```json
{
  "memory_id": "mem-abc123xyz",
  "audit_id": "audit-def456uvw",
  "decision": "allowed"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid memory_type, sensitivity, or scope
- `423 Locked`: Agent is disabled or frozen
- `403 Forbidden`: Policy enforcement failed

---

### Memory Query

**POST /memory/query**

Query memories with policy enforcement at retrieval time.

**Request:**
```json
{
  "agent_id": "agent-123",
  "memory_types": ["long_term", "episodic"],  // optional
  "sensitivity": "non_pii",                    // optional
  "scope": "agent",                            // optional
  "limit": 50                                  // optional, default: 50, max: 500
}
```

**Response (200 OK):**
```json
{
  "memories": [
    {
      "memory_id": "mem-abc",
      "content": "Memory content",
      "memory_type": "long_term",
      "sensitivity": "non_pii",
      "scope": "agent",
      "created_at": "2025-02-01T10:00:00Z",
      "expires_at": "2025-03-03T10:00:00Z"
    }
  ],
  "metadata": {
    "total": 1,
    "filtered": 0,
    "audit_id": "audit-xyz"
  }
}
```

**Governance Applied:**
- ✅ TTL enforcement (expired memories excluded)
- ✅ Sensitivity filtering (agent cannot read unauthorized)
- ✅ Scope isolation (agent-scoped memories only)
- ✅ Audit logging (all queries recorded)

---

### Build Context

**POST /context/build**

Build governed context for agent consumption.

**Request:**
```json
{
  "agent_id": "agent-123",
  "memory_types": ["long_term"],    // optional
  "max_tokens": 4000,                // optional, default: 4000
  "max_items": 50                    // optional, default: 50
}
```

**Response (200 OK):**
```json
{
  "memories": [
    {
      "memory_id": "mem-xyz",
      "content": "Important data",
      "memory_type": "long_term",
      "sensitivity": "non_pii",
      "scope": "agent",
      "created_at": "2025-02-01T10:00:00Z",
      "expires_at": "2025-03-03T10:00:00Z"
    }
  ],
  "metadata": {
    "token_count": 1234,
    "filtered_count": 5,
    "policy_version": "1.0.0"
  }
}
```

**Enforcement Pipeline:**
1. Agent identity validation
2. Kill switch check
3. Memory-type filtering
4. TTL enforcement
5. Sensitivity filtering
6. Scope isolation
7. Token budget enforcement
8. Audit logging

**Error Responses:**
- `423 Locked`: Agent is disabled
- `403 Forbidden`: Policy enforcement failed

---

### Get Audit Log

**GET /audit/{audit_id}**

Retrieve audit records for a governance decision.

**Response (200 OK):**
```json
{
  "records": [
    {
      "audit_id": "audit-abc",
      "timestamp": "2025-02-02T14:30:00Z",
      "agent_id": "agent-123",
      "operation": "write",
      "decision": "allowed",
      "reason": "policy_enforcement_passed",
      "memory_id": "mem-xyz",
      "metadata": {
        "memory_type": "long_term",
        "sensitivity": "non_pii",
        "scope": "agent",
        "ttl_seconds": 2592000
      }
    }
  ],
  "count": 1
}
```

**Error Responses:**
- `404 Not Found`: Audit record not found

---

### Disable Agent

**POST /agent/{agent_id}/disable**

Immediately disable an agent (kill switch).

**Query Parameters:**
- `reason` (string, optional): Reason for disabling
- `actor_id` (string, optional, default: "api"): Who triggered disable

**Response (200 OK):**
```json
{
  "agent_id": "agent-123",
  "status": "disabled",
  "timestamp": "2025-02-02T14:30:00Z",
  "audit_id": "audit-xyz"
}
```

**Effect:**
- Agent can no longer read or write memory
- All memory operations blocked
- Audit trail recorded
- Status can be checked with GET /agent/{id}/status

---

### Freeze Agent Writes

**POST /agent/{agent_id}/freeze**

Freeze memory writes (read-only mode) for incident response.

**Query Parameters:**
- `reason` (string, optional): Reason for freezing
- `actor_id` (string, optional, default: "api"): Who triggered freeze

**Response (200 OK):**
```json
{
  "agent_id": "agent-123",
  "status": "frozen",
  "timestamp": "2025-02-02T14:30:00Z",
  "audit_id": "audit-xyz"
}
```

**Effect:**
- Agent can read existing memory
- Agent cannot write new memory
- Useful for incident investigation
- Can later upgrade to full disable if needed

---

### Get Agent Status

**GET /agent/{agent_id}/status**

Get current governance state of an agent.

**Response (200 OK):**
```json
{
  "agent_id": "agent-123",
  "state": "enabled",  // enabled | disabled | frozen
  "memory_write": "allowed",  // allowed | frozen
  "disabled_at": null
}
```

**States:**
- `enabled`: Normal operation, all memory operations allowed
- `disabled`: All operations blocked
- `frozen`: Reads allowed, writes blocked

---

## Examples

### Example 1: Complete Workflow

```bash
# 1. Write memory
WRITE_RESPONSE=$(curl -s -X POST http://localhost:8000/memory/write \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-abc",
    "content": "Important insight",
    "memory_type": "long_term",
    "sensitivity": "non_pii"
  }')

MEMORY_ID=$(echo $WRITE_RESPONSE | jq -r '.memory_id')
echo "Memory written: $MEMORY_ID"

# 2. Query memory
curl -s -X POST http://localhost:8000/memory/query \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-abc"
  }' | jq .

# 3. Build context
curl -s -X POST http://localhost:8000/context/build \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-abc",
    "max_tokens": 4000
  }' | jq .
```

### Example 2: Incident Response

```bash
# Detect problem, freeze writes
curl -X POST http://localhost:8000/agent/agent-problematic/freeze \
  -G --data-urlencode "reason=suspicious_pattern_detected" \
  -G --data-urlencode "actor_id=security-monitor"

# Check status
curl -s http://localhost:8000/agent/agent-problematic/status | jq .

# Agent can still read for investigation
curl -s -X POST http://localhost:8000/context/build \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent-problematic"}' | jq .

# If confirmed as threat, disable
curl -X POST http://localhost:8000/agent/agent-problematic/disable \
  -G --data-urlencode "reason=confirmed_malicious_behavior" \
  -G --data-urlencode "actor_id=security-admin"
```

### Example 3: Multi-Agent Isolation Verification

```bash
# Agent A writes
curl -X POST http://localhost:8000/memory/write \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-a",
    "content": "Agent A data",
    "memory_type": "long_term",
    "sensitivity": "non_pii"
  }'

# Agent B writes
curl -X POST http://localhost:8000/memory/write \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-b",
    "content": "Agent B data",
    "memory_type": "long_term",
    "sensitivity": "non_pii"
  }'

# Agent A queries - sees only its memory
curl -s -X POST http://localhost:8000/memory/query \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent-a"}' | jq '.memories[0].content'
# Output: "Agent A data"

# Agent B queries - sees only its memory
curl -s -X POST http://localhost:8000/memory/query \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent-b"}' | jq '.memories[0].content'
# Output: "Agent B data"
```

---

## Deployment

### Local Development

```bash
pip install -e .
python3 run_api.py --reload  # Auto-reload on changes
```

### Production

```bash
# Install dependencies
pip install fastapi uvicorn pydantic

# Run with gunicorn/uvicorn
uvicorn src.amg.api.server:create_app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY . .

RUN pip install -e . && pip install fastapi uvicorn

EXPOSE 8000
CMD ["python3", "run_api.py", "--host", "0.0.0.0"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  amg-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PYTHONUNBUFFERED=1
    volumes:
      - ./:/app  # for development
```

---

## Test Coverage

Phase 5 includes **28 comprehensive HTTP API tests**:

**Test Categories:**
- HealthCheck (1 test)
- MemoryWrite (6 tests) - success, PII handling, TTL, validation
- MemoryQuery (4 tests) - empty, after write, filtering, limits
- ContextBuild (5 tests) - success, empty, filters, budgets, items
- AuditLog (2 tests) - not found, after write
- KillSwitch (6 tests) - disable, freeze, status, write blocking, read allowing
- Integration (4 tests) - full workflows, incident response, multi-agent isolation

**All tests passing:** 28/28 ✅

Run tests:
```bash
python3 -m pytest tests/test_api.py -v
```

---

## Error Handling

All errors return appropriate HTTP status codes:

| Status | Meaning | When |
|--------|---------|------|
| 200 | Success | Operation allowed and completed |
| 400 | Bad Request | Invalid parameters or types |
| 403 | Forbidden | Policy enforcement failed |
| 404 | Not Found | Resource not found (audit log, etc.) |
| 423 | Locked | Agent disabled or frozen |
| 503 | Service Unavailable | Service unhealthy |

**Example Error Response:**
```json
{
  "detail": "Agent disabled: Write not allowed: agent_frozen_write_denied"
}
```

---

## Security Considerations

1. **No Authentication** (Phase 5)
   - API assumes trust network (internal deployment)
   - Phase 5+ will add API key authentication

2. **All Operations Audited**
   - Every request logged with immutable records
   - Governance decisions traceable

3. **Kill Switch Instant**
   - No queues or delays
   - Immediate enforcement

4. **Memory Isolation**
   - Agents cannot read other agents' memory
   - Scope boundaries enforced at API layer

---

## Future Enhancements

### Phase 5+ Roadmap
- [ ] API authentication (API keys, OAuth2)
- [ ] Rate limiting
- [ ] Request signing for audit trail
- [ ] Batch operations support
- [ ] WebSocket support for streaming context
- [ ] GraphQL endpoint option
- [ ] API versioning

---

## Files

- [src/amg/api/__init__.py](../src/amg/api/__init__.py) - API module init
- [src/amg/api/server.py](../src/amg/api/server.py) - FastAPI application (467 lines)
- [tests/test_api.py](../tests/test_api.py) - API tests (529 lines, 28 tests)
- [run_api.py](../run_api.py) - API server runner

---

## Summary

Phase 5 delivers a production-grade HTTP API for AMG, enabling:

✅ **Language-agnostic integration** - any language can call HTTP endpoints  
✅ **Out-of-process deployment** - separate API service from agents  
✅ **Full governance enforcement** - kill switch, context curation, audit logging  
✅ **Comprehensive testing** - 28 tests with 100% pass rate  
✅ **Clear documentation** - API reference, examples, deployment guides  

With 132 total tests passing (104 core + 28 API), AMG is now a complete governance platform with both Python SDK and HTTP API interfaces.

**Status:** ✅ Phase 5 Complete - Production Ready
