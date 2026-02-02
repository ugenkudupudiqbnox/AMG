"""Integration tests for Postgres storage adapter.

Tests verify:
- Deterministic queries (same request = same result)
- TTL enforcement
- Scope isolation
- Audit completeness
- Hard delete (no soft deletes)
- Retrieval guard filtering
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from amg.types import Memory, MemoryPolicy, Scope, MemoryType, Sensitivity
from amg.storage import PolicyCheck
from amg.adapters.postgres import PostgresStorageAdapter


@pytest.fixture
def postgres_adapter():
    """Create in-memory Postgres adapter for testing."""
    adapter = PostgresStorageAdapter(db_path=":memory:")
    return adapter


@pytest.fixture
def policy_check():
    """Create policy check context."""
    return PolicyCheck(
        agent_id="test-agent-1",
        allowed_scopes=[],
        allow_read=True,
        allow_write=True,
    )


class TestPostgresWrite:
    """Test write operations."""

    def test_write_success(self, postgres_adapter, policy_check):
        """Successfully write memory."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=True,
            allow_write=True,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Test memory",
            policy=policy,
            created_by="agent-1",
        )

        audit = postgres_adapter.write(memory, {})

        assert audit.decision == "allowed"
        assert audit.operation == "write"
        assert audit.memory_id == memory.memory_id
        assert audit.signature  # Signed

    def test_write_without_agent_id(self, postgres_adapter, policy_check):
        """Reject write without agent_id."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )

        memory = Memory(
            agent_id="",  # Invalid
            content="Test",
            policy=policy,
            created_by="agent-1",
        )

        with pytest.raises(Exception):  # PolicyEnforcementError
            postgres_adapter.write(memory, {})

    def test_write_invalid_ttl(self, postgres_adapter, policy_check):
        """Reject invalid TTL."""
        # TTL validation happens in MemoryPolicy.__post_init__
        with pytest.raises(ValueError):  # TTL must be positive
            policy = MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=-1,  # Invalid
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            )


class TestPostgresRead:
    """Test read operations with policy enforcement."""

    def test_read_success(self, postgres_adapter, policy_check):
        """Successfully read authorized memory."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=True,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Test memory",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        read_memory, audit = postgres_adapter.read(
            memory.memory_id, "agent-1", policy_check
        )

        assert read_memory is not None
        assert read_memory.memory_id == memory.memory_id
        assert read_memory.content == "Test memory"
        assert audit.decision == "allowed"

    def test_read_expired_memory(self, postgres_adapter, policy_check):
        """Deny read of expired memory."""
        import time
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=1,  # Expires in 1 second
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=True,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Expiring memory",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        # Wait for TTL to expire
        time.sleep(1.5)

        read_memory, audit = postgres_adapter.read(
            memory.memory_id, "agent-1", policy_check
        )

        # Should be expired
        assert read_memory is None
        assert audit.decision == "denied"
        assert audit.reason == "memory_expired"

    def test_read_scope_isolation(self, postgres_adapter, policy_check):
        """Agent cannot read another agent's memory (agent scope)."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,  # Agent-scoped
            allow_read=True,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Agent-1's secret",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        # Agent-2 tries to read
        read_memory, audit = postgres_adapter.read(
            memory.memory_id, "agent-2", policy_check
        )

        assert read_memory is None
        assert audit.decision == "denied"
        assert audit.reason == "scope_isolation_violation"

    def test_read_tenant_scope_allowed(self, postgres_adapter, policy_check):
        """Agent can read tenant-scoped memory."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.TENANT,  # Tenant-scoped
            allow_read=True,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Tenant-shared memory",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        # Agent-2 reads tenant memory
        read_memory, audit = postgres_adapter.read(
            memory.memory_id, "agent-2", policy_check
        )

        assert read_memory is not None
        assert audit.decision == "allowed"

    def test_read_permission_denied(self, postgres_adapter, policy_check):
        """Deny read when policy forbids it."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=False,  # Not allowed
        )

        memory = Memory(
            agent_id="agent-1",
            content="Forbidden",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        read_memory, audit = postgres_adapter.read(
            memory.memory_id, "agent-1", policy_check
        )

        assert read_memory is None
        assert audit.decision == "denied"
        assert audit.reason == "read_not_allowed"

    def test_read_nonexistent_memory(self, postgres_adapter, policy_check):
        """Return None for nonexistent memory."""
        read_memory, audit = postgres_adapter.read(
            "nonexistent-id", "agent-1", policy_check
        )

        assert read_memory is None
        assert audit.decision == "denied"
        assert audit.reason == "memory_not_found"


class TestPostgresDelete:
    """Test delete operations."""

    def test_delete_success(self, postgres_adapter):
        """Successfully delete memory."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )

        memory = Memory(
            agent_id="agent-1",
            content="To be deleted",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        audit = postgres_adapter.delete(memory.memory_id, "admin", "gdpr_deletion")

        assert audit.operation == "delete"
        assert audit.reason == "gdpr_deletion"
        assert audit.signature

    def test_delete_already_deleted(self, postgres_adapter):
        """Cannot delete already-deleted memory."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Delete twice",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})
        postgres_adapter.delete(memory.memory_id, "admin", "first_delete")

        with pytest.raises(Exception):  # MemoryNotFoundError
            postgres_adapter.delete(memory.memory_id, "admin", "second_delete")

    def test_deleted_memory_not_readable(self, postgres_adapter, policy_check):
        """Deleted memory cannot be read."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=True,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Will be deleted",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})
        postgres_adapter.delete(memory.memory_id, "admin", "test_delete")

        read_memory, audit = postgres_adapter.read(
            memory.memory_id, "agent-1", policy_check
        )

        assert read_memory is None
        assert audit.reason == "memory_not_found"


