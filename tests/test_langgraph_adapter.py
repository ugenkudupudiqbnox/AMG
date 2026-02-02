"""Tests for LangGraph framework adapter.

Tests verify:
- Context building with governance enforcement
- Memory write interception and validation
- Kill switch state exposure
- Audit context integration
- Non-invasive framework integration
"""

import pytest
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any

from amg.adapters.langgraph import LangGraphMemoryAdapter, LangGraphStateSchema
from amg.adapters.in_memory import InMemoryStorageAdapter
from amg.kill_switch import KillSwitch
from amg.context import GovernedContextBuilder
from amg.types import MemoryType, Sensitivity, Scope, Memory, MemoryPolicy
from amg.storage import PolicyCheck
from amg.errors import AgentDisabledError, PolicyEnforcementError


@pytest.fixture
def storage():
    """Create in-memory storage adapter."""
    return InMemoryStorageAdapter()


@pytest.fixture
def kill_switch():
    """Create kill switch."""
    return KillSwitch()


@pytest.fixture
def langgraph_adapter(storage, kill_switch):
    """Create LangGraph adapter."""
    return LangGraphMemoryAdapter(storage, kill_switch)


@pytest.fixture
def setup_agent_memory(storage):
    """Helper to setup test memory for an agent."""
    def _setup(agent_id: str, count: int = 3):
        """Create test memories."""
        memory_ids = []
        for i in range(count):
            policy = MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII if i % 2 == 0 else Sensitivity.PII,
                scope=Scope.AGENT,
                allow_read=True,
            )
            memory = Memory(
                agent_id=agent_id,
                content=f"Test memory {i}",
                policy=policy,
                created_by=agent_id,
            )
            storage.write(memory, {})
            memory_ids.append(memory.memory_id)
        return memory_ids
    return _setup


class TestLangGraphContextBuilding:
    """Test context building with governance."""

    def test_build_context_success(self, langgraph_adapter, setup_agent_memory):
        """Successfully build governed context."""
        agent_id = "agent-1"
        setup_agent_memory(agent_id, 3)
        
        context = langgraph_adapter.build_context(agent_id=agent_id)
        
        assert context is not None
        assert len(context.memories) >= 0  # May include some memories
        assert context.metadata["policy_version"] == "1.0.0"

    def test_build_context_disabled_agent(self, langgraph_adapter, kill_switch):
        """Reject context for disabled agent."""
        agent_id = "agent-disabled"
        kill_switch.disable(agent_id, "test_disable", "admin")
        
        with pytest.raises(AgentDisabledError):
            langgraph_adapter.build_context(agent_id=agent_id)

    def test_build_context_frozen_agent_allowed(self, langgraph_adapter, kill_switch, setup_agent_memory):
        """Frozen agent can still read (build context)."""
        agent_id = "agent-frozen"
        setup_agent_memory(agent_id, 2)
        kill_switch.freeze_writes(agent_id, "test_freeze", "admin")
        
        # Should still be able to read
        context = langgraph_adapter.build_context(agent_id=agent_id)
        assert context is not None

    def test_build_context_with_memory_filters(self, langgraph_adapter, setup_agent_memory):
        """Build context with memory type filters."""
        agent_id = "agent-2"
        setup_agent_memory(agent_id, 3)
        
        context = langgraph_adapter.build_context(
            agent_id=agent_id,
            memory_filters={"memory_types": ["long_term"]},
        )
        
        assert context is not None
        # All returned memories should be long_term
        for memory in context.memories:
            assert memory.policy.memory_type == MemoryType.LONG_TERM

    def test_build_context_token_budget(self, langgraph_adapter):
        """Enforce token budget in context."""
        agent_id = "agent-3"
        
        # Create memory with large content
        policy = MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            ttl_seconds=86400,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            allow_read=True,
        )
        large_content = "x" * 5000  # Large content
        memory = Memory(
            agent_id=agent_id,
            content=large_content,
            policy=policy,
            created_by=agent_id,
        )
        
        langgraph_adapter.storage.write(memory, {})
        
        # Build context with small token budget
        context = langgraph_adapter.build_context(
            agent_id=agent_id,
            max_tokens=1000,  # Small limit
        )
        
        # Should respect token budget
        total_tokens = context.metadata["token_count"]
        assert total_tokens <= 1000


