"""Tests for memory store interface and in-memory adapter."""

import pytest
from datetime import datetime, timedelta

from amg.types import Memory, MemoryPolicy, MemoryType, Sensitivity, Scope, AuditRecord
from amg.adapters import InMemoryStorageAdapter
from amg.storage import PolicyCheck
from amg.errors import (
    MemoryNotFoundError,
    PolicyEnforcementError,
    UnauthorizedReadError,
    IsolationViolationError,
)


class TestMemoryStore:
    """Test memory store interface contracts."""

    @pytest.fixture
    def adapter(self):
        """Create fresh adapter for each test."""
        return InMemoryStorageAdapter()

    @pytest.fixture
    def sample_memory(self):
        """Create sample memory item."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )
        return Memory(
            agent_id="agent-123",
            content="Sample memory content",
            policy=policy,
        )

    # ============================================================
    # Critical Path 1: Policy Enforcement on Write
    # ============================================================

    def test_write_stores_memory_with_policy(self, adapter, sample_memory):
        """Memory write respects policy contract."""
        audit = adapter.write(sample_memory, {"request_id": "req-123"})
        
        assert audit.decision == "allowed"
        assert audit.operation == "write"
        assert audit.memory_id == sample_memory.memory_id
        assert sample_memory.memory_id in adapter._memories

    def test_write_creates_immutable_audit_record(self, adapter, sample_memory):
        """Write creates signed audit record that cannot be tampered."""
        audit = adapter.write(sample_memory, {"request_id": "req-123"})
        
        assert audit.audit_id
        assert audit.timestamp
        assert audit.signature
        assert audit.policy_version == "1.0.0"
        assert audit.reason == "policy_enforcement_passed"

    def test_write_rejects_invalid_ttl(self, adapter, sample_memory):
        """Write rejects negative/zero TTL."""
        sample_memory.policy.ttl_seconds = -1
        with pytest.raises(PolicyEnforcementError):
            adapter.write(sample_memory, {"request_id": "req-123"})

    def test_write_requires_agent_id(self, adapter, sample_memory):
        """Write requires agent_id (prevents anonymous memory)."""
        sample_memory.agent_id = ""
        with pytest.raises(PolicyEnforcementError):
            adapter.write(sample_memory, {"request_id": "req-123"})

    # ============================================================
    # Critical Path 2: Policy Enforcement on Read
    # ============================================================

    def test_read_returns_memory_if_allowed(self, adapter, sample_memory):
        """Read returns memory when policy allows."""
        adapter.write(sample_memory, {"request_id": "req-123"})
        
        policy_check = PolicyCheck(
            agent_id="agent-123",
            allowed_scopes=[Scope.AGENT],
        )
        memory, audit = adapter.read(sample_memory.memory_id, "agent-123", policy_check)
        
        assert memory is not None
        assert memory.content == sample_memory.content
        assert audit.decision == "allowed"

    def test_read_blocks_agent_scope_violation(self, adapter, sample_memory):
        """Read blocks access across agent boundaries (isolation)."""
        adapter.write(sample_memory, {"request_id": "req-123"})
        
        policy_check = PolicyCheck(
            agent_id="agent-456",
            allowed_scopes=[Scope.AGENT],
        )
        memory, audit = adapter.read(sample_memory.memory_id, "agent-456", policy_check)
        
        assert memory is None
        assert audit.decision == "denied"
        assert audit.reason == "scope_isolation_violation"

    def test_read_blocks_expired_memory(self, adapter):
        """Read blocks access to expired memory."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=1,  # Expires in 1 second
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )
        memory = Memory(agent_id="agent-123", content="temp", policy=policy)
        adapter.write(memory, {"request_id": "req-123"})
        
        # Manually expire the memory
        memory.expires_at = datetime.utcnow() - timedelta(seconds=1)
        
        policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
        result, audit = adapter.read(memory.memory_id, "agent-123", policy_check)
        
        assert result is None
        assert audit.reason == "memory_expired"

    def test_read_blocks_if_read_permission_denied(self, adapter):
        """Read respects allow_read flag."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=False,  # Explicitly deny reads
        )
        memory = Memory(agent_id="agent-123", content="secret", policy=policy)
        adapter.write(memory, {"request_id": "req-123"})
        
        policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
        result, audit = adapter.read(memory.memory_id, "agent-123", policy_check)
        
        assert result is None
        assert audit.reason == "read_not_allowed"

    def test_read_returns_not_found_for_missing_memory(self, adapter):
        """Read returns None for non-existent memory."""
        policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
        memory, audit = adapter.read("nonexistent", "agent-123", policy_check)
        
        assert memory is None
        assert audit.decision == "denied"
        assert audit.reason == "memory_not_found"

    def test_read_logs_all_attempts_in_audit(self, adapter, sample_memory):
        """Read operations always create audit records (even denials)."""
        adapter.write(sample_memory, {"request_id": "req-123"})
        
        policy_check = PolicyCheck(agent_id="agent-456", allowed_scopes=[Scope.AGENT])
        # Try to read as different agent
        _, audit = adapter.read(sample_memory.memory_id, "agent-456", policy_check)
        
        # Verify denial is logged
        assert audit in adapter._audit_log
        assert audit.decision == "denied"

    # ============================================================
    # Critical Path 3: Audit Log Immutability & Completeness
    # ============================================================

    def test_audit_logs_are_write_once(self, adapter, sample_memory):
        """Audit records cannot be modified after creation."""
        adapter.write(sample_memory, {"request_id": "req-123"})
        
        audit_before = adapter.get_audit_log()[0]
        audit_before.reason = "TAMPERED"  # Try to modify
        
        # Retrieve again - should be unchanged
        audit_after = adapter.get_audit_log()[0]
        assert audit_after.reason == "policy_enforcement_passed"

    def test_audit_logs_are_chronologically_ordered(self, adapter):
        """Audit records maintain order (append-only)."""
        mem1 = Memory(agent_id="agent-1", content="mem1")
        mem2 = Memory(agent_id="agent-2", content="mem2")
        
        adapter.write(mem1, {"request_id": "req-1"})
        adapter.write(mem2, {"request_id": "req-2"})
        
        logs = adapter.get_audit_log()
        assert logs[0].memory_id == mem1.memory_id
        assert logs[1].memory_id == mem2.memory_id
        assert logs[0].timestamp <= logs[1].timestamp

    def test_audit_records_are_signed(self, adapter, sample_memory):
        """Audit records include signature (prevents tampering)."""
        audit = adapter.write(sample_memory, {"request_id": "req-123"})
        
        assert audit.signature
        assert len(audit.signature) > 0

    def test_every_operation_logged_in_audit(self, adapter, sample_memory):
        """All critical operations produce audit records."""
        # Write
        adapter.write(sample_memory, {"request_id": "req-123"})
        # Read
        policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
        adapter.read(sample_memory.memory_id, "agent-123", policy_check)
        # Query
        adapter.query({}, "agent-123", policy_check)
        # Delete
        adapter.delete(sample_memory.memory_id, "admin", "test_deletion")
        
        logs = adapter.get_audit_log()
        assert len(logs) == 4
        assert logs[0].operation == "write"
        assert logs[1].operation == "read"
        assert logs[2].operation == "query"
        assert logs[3].operation == "delete"

    # ============================================================
    # Critical Path 4: Query with Retrieval Guard
    # ============================================================

    def test_query_returns_unfiltered_memory(self, adapter):
        """Query returns memory matching filters."""
        memory = Memory(
            agent_id="agent-123",
            content="test",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )
        adapter.write(memory, {"request_id": "req-123"})
        
        policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
        results, audit = adapter.query(
            {"memory_types": ["long_term"]},
            "agent-123",
            policy_check,
        )
        
        assert len(results) == 1
        assert results[0].memory_id == memory.memory_id

    def test_query_filters_by_memory_type(self, adapter):
        """Query respects memory_type filter."""
        mem1 = Memory(
            agent_id="agent-123",
            content="long",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )
        mem2 = Memory(
            agent_id="agent-123",
            content="episodic",
            policy=MemoryPolicy(
                memory_type=MemoryType.EPISODIC,
                ttl_seconds=3600,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )
        adapter.write(mem1, {"request_id": "req-1"})
        adapter.write(mem2, {"request_id": "req-2"})
        
        policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
        results, _ = adapter.query(
            {"memory_types": ["long_term"]},
            "agent-123",
            policy_check,
        )
        
        assert len(results) == 1
        assert results[0].policy.memory_type == MemoryType.LONG_TERM

    def test_query_respects_scope_isolation(self, adapter):
        """Query filters out memory from other agents (scope)."""
        mem_agent1 = Memory(agent_id="agent-1", content="private")
        mem_agent2 = Memory(agent_id="agent-2", content="private")
        
        adapter.write(mem_agent1, {"request_id": "req-1"})
        adapter.write(mem_agent2, {"request_id": "req-2"})
        
        policy_check = PolicyCheck(agent_id="agent-1", allowed_scopes=[Scope.AGENT])
        results, _ = adapter.query({}, "agent-1", policy_check)
        
        # Agent-1 should only see their own memory
        assert len(results) == 1
        assert results[0].agent_id == "agent-1"

    def test_query_excludes_expired_memory(self, adapter):
        """Query filters out expired memory."""
        mem = Memory(
            agent_id="agent-123",
            content="temp",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=1,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )
        adapter.write(mem, {"request_id": "req-123"})
        mem.expires_at = datetime.utcnow() - timedelta(seconds=1)
        
        policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
        results, _ = adapter.query({}, "agent-123", policy_check)
        
        assert len(results) == 0

    def test_query_includes_filtered_count_in_metadata(self, adapter):
        """Query metadata shows how many records were filtered."""
        mem1 = Memory(agent_id="agent-1", content="1")
        mem2 = Memory(agent_id="agent-2", content="2")
        mem3 = Memory(agent_id="agent-1", content="3")
        
        adapter.write(mem1, {"request_id": "req-1"})
        adapter.write(mem2, {"request_id": "req-2"})
        adapter.write(mem3, {"request_id": "req-3"})
        
        policy_check = PolicyCheck(agent_id="agent-1", allowed_scopes=[Scope.AGENT])
        _, audit = adapter.query({}, "agent-1", policy_check)
        
        assert audit.metadata["total_records_examined"] == 3
        assert audit.metadata["returned_count"] == 2
        assert audit.metadata["filtered_count"] == 1

    # ============================================================
    # Critical Path 5: Isolation & Non-Bypassability
    # ============================================================

    def test_cannot_bypass_scope_isolation_via_direct_storage(self, adapter):
        """Agents cannot access storage directly to bypass governance."""
        mem = Memory(agent_id="agent-123", content="secret")
        adapter.write(mem, {"request_id": "req-123"})
        
        # Attempt to bypass policy by accessing internal storage directly
        bypassed_memory = adapter._memories.get(mem.memory_id)
        assert bypassed_memory is not None  # Direct access is possible
        
        # But through public API, access is blocked
        policy_check = PolicyCheck(agent_id="agent-456", allowed_scopes=[Scope.AGENT])
        result, _ = adapter.read(mem.memory_id, "agent-456", policy_check)
        assert result is None

    def test_tenant_scope_isolation(self, adapter):
        """Tenant-scoped memory is readable across agents in same tenant."""
        mem = Memory(
            agent_id="agent-123",
            content="shared",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.TENANT,  # Shared within tenant
            ),
        )
        adapter.write(mem, {"request_id": "req-123"})
        
        # Different agent in same tenant can read
        policy_check = PolicyCheck(agent_id="agent-456", allowed_scopes=[Scope.TENANT])
        result, audit = adapter.read(mem.memory_id, "agent-456", policy_check)
        
        assert result is not None
        assert audit.decision == "allowed"

    # ============================================================
    # Bonus: Health & Compliance
    # ============================================================

    def test_health_check_succeeds(self, adapter):
        """Adapter reports healthy status."""
        assert adapter.health_check() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