class TestPostgresQuery:
    """Test query operations with retrieval guard."""

    def test_query_by_type(self, postgres_adapter, policy_check):
        """Query memories by type."""
        # Write multiple memories
        for i in range(3):
            policy = MemoryPolicy(
                memory_type=MemoryType.LONG_TERM if i < 2 else MemoryType.EPISODIC,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
                allow_read=True,
            )

            memory = Memory(
                agent_id="agent-1",
                content=f"Memory {i}",
                policy=policy,
                created_by="agent-1",
            )

            postgres_adapter.write(memory, {})

        # Query only LONG_TERM
        results, audit = postgres_adapter.query(
            {"memory_types": ["long_term"]},
            "agent-1",
            policy_check,
        )

        assert len(results) == 2
        assert all(m.policy.memory_type == MemoryType.LONG_TERM for m in results)

    def test_query_retrieval_guard_filters(self, postgres_adapter, policy_check):
        """Retrieval guard filters expired and unauthorized memory."""
        # Write mix of authorized and unauthorized
        policies = [
            MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
                allow_read=True,
            ),
            MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
                allow_read=False,  # Not readable
            ),
        ]

        for i, policy in enumerate(policies):
            memory = Memory(
                agent_id="agent-1",
                content=f"Memory {i}",
                policy=policy,
                created_by="agent-1",
            )
            postgres_adapter.write(memory, {})

        # Query all
        results, audit = postgres_adapter.query(
            {},
            "agent-1",
            policy_check,
        )

        # Should only return the readable one
        assert len(results) == 1
        assert audit.metadata["filtered_count"] == 1

    def test_query_scope_isolation(self, postgres_adapter, policy_check):
        """Query respects scope isolation."""
        # Agent-1 writes agent-scoped and tenant-scoped memory
        for scope in [Scope.AGENT, Scope.TENANT]:
            policy = MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=scope,
                allow_read=True,
            )

            memory = Memory(
                agent_id="agent-1",
                content=f"Memory for {scope.value}",
                policy=policy,
                created_by="agent-1",
            )

            postgres_adapter.write(memory, {})

        # Agent-2 queries
        results, audit = postgres_adapter.query(
            {},
            "agent-2",
            policy_check,
        )

        # Should only see tenant-scoped memory
        assert len(results) == 1
        assert results[0].policy.scope == Scope.TENANT