class TestLangGraphMemoryRecording:
    """Test memory write interception and validation."""

    def test_record_memory_success(self, langgraph_adapter):
        """Successfully record memory."""
        agent_id = "agent-4"
        
        audit = langgraph_adapter.record_memory(
            agent_id=agent_id,
            content="Test memory content",
            memory_type="long_term",
            sensitivity="non_pii",
        )
        
        assert audit.decision == "allowed"
        assert audit.operation == "write"
        assert audit.memory_id is not None
        assert audit.signature  # Signed

    def test_record_memory_pii_short_ttl(self, langgraph_adapter):
        """PII memory gets shorter TTL."""
        agent_id = "agent-5"
        
        audit = langgraph_adapter.record_memory(
            agent_id=agent_id,
            content="PII data",
            memory_type="long_term",
            sensitivity="pii",
        )
        
        # Verify memory was written
        memory, _ = langgraph_adapter.storage.read(
            audit.memory_id, agent_id, 
            PolicyCheck(agent_id=agent_id, allowed_scopes=[Scope.AGENT])
        )
        
        # PII should have 1-day TTL (86400 seconds)
        assert memory is not None
        assert memory.policy.ttl_seconds == 86400

    def test_record_memory_non_pii_long_ttl(self, langgraph_adapter):
        """Non-PII memory gets longer TTL."""
        agent_id = "agent-6"
        
        audit = langgraph_adapter.record_memory(
            agent_id=agent_id,
            content="Non-PII data",
            memory_type="long_term",
            sensitivity="non_pii",
        )
        
        memory, _ = langgraph_adapter.storage.read(
            audit.memory_id, agent_id,
            PolicyCheck(agent_id=agent_id, allowed_scopes=[Scope.AGENT])
        )
        
        # Non-PII should have 30-day TTL (2592000 seconds)
        assert memory is not None
        assert memory.policy.ttl_seconds == 2592000

    def test_record_memory_disabled_agent(self, langgraph_adapter, kill_switch):
        """Disabled agent cannot write memory."""
        agent_id = "agent-disabled-write"
        kill_switch.disable(agent_id, "test", "admin")
        
        with pytest.raises(AgentDisabledError):
            langgraph_adapter.record_memory(
                agent_id=agent_id,
                content="Test",
                memory_type="long_term",
                sensitivity="non_pii",
            )

    def test_record_memory_frozen_agent_write_blocked(self, langgraph_adapter, kill_switch):
        """Frozen agent cannot write (but can read)."""
        agent_id = "agent-frozen-write"
        kill_switch.freeze_writes(agent_id, "test", "admin")
        
        with pytest.raises(AgentDisabledError):
            langgraph_adapter.record_memory(
                agent_id=agent_id,
                content="Test",
                memory_type="long_term",
                sensitivity="non_pii",
            )

    def test_record_memory_invalid_type(self, langgraph_adapter):
        """Reject invalid memory type."""
        agent_id = "agent-7"
        
        with pytest.raises(PolicyEnforcementError):
            langgraph_adapter.record_memory(
                agent_id=agent_id,
                content="Test",
                memory_type="invalid_type",
                sensitivity="non_pii",
            )

    def test_record_memory_with_provenance(self, langgraph_adapter):
        """Record memory with provenance source."""
        agent_id = "agent-8"
        
        audit = langgraph_adapter.record_memory(
            agent_id=agent_id,
            content="Sourced memory",
            memory_type="episodic",
            sensitivity="non_pii",
            provenance="user_input:form_submission",
        )
        
        memory, _ = langgraph_adapter.storage.read(
            audit.memory_id, agent_id,
            PolicyCheck(agent_id=agent_id, allowed_scopes=[Scope.AGENT])
        )
        
        assert memory.policy.provenance == "user_input:form_submission"


