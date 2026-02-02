"""Tests for Policy Engine, Kill Switch, and Governed Context Builder."""

import pytest
from datetime import datetime, timedelta

from amg.types import Memory, MemoryPolicy, MemoryType, Sensitivity, Scope
from amg.policy import PolicyEngine, PolicyDecision
from amg.kill_switch import KillSwitch, AgentState, OperationType
from amg.context import GovernedContextBuilder, ContextRequest
from amg.adapters import InMemoryStorageAdapter
from amg.errors import AgentDisabledError, PolicyEnforcementError


class TestPolicyEngine:
    """Test Policy Engine evaluation and enforcement."""

    @pytest.fixture
    def engine(self):
        """Create policy engine."""
        return PolicyEngine()

    @pytest.fixture
    def sample_memory(self):
        """Create sample memory."""
        return Memory(
            agent_id="agent-123",
            content="test",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )

    # ============================================================
    # Policy Engine: Write Evaluation
    # ============================================================

    def test_evaluate_write_allows_valid_memory(self, engine, sample_memory):
        """Write evaluation passes for valid memory."""
        result = engine.evaluate_write(sample_memory, "agent-123")
        assert result.decision == PolicyDecision.ALLOWED

    def test_evaluate_write_denies_agent_mismatch(self, engine, sample_memory):
        """Write evaluation denies if agent_id doesn't match."""
        result = engine.evaluate_write(sample_memory, "agent-456")
        assert result.decision == PolicyDecision.DENIED
        assert result.reason == "agent_ownership_violation"

    def test_evaluate_write_denies_invalid_ttl(self, engine, sample_memory):
        """Write evaluation denies invalid TTL."""
        sample_memory.policy.ttl_seconds = -1
        result = engine.evaluate_write(sample_memory, "agent-123")
        assert result.decision == PolicyDecision.DENIED
        assert result.reason == "invalid_ttl"

    def test_evaluate_write_denies_ttl_exceeds_policy(self, engine, sample_memory):
        """Write evaluation denies TTL exceeding policy limits."""
        # PII + agent scope max is 1 day (86400)
        sample_memory.policy.sensitivity = Sensitivity.PII
        sample_memory.policy.ttl_seconds = 999999
        result = engine.evaluate_write(sample_memory, "agent-123")
        assert result.decision == PolicyDecision.DENIED
        assert result.reason == "ttl_exceeds_policy"

    def test_evaluate_write_respects_policy_limits_pii(self, engine):
        """Write evaluation enforces PII TTL limits."""
        # PII + agent = 1 day max
        memory = Memory(
            agent_id="agent-123",
            content="ssn: 123-45-6789",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,  # 1 day - at limit
                sensitivity=Sensitivity.PII,
                scope=Scope.AGENT,
            ),
        )
        result = engine.evaluate_write(memory, "agent-123")
        assert result.decision == PolicyDecision.ALLOWED

    def test_evaluate_write_respects_policy_limits_non_pii(self, engine):
        """Write evaluation enforces non-PII TTL limits."""
        # Non-PII + agent = 30 days max
        memory = Memory(
            agent_id="agent-123",
            content="status update",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=2592000,  # 30 days - at limit
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )
        result = engine.evaluate_write(memory, "agent-123")
        assert result.decision == PolicyDecision.ALLOWED

    # ============================================================
    # Policy Engine: Read Evaluation
    # ============================================================

    def test_evaluate_read_allows_authorized_read(self, engine, sample_memory):
        """Read evaluation allows authorized read."""
        result = engine.evaluate_read(sample_memory, "agent-123")
        assert result.decision == PolicyDecision.ALLOWED

    def test_evaluate_read_denies_scope_isolation(self, engine, sample_memory):
        """Read evaluation denies cross-agent access (scope)."""
        result = engine.evaluate_read(sample_memory, "agent-456")
        assert result.decision == PolicyDecision.DENIED
        assert result.reason == "scope_isolation_violation"

    def test_evaluate_read_denies_read_permission(self, engine, sample_memory):
        """Read evaluation denies if allow_read=false."""
        sample_memory.policy.allow_read = False
        result = engine.evaluate_read(sample_memory, "agent-123")
        assert result.decision == PolicyDecision.DENIED
        assert result.reason == "read_not_allowed"

    # ============================================================
    # Policy Engine: TTL Calculation
    # ============================================================

    def test_calculate_ttl_pii_agent_scope(self, engine):
        """TTL calculation for PII + agent scope = 1 day."""
        ttl = engine.calculate_ttl(Sensitivity.PII, Scope.AGENT)
        assert ttl == 86400

    def test_calculate_ttl_pii_tenant_scope(self, engine):
        """TTL calculation for PII + tenant scope = 7 days."""
        ttl = engine.calculate_ttl(Sensitivity.PII, Scope.TENANT)
        assert ttl == 604800

    def test_calculate_ttl_non_pii_agent_scope(self, engine):
        """TTL calculation for non-PII + agent scope = 30 days."""
        ttl = engine.calculate_ttl(Sensitivity.NON_PII, Scope.AGENT)
        assert ttl == 2592000

    def test_calculate_ttl_non_pii_tenant_scope(self, engine):
        """TTL calculation for non-PII + tenant scope = 90 days."""
        ttl = engine.calculate_ttl(Sensitivity.NON_PII, Scope.TENANT)
        assert ttl == 7776000


