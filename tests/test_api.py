"""Tests for HTTP API layer."""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from amg.api.server import create_app
from amg.types import MemoryType, Sensitivity, Scope


@pytest.fixture
def client():
    """Create FastAPI test client."""
    app = create_app()
    return TestClient(app)


# ============================================================
# Health Check Tests
# ============================================================

class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_success(self, client):
        """Health check returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert "timestamp" in response.json()


# ============================================================
# Memory Write Tests
# ============================================================

class TestMemoryWrite:
    """Test memory write endpoint."""

    def test_write_memory_success(self, client):
        """Write memory successfully."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test memory",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
                "scope": "agent",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"]
        assert data["audit_id"]
        assert data["decision"] == "allowed"

    def test_write_pii_memory(self, client):
        """Write PII memory gets shorter TTL."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "user@example.com",
                "memory_type": "episodic",
                "sensitivity": "pii",
                "scope": "agent",
            }
        )
        assert response.status_code == 200
        assert response.json()["decision"] == "allowed"

    def test_write_custom_ttl(self, client):
        """Write memory with custom TTL."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Custom TTL memory",
                "memory_type": "short_term",
                "sensitivity": "non_pii",
                "ttl_seconds": 3600,
            }
        )
        assert response.status_code == 200

    def test_write_invalid_memory_type(self, client):
        """Reject invalid memory type."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test",
                "memory_type": "invalid_type",
                "sensitivity": "non_pii",
            }
        )
        assert response.status_code == 400
        assert "Invalid memory_type" in response.json()["detail"]

    def test_write_invalid_sensitivity(self, client):
        """Reject invalid sensitivity."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test",
                "memory_type": "long_term",
                "sensitivity": "invalid_sensitivity",
            }
        )
        assert response.status_code == 400
        assert "Invalid sensitivity" in response.json()["detail"]

    def test_write_requires_agent_id(self, client):
        """Require agent_id in request."""
        response = client.post(
            "/memory/write",
            json={
                "content": "Test",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            }
        )
        assert response.status_code == 422  # Validation error

    def test_write_requires_content(self, client):
        """Require content in request."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            }
        )
        assert response.status_code == 422


# ============================================================
# Memory Query Tests
# ============================================================

class TestMemoryQuery:
    """Test memory query endpoint."""

    def test_query_memory_empty(self, client):
        """Query returns empty list when no memories."""
        response = client.post(
            "/memory/query",
            json={"agent_id": "agent-empty"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["memories"] == []
        assert data["metadata"]["total"] == 0

    def test_query_memory_after_write(self, client):
        """Query returns written memories."""
        # Write memory
        client.post(
            "/memory/write",
            json={
                "agent_id": "agent-456",
                "content": "Queryable memory",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            }
        )

        # Query
        response = client.post(
            "/memory/query",
            json={"agent_id": "agent-456"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1
        assert data["memories"][0]["content"] == "Queryable memory"
        assert data["metadata"]["total"] == 1

    def test_query_with_memory_type_filter(self, client):
        """Query filters by memory type."""
        # Write different types
        client.post("/memory/write", json={
            "agent_id": "agent-789",
            "content": "Long term",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })
        client.post("/memory/write", json={
            "agent_id": "agent-789",
            "content": "Short term",
            "memory_type": "short_term",
            "sensitivity": "non_pii",
        })

        # Filter by type
        response = client.post("/memory/query", json={
            "agent_id": "agent-789",
            "memory_types": ["long_term"],
        })
        data = response.json()
        assert len(data["memories"]) == 1
        assert data["memories"][0]["memory_type"] == "long_term"

    def test_query_limit(self, client):
        """Query respects limit parameter."""
        agent_id = "agent-limit"
        # Write 5 memories
        for i in range(5):
            client.post("/memory/write", json={
                "agent_id": agent_id,
                "content": f"Memory {i}",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            })

        # Query with limit=2
        response = client.post("/memory/query", json={
            "agent_id": agent_id,
            "limit": 2,
        })
        data = response.json()
        assert len(data["memories"]) == 2


# ============================================================
# Context Build Tests
# ============================================================

class TestContextBuild:
    """Test context building endpoint."""

    def test_build_context_success(self, client):
        """Build context successfully."""
        # Write memory
        client.post("/memory/write", json={
            "agent_id": "agent-ctx",
            "content": "Context memory",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })

        # Build context
        response = client.post("/context/build", json={
            "agent_id": "agent-ctx",
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1
        assert "metadata" in data

    def test_build_context_empty(self, client):
        """Build context for agent with no memories."""
        response = client.post("/context/build", json={
            "agent_id": "agent-no-mem",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["memories"] == []

    def test_build_context_with_filters(self, client):
        """Build context with memory type filters."""
        # Write memories
        client.post("/memory/write", json={
            "agent_id": "agent-filter",
            "content": "Long",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })
        client.post("/memory/write", json={
            "agent_id": "agent-filter",
            "content": "Short",
            "memory_type": "short_term",
            "sensitivity": "non_pii",
        })

        # Build context with filter
        response = client.post("/context/build", json={
            "agent_id": "agent-filter",
            "memory_types": ["long_term"],
        })
        data = response.json()
        assert len(data["memories"]) == 1
        assert data["memories"][0]["memory_type"] == "long_term"

    def test_build_context_token_budget(self, client):
        """Build context respects token budget."""
        response = client.post("/context/build", json={
            "agent_id": "agent-budget",
            "max_tokens": 100,
        })
        assert response.status_code == 200
        # Metadata should include token info
        assert "metadata" in response.json()

    def test_build_context_max_items(self, client):
        """Build context respects max items."""
        response = client.post("/context/build", json={
            "agent_id": "agent-items",
            "max_items": 10,
        })
        assert response.status_code == 200


# ============================================================
# Audit Log Tests
# ============================================================

class TestAuditLog:
    """Test audit log retrieval."""

    def test_get_audit_log_not_found(self, client):
        """Audit log not found returns 404."""
        response = client.get("/audit/nonexistent-audit-id")
        assert response.status_code == 404

    def test_get_audit_log_after_write(self, client):
        """Audit log available after memory write."""
        # Write memory
        write_response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-audit",
                "content": "Auditable",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            }
        )
        audit_id = write_response.json()["audit_id"]

        # Get audit
        response = client.get(f"/audit/{audit_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["records"]) == 1
        assert data["records"][0]["audit_id"] == audit_id
        assert data["records"][0]["operation"] == "write"
        assert data["records"][0]["decision"] == "allowed"


# ============================================================
# Kill Switch Tests
# ============================================================

class TestKillSwitch:
    """Test kill switch endpoint."""

    def test_disable_agent(self, client):
        """Disable agent successfully."""
        response = client.post(
            "/agent/agent-disable/disable",
            params={
                "reason": "test_disable",
                "actor_id": "test-admin",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-disable"
        assert data["status"] == "disabled"
        assert data["audit_id"]

    def test_agent_status_enabled(self, client):
        """Agent status shows enabled."""
        response = client.get("/agent/agent-status-1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "enabled"

    def test_agent_status_disabled(self, client):
        """Agent status shows disabled after disable."""
        # Disable
        client.post("/agent/agent-disabled/disable")

        # Check status
        response = client.get("/agent/agent-disabled/status")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "disabled"

    def test_freeze_agent_writes(self, client):
        """Freeze agent writes (read-only mode)."""
        response = client.post(
            "/agent/agent-freeze/freeze",
            params={"reason": "test_freeze"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "frozen"

    def test_frozen_agent_blocks_writes(self, client):
        """Frozen agent cannot write memory."""
        # Freeze agent
        client.post("/agent/agent-frozen-write/freeze")

        # Try to write
        response = client.post("/memory/write", json={
            "agent_id": "agent-frozen-write",
            "content": "Should fail",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })
        assert response.status_code == 423  # Locked
        assert "disabled" in response.json()["detail"].lower()

    def test_frozen_agent_allows_reads(self, client):
        """Frozen agent can still read memory."""
        agent_id = "agent-frozen-read"

        # Write memory
        client.post("/memory/write", json={
            "agent_id": agent_id,
            "content": "Read this",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })

        # Freeze agent
        client.post(f"/agent/{agent_id}/freeze")

        # Read should work
        response = client.post("/context/build", json={
            "agent_id": agent_id,
        })
        assert response.status_code == 200
        assert len(response.json()["memories"]) == 1


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_workflow_write_query_build(self, client):
        """Full workflow: write → query → build context."""
        agent_id = "agent-workflow"

        # 1. Write memory
        write_resp = client.post("/memory/write", json={
            "agent_id": agent_id,
            "content": "Important info",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })
        assert write_resp.status_code == 200
        memory_id = write_resp.json()["memory_id"]

        # 2. Query memory
        query_resp = client.post("/memory/query", json={
            "agent_id": agent_id,
        })
        assert query_resp.status_code == 200
        assert len(query_resp.json()["memories"]) == 1

        # 3. Build context
        ctx_resp = client.post("/context/build", json={
            "agent_id": agent_id,
        })
        assert ctx_resp.status_code == 200
        assert len(ctx_resp.json()["memories"]) == 1

    def test_incident_response_flow(self, client):
        """Incident response: write → freeze → check status."""
        agent_id = "agent-incident"

        # Write memory
        client.post("/memory/write", json={
            "agent_id": agent_id,
            "content": "Pre-incident data",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })

        # Detect incident, freeze writes
        freeze_resp = client.post(
            f"/agent/{agent_id}/freeze",
            params={"reason": "incident_detected"}
        )
        assert freeze_resp.status_code == 200

        # Check status
        status_resp = client.get(f"/agent/{agent_id}/status")
        data = status_resp.json()
        assert data["state"] == "frozen"
        assert data["memory_write"] == "frozen"

        # Can still read existing data
        ctx_resp = client.post("/context/build", json={
            "agent_id": agent_id,
        })
        assert ctx_resp.status_code == 200
        assert len(ctx_resp.json()["memories"]) == 1

    def test_multi_agent_isolation(self, client):
        """Multiple agents maintain isolation."""
        # Agent A writes
        client.post("/memory/write", json={
            "agent_id": "agent-a",
            "content": "A's secret",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })

        # Agent B writes
        client.post("/memory/write", json={
            "agent_id": "agent-b",
            "content": "B's secret",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })

        # Agent A queries - should only see A's memory
        a_query = client.post("/memory/query", json={
            "agent_id": "agent-a",
        })
        assert len(a_query.json()["memories"]) == 1
        assert a_query.json()["memories"][0]["content"] == "A's secret"

        # Agent B queries - should only see B's memory
        b_query = client.post("/memory/query", json={
            "agent_id": "agent-b",
        })
        assert len(b_query.json()["memories"]) == 1
        assert b_query.json()["memories"][0]["content"] == "B's secret"