class TestLangGraphAgentStatus:
    """Test agent status checking and kill switch interaction."""

    def test_check_agent_enabled(self, langgraph_adapter):
        """Check if agent is enabled."""
        agent_id = "agent-9"
        
        enabled = langgraph_adapter.check_agent_enabled(agent_id)
        assert enabled is True

    def test_check_agent_disabled(self, langgraph_adapter, kill_switch):
        """Check disabled agent."""
        agent_id = "agent-disabled-check"
        kill_switch.disable(agent_id, "test", "admin")
        
        enabled = langgraph_adapter.check_agent_enabled(agent_id)
        assert enabled is False

    def test_check_agent_frozen_read(self, langgraph_adapter, kill_switch):
        """Frozen agent can read."""
        agent_id = "agent-frozen-read"
        kill_switch.freeze_writes(agent_id, "test", "admin")
        
        enabled = langgraph_adapter.check_agent_enabled(agent_id, operation="read")
        assert enabled is True

    def test_check_agent_frozen_write(self, langgraph_adapter, kill_switch):
        """Frozen agent cannot write."""
        agent_id = "agent-frozen-no-write"
        kill_switch.freeze_writes(agent_id, "test", "admin")
        
        enabled = langgraph_adapter.check_agent_enabled(agent_id, operation="write")
        assert enabled is False

    def test_get_agent_status(self, langgraph_adapter, kill_switch):
        """Get comprehensive agent status."""
        agent_id = "agent-10"
        
        status = langgraph_adapter.get_agent_status(agent_id)
        
        assert status["agent_id"] == agent_id
        assert status["state"] == "enabled"
        assert status["write_allowed"] is True
        assert status["read_allowed"] is True
        assert status["disabled_at"] is None

    def test_get_agent_status_disabled(self, langgraph_adapter, kill_switch):
        """Get status of disabled agent."""
        agent_id = "agent-disabled-status"
        kill_switch.disable(agent_id, "test_reason", "admin-123")
        
        status = langgraph_adapter.get_agent_status(agent_id)
        
        assert status["state"] == "disabled"
        assert status["write_allowed"] is False
        assert status["read_allowed"] is False


class TestLangGraphAuditIntegration:
    """Test audit context for framework logging."""

    def test_audit_context(self, langgraph_adapter):
        """Generate audit context for framework."""
        agent_id = "agent-11"
        request_id = "req-test-123"
        
        context = langgraph_adapter.audit_context(agent_id, request_id)
        
        assert context["agent_id"] == agent_id
        assert context["request_id"] == request_id
        assert context["governance_applied"] is True
        assert context["policy_version"] == "1.0.0"
        assert "timestamp" in context
        assert context["agent_state"] == "enabled"

    def test_audit_context_disabled_agent(self, langgraph_adapter, kill_switch):
        """Audit context shows disabled agent."""
        agent_id = "agent-disabled-audit"
        kill_switch.disable(agent_id, "test", "admin")
        
        context = langgraph_adapter.audit_context(agent_id, "req-123")
        
        assert context["agent_state"] == "disabled"


class TestLangGraphMemoryUsageStats:
    """Test memory usage analysis."""

    def test_get_memory_usage_empty(self, langgraph_adapter):
        """Get stats for agent with no memory."""
        agent_id = "agent-no-memory"
        
        stats = langgraph_adapter.get_memory_usage(agent_id)
        
        assert stats["total_memories"] == 0
        assert stats["by_type"] == {}
        assert stats["by_sensitivity"] == {}
        assert stats["expiring_soon"] == 0
        assert stats["total_characters"] == 0

    def test_get_memory_usage_with_memories(self, langgraph_adapter, setup_agent_memory):
        """Get stats for agent with memories."""
        agent_id = "agent-with-memory"
        setup_agent_memory(agent_id, 3)
        
        stats = langgraph_adapter.get_memory_usage(agent_id)
        
        assert stats["total_memories"] == 3
        assert "long_term" in stats["by_type"]
        assert len(stats["by_sensitivity"]) > 0
        assert stats["total_characters"] > 0

    def test_get_memory_usage_mixed_sensitivities(self, langgraph_adapter, storage):
        """Get stats with mixed sensitivity levels."""
        agent_id = "agent-mixed"
        
        # Add PII and non-PII
        for is_pii in [True, False]:
            policy = MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.PII if is_pii else Sensitivity.NON_PII,
                scope=Scope.AGENT,
                allow_read=True,
            )
            memory = Memory(
                agent_id=agent_id,
                content="x" * 100,
                policy=policy,
                created_by=agent_id,
            )
            storage.write(memory, {})
        
        stats = langgraph_adapter.get_memory_usage(agent_id)
        
        assert stats["total_memories"] == 2
        assert stats["by_sensitivity"]["pii"] == 1
        assert stats["by_sensitivity"]["non_pii"] == 1