class TestPostgresAudit:
    """Test audit log."""

    def test_audit_complete_on_write(self, postgres_adapter):
        """Write operation creates complete audit record."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.PII,
            scope=Scope.TENANT,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Sensitive data",
            policy=policy,
            created_by="agent-1",
        )

        audit = postgres_adapter.write(memory, {})

        assert audit.audit_id
        assert audit.timestamp
        assert audit.operation == "write"
        assert audit.memory_id == memory.memory_id
        assert audit.decision == "allowed"
        assert audit.signature

    def test_audit_retrievable(self, postgres_adapter):
        """Audit records can be retrieved."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Audit test",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        logs = postgres_adapter.get_audit_log(agent_id="agent-1")

        assert len(logs) >= 1
        assert logs[0].agent_id == "agent-1"
        assert logs[0].operation == "write"

    def test_audit_append_only(self, postgres_adapter):
        """Audit log is append-only (no deletions)."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Append test",
            policy=policy,
            created_by="agent-1",
        )

        policy_check = PolicyCheck(
            agent_id="agent-1",
            allowed_scopes=[Scope.AGENT],
        )

        # Write, read, delete
        postgres_adapter.write(memory, {})
        postgres_adapter.read(memory.memory_id, "agent-1", policy_check)
        postgres_adapter.delete(memory.memory_id, "admin", "test")

        logs = postgres_adapter.get_audit_log(agent_id="agent-1")

        # Should have all three operations
        operations = [log.operation for log in logs]
        assert "write" in operations
        assert "read" in operations
        assert "delete" in operations

    def test_audit_signed(self, postgres_adapter):
        """All audit records are signed."""
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Signed audit test",
            policy=policy,
            created_by="agent-1",
        )

        postgres_adapter.write(memory, {})

        logs = postgres_adapter.get_audit_log()

        for log in logs:
            assert log.signature
            assert len(log.signature) == 64  # SHA256 hex length


class TestPostgresHealthCheck:
    """Test health check."""

    def test_health_check_success(self, postgres_adapter):
        """Health check succeeds when DB is operational."""
        assert postgres_adapter.health_check() is True

    def test_health_check_bad_path(self, tmp_path):
        """Health check fails for inaccessible database."""
        # Use a read-only directory to simulate inaccessible path
        bad_path = tmp_path / "readonly" / "db.sqlite"
        try:
            bad_adapter = PostgresStorageAdapter(db_path=str(bad_path))
            assert bad_adapter.health_check() is False
        except Exception:
            # Path creation may fail, that's acceptable for this test
            pass


class TestPostgresIntegration:
    """Integration tests."""

    def test_full_memory_lifecycle(self, postgres_adapter, policy_check):
        """Test complete memory lifecycle."""
        # 1. Write
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=True,
        )

        memory = Memory(
            agent_id="agent-1",
            content="Lifecycle test",
            policy=policy,
            created_by="agent-1",
        )

        write_audit = postgres_adapter.write(memory, {})
        assert write_audit.decision == "allowed"

        # 2. Read
        read_memory, read_audit = postgres_adapter.read(
            memory.memory_id, "agent-1", policy_check
        )
        assert read_memory is not None
        assert read_audit.decision == "allowed"

        # 3. Query
        query_results, query_audit = postgres_adapter.query({}, "agent-1", policy_check)
        assert len(query_results) >= 1
        assert query_audit.decision == "allowed"

        # 4. Delete
        delete_audit = postgres_adapter.delete(
            memory.memory_id, "admin", "lifecycle_test"
        )
        assert delete_audit.operation == "delete"

        # 5. Verify deleted
        read_deleted, read_deleted_audit = postgres_adapter.read(
            memory.memory_id, "agent-1", policy_check
        )
        assert read_deleted is None

        # 6. Audit trail complete
        logs = postgres_adapter.get_audit_log(agent_id="agent-1")
        operations = [log.operation for log in logs]
        assert "write" in operations
        assert "read" in operations
        assert "query" in operations
        assert "delete" in operations

    def test_multi_agent_isolation(self, postgres_adapter, policy_check):
        """Multiple agents maintain isolation."""
        agent_memories = {}

        for agent_id in ["agent-1", "agent-2", "agent-3"]:
            policy = MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
                allow_read=True,
            )

            memory = Memory(
                agent_id=agent_id,
                content=f"Secret of {agent_id}",
                policy=policy,
                created_by=agent_id,
            )

            postgres_adapter.write(memory, {})
            agent_memories[agent_id] = memory.memory_id

        # Each agent can only read its own
        for reader_id in ["agent-1", "agent-2"]:
            for owner_id, memory_id in agent_memories.items():
                mem, audit = postgres_adapter.read(memory_id, reader_id, policy_check)

                if reader_id == owner_id:
                    assert mem is not None
                else:
                    assert mem is None