class TestKillSwitch:
    """Test Kill Switch incident response controls."""

    @pytest.fixture
    def kill_switch(self):
        """Create kill switch."""
        return KillSwitch()

    # ============================================================
    # Kill Switch: Basic Operations
    # ============================================================

    def test_enabled_agent_allowed_all_operations(self, kill_switch):
        """Enabled agent allowed all operations."""
        allowed, _ = kill_switch.check_allowed("agent-123", OperationType.READ)
        assert allowed

        allowed, _ = kill_switch.check_allowed("agent-123", OperationType.WRITE)
        assert allowed

        allowed, _ = kill_switch.check_allowed("agent-123", OperationType.QUERY)
        assert allowed

    def test_disabled_agent_blocked_all_operations(self, kill_switch):
        """Disabled agent blocked from all operations."""
        kill_switch.disable("agent-123", "test_disable", "admin")

        allowed, reason = kill_switch.check_allowed("agent-123", OperationType.READ)
        assert not allowed
        assert reason == "agent_disabled"

        allowed, reason = kill_switch.check_allowed("agent-123", OperationType.WRITE)
        assert not allowed

    def test_frozen_agent_allows_reads_blocks_writes(self, kill_switch):
        """Frozen agent allows reads but blocks writes."""
        kill_switch.freeze_writes("agent-123", "test_freeze", "admin")

        # Read allowed
        allowed, _ = kill_switch.check_allowed("agent-123", OperationType.READ)
        assert allowed

        # Write blocked
        allowed, reason = kill_switch.check_allowed("agent-123", OperationType.WRITE)
        assert not allowed
        assert reason == "agent_frozen_write_denied"

    # ============================================================
    # Kill Switch: Disable/Enable
    # ============================================================

    def test_disable_agent_creates_audit_record(self, kill_switch):
        """Disable creates immutable audit record."""
        audit = kill_switch.disable("agent-123", "security_violation", "admin")

        assert audit.agent_id == "agent-123"
        assert audit.operation == "disable"
        assert audit.decision == "allowed"
        assert audit.reason == "security_violation"
        assert audit.signature

    def test_enable_reenables_disabled_agent(self, kill_switch):
        """Enable re-enables a disabled agent."""
        kill_switch.disable("agent-123", "test_disable", "admin")

        allowed, _ = kill_switch.check_allowed("agent-123", OperationType.WRITE)
        assert not allowed

        kill_switch.enable("agent-123", "re-enabling", "admin")

        allowed, _ = kill_switch.check_allowed("agent-123", OperationType.WRITE)
        assert allowed

    # ============================================================
    # Kill Switch: Global Shutdown
    # ============================================================

    def test_global_shutdown_disables_all_agents(self, kill_switch):
        """Global shutdown disables all active agents."""
        kill_switch.enable("agent-1", "setup", "admin")
        kill_switch.enable("agent-2", "setup", "admin")
        kill_switch.enable("agent-3", "setup", "admin")

        results = kill_switch.global_shutdown("emergency_shutdown", "admin")

        assert len(results) >= 2

        for agent_id in ["agent-1", "agent-2", "agent-3"]:
            allowed, _ = kill_switch.check_allowed(agent_id, OperationType.WRITE)
            assert not allowed

    # ============================================================
    # Kill Switch: Status & Audit Log
    # ============================================================

    def test_get_status_returns_current_state(self, kill_switch):
        """Get status returns current agent state."""
        status = kill_switch.get_status("agent-123")
        assert status.state == AgentState.ENABLED
        assert status.memory_write == "allowed"

        kill_switch.disable("agent-123", "test", "admin")
        status = kill_switch.get_status("agent-123")
        assert status.state == AgentState.DISABLED
        assert status.memory_write == "blocked"

    def test_audit_log_includes_all_operations(self, kill_switch):
        """Audit log records all operations."""
        kill_switch.disable("agent-1", "reason1", "admin")
        kill_switch.freeze_writes("agent-2", "reason2", "admin")
        kill_switch.enable("agent-1", "reactivating", "admin")

        logs = kill_switch.get_audit_log()
        assert len(logs) == 3

        operations = [log.operation for log in logs]
        assert "disable" in operations
        assert "freeze" in operations
        assert "enable" in operations

    def test_audit_log_can_be_filtered_by_agent(self, kill_switch):
        """Audit log can be filtered by agent."""
        kill_switch.disable("agent-1", "test1", "admin")
        kill_switch.disable("agent-2", "test2", "admin")

        agent1_logs = kill_switch.get_audit_log("agent-1")
        assert len(agent1_logs) == 1
        assert agent1_logs[0].agent_id == "agent-1"