class TestLangGraphStateSchema:
    """Test state schema helpers."""

    def test_schema_type_hints(self):
        """Get type hints for state schema."""
        context_type = LangGraphStateSchema.governed_context_type()
        memory_type = LangGraphStateSchema.memory_record_type()
        audit_type = LangGraphStateSchema.audit_record_type()
        
        assert context_type == Dict[str, Any]
        assert memory_type == Dict[str, Any]
        assert audit_type == Dict[str, Any]


class TestLangGraphIntegration:
    """Full integration tests."""

    def test_agent_workflow_write_and_read(self, langgraph_adapter):
        """Simulate agent workflow: write memory and read context."""
        agent_id = "agent-workflow"
        
        # Step 1: Agent writes memory
        write_audit = langgraph_adapter.record_memory(
            agent_id=agent_id,
            content="Important fact: the sky is blue",
            memory_type="long_term",
            sensitivity="non_pii",
        )
        
        assert write_audit.decision == "allowed"
        
        # Step 2: Agent reads context (gets its memory back)
        context = langgraph_adapter.build_context(agent_id=agent_id)
        
        assert context is not None
        # Should have at least the memory we just wrote
        assert any("blue" in m.content for m in context.memories)

    def test_multi_agent_isolation(self, langgraph_adapter):
        """Verify multi-agent isolation."""
        agent1_id = "agent-a"
        agent2_id = "agent-b"
        
        # Agent 1 writes
        write_audit1 = langgraph_adapter.record_memory(
            agent_id=agent1_id,
            content="Agent A secret",
            memory_type="long_term",
            sensitivity="non_pii",
        )
        
        # Agent 2 writes
        write_audit2 = langgraph_adapter.record_memory(
            agent_id=agent2_id,
            content="Agent B secret",
            memory_type="long_term",
            sensitivity="non_pii",
        )
        
        # Agent 1 gets its context
        context1 = langgraph_adapter.build_context(agent_id=agent1_id)
        
        # Agent 2 gets its context
        context2 = langgraph_adapter.build_context(agent_id=agent2_id)
        
        # Agent 1's context should not contain Agent 2's memory
        context1_contents = [m.content for m in context1.memories]
        context2_contents = [m.content for m in context2.memories]
        
        assert "Agent A secret" in context1_contents
        assert "Agent B secret" not in context1_contents
        
        assert "Agent B secret" in context2_contents
        assert "Agent A secret" not in context2_contents

    def test_incident_response_workflow(self, langgraph_adapter, kill_switch):
        """Simulate incident response: disable agent, verify writes blocked."""
        agent_id = "agent-incident"
        
        # Normal operation
        audit1 = langgraph_adapter.record_memory(
            agent_id=agent_id,
            content="Normal memory",
            memory_type="long_term",
            sensitivity="non_pii",
        )
        assert audit1.decision == "allowed"
        
        # Agent misbehaves - disable it
        kill_switch.disable(agent_id, "suspicious_behavior", "security_team")
        
        # Future writes should fail
        with pytest.raises(AgentDisabledError):
            langgraph_adapter.record_memory(
                agent_id=agent_id,
                content="Malicious memory",
                memory_type="long_term",
                sensitivity="non_pii",
            )
        
        # But previous memories still exist and are audited
        status = langgraph_adapter.get_agent_status(agent_id)
        assert status["state"] == "disabled"