class TestGovernedContextBuilder:
    """Test Governed Context Builder with governance enforcement."""

    @pytest.fixture
    def setup(self):
        """Set up context builder with dependencies."""
        storage = InMemoryStorageAdapter()
        kill_switch = KillSwitch()
        builder = GovernedContextBuilder(storage, kill_switch)
        return builder, storage, kill_switch

    # ============================================================
    # Context Builder: Basic Flow
    # ============================================================

    def test_build_returns_governed_context(self, setup):
        """Build returns governed context with policy metadata."""
        builder, storage, _ = setup

        # Add memory
        memory = Memory(agent_id="agent-123", content="test data")
        storage.write(memory, {"request_id": "req-123"})

        # Request context
        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-456",
        )
        context = builder.build(request)

        assert context.agent_id == "agent-123"
        assert context.request_id == "req-456"
        assert len(context.memories) == 1
        assert context.memories[0].content == "test data"

    def test_build_enforces_agent_identity(self, setup):
        """Build rejects requests without agent_id."""
        builder, _, _ = setup

        request = ContextRequest(
            agent_id="",
            request_id="req-456",
        )

        with pytest.raises(PolicyEnforcementError):
            builder.build(request)

    # ============================================================
    # Context Builder: Kill Switch Integration
    # ============================================================

    def test_build_rejects_disabled_agent(self, setup):
        """Build rejects context request from disabled agent."""
        builder, storage, kill_switch = setup

        # Add memory
        memory = Memory(agent_id="agent-123", content="test")
        storage.write(memory, {"request_id": "req-123"})

        # Disable agent
        kill_switch.disable("agent-123", "test_disable", "admin")

        # Try to build context
        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-456",
        )

        with pytest.raises(AgentDisabledError):
            builder.build(request)

    def test_build_allows_frozen_agent_reads(self, setup):
        """Build allows frozen agent to read (human-in-the-loop)."""
        builder, storage, kill_switch = setup

        # Add memory
        memory = Memory(agent_id="agent-123", content="test")
        storage.write(memory, {"request_id": "req-123"})

        # Freeze writes
        kill_switch.freeze_writes("agent-123", "test_freeze", "admin")

        # Can still build context (read allowed)
        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-456",
        )
        context = builder.build(request)

        assert len(context.memories) == 1

    # ============================================================
    # Context Builder: Policy Enforcement
    # ============================================================

    def test_build_enforces_scope_isolation(self, setup):
        """Build enforces scope isolation (agent can't see other's memory)."""
        builder, storage, _ = setup

        # Agent-1 writes memory
        memory = Memory(agent_id="agent-1", content="secret")
        storage.write(memory, {"request_id": "req-1"})

        # Agent-2 tries to read
        request = ContextRequest(
            agent_id="agent-2",
            request_id="req-2",
        )
        context = builder.build(request)

        assert len(context.memories) == 0

    def test_build_filters_by_memory_type(self, setup):
        """Build filters context by memory type."""
        builder, storage, _ = setup

        # Write different memory types
        mem_long = Memory(
            agent_id="agent-123",
            content="long",
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM,
                ttl_seconds=86400,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )
        mem_episodic = Memory(
            agent_id="agent-123",
            content="episodic",
            policy=MemoryPolicy(
                memory_type=MemoryType.EPISODIC,
                ttl_seconds=3600,
                sensitivity=Sensitivity.NON_PII,
                scope=Scope.AGENT,
            ),
        )

        storage.write(mem_long, {"request_id": "req-1"})
        storage.write(mem_episodic, {"request_id": "req-2"})

        # Request only long-term
        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-3",
            filters={"memory_types": ["long_term"]},
        )
        context = builder.build(request)

        assert len(context.memories) == 1
        assert context.memories[0].policy.memory_type == MemoryType.LONG_TERM

    # ============================================================
    # Context Builder: Token Budget
    # ============================================================

    def test_build_enforces_token_budget(self, setup):
        """Build enforces maximum token budget."""
        builder, storage, _ = setup

        # Write large memory
        large_content = " ".join(["word"] * 1000)  # 1000 words
        memory = Memory(agent_id="agent-123", content=large_content)
        storage.write(memory, {"request_id": "req-123"})

        # Request with small token budget
        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-456",
            max_tokens=100,  # Small budget
        )
        context = builder.build(request)

        # Should be truncated
        assert context.metadata["token_count"] <= request.max_tokens

    def test_build_respects_max_items(self, setup):
        """Build respects maximum item count."""
        builder, storage, _ = setup

        # Write multiple memories
        for i in range(10):
            memory = Memory(agent_id="agent-123", content=f"item-{i}")
            storage.write(memory, {"request_id": f"req-{i}"})

        # Request with max 3 items
        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-final",
            max_items=3,
        )
        context = builder.build(request)

        assert len(context.memories) <= 3

    # ============================================================
    # Context Builder: Metadata & Audit
    # ============================================================

    def test_build_includes_policy_metadata(self, setup):
        """Build includes governance metadata in response."""
        builder, storage, _ = setup

        memory = Memory(agent_id="agent-123", content="test")
        storage.write(memory, {"request_id": "req-123"})

        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-456",
        )
        context = builder.build(request)

        assert "token_count" in context.metadata
        assert "filtered_count" in context.metadata
        assert "returned_count" in context.metadata
        assert "audit_id" in context.metadata
        assert "policy_version" in context.metadata

    def test_build_creates_audit_trail(self, setup):
        """Build operation creates audit trail."""
        builder, storage, _ = setup

        memory = Memory(agent_id="agent-123", content="test")
        storage.write(memory, {"request_id": "req-123"})

        request = ContextRequest(
            agent_id="agent-123",
            request_id="req-456",
        )
        context = builder.build(request)

        # Audit should be recorded in storage
        audit_logs = storage.get_audit_log()
        assert any(log.operation == "query" for log in audit_logs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
