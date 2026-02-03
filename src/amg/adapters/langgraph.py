"""LangGraph framework adapter for AMG.

Integrates AMG governance into LangGraph workflows without modifying core logic.
Provides:
- Context building with governance enforcement
- Memory write interception and policy checking
- Kill switch state exposure
- Audit context integration
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4

from ..types import Memory, MemoryPolicy, MemoryType, Sensitivity, Scope
from ..context import GovernedContextBuilder, ContextRequest
from ..kill_switch import KillSwitch
from ..storage import StorageAdapter, PolicyCheck
from ..errors import AgentDisabledError, PolicyEnforcementError


class LangGraphMemoryAdapter:
    """Adapter for LangGraph state management with AMG governance.
    
    Non-invasive integration: wraps memory operations without modifying
    LangGraph's internal logic.
    
    Usage:
        adapter = LangGraphMemoryAdapter(storage, kill_switch)
        
        # In your graph node:
        state['context'] = adapter.build_context(
            agent_id=state['agent_id'],
            memory_filters={}
        )
        
        # When agent stores memory:
        audit = adapter.record_memory(
            agent_id=state['agent_id'],
            content=state['memory_content'],
            memory_type='long_term',
            sensitivity='non_pii'
        )
    """

    def __init__(
        self,
        storage: StorageAdapter,
        kill_switch: KillSwitch,
        context_builder: Optional[GovernedContextBuilder] = None,
        policy_version: str = "1.0.0",
    ):
        """Initialize LangGraph adapter.
        
        Args:
            storage: Storage adapter for persistence
            kill_switch: Kill switch for incident response
            context_builder: Optional custom context builder
            policy_version: Policy version for audit trail
        """
        self.storage = storage
        self.kill_switch = kill_switch
        self.context_builder = context_builder or GovernedContextBuilder(storage, kill_switch)
        self.policy_version = policy_version

    def build_context(
        self,
        agent_id: str,
        memory_filters: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4000,
        max_items: int = 50,
    ) -> "GovernedContext":
        """Build governed context for LangGraph state.
        
        Applies all governance before context reaches agent:
        1. Agent identity validation
        2. Kill switch check
        3. Memory-type filtering
        4. TTL enforcement
        5. Sensitivity filtering
        6. Scope isolation
        7. Token budget limits
        8. Audit logging
        
        Args:
            agent_id: Agent requesting context
            memory_filters: Optional memory type filters
            max_tokens: Token budget limit
            max_items: Maximum memory items to return
            
        Returns:
            GovernedContext with filtered, policy-compliant memories
            
        Raises:
            AgentDisabledError: If agent is disabled/frozen
            PolicyEnforcementError: If governance check fails
        """
        memory_filters = memory_filters or {}
        
        # Check if agent is enabled
        allowed, reason = self.kill_switch.check_allowed(agent_id, "read")
        if not allowed:
            raise AgentDisabledError(
                f"Agent {agent_id} is disabled: {reason}"
            )
        
        # Build request and delegate to context builder
        request = ContextRequest(
            agent_id=agent_id,
            request_id=str(uuid4()),
            filters=memory_filters,
            max_items=max_items,
            max_tokens=max_tokens,
        )
        
        return self.context_builder.build(request)

    def record_memory(
        self,
        agent_id: str,
        content: str,
        memory_type: str,
        sensitivity: str,
        scope: str = "agent",
        provenance: Optional[str] = None,
        vector: Optional[List[float]] = None,
    ) -> "AuditRecord":
        """Record memory with governance enforcement.
        
        Enforces policy before write:
        1. Agent identity check
        2. Kill switch write permission
        3. Policy validation
        4. TTL assignment
        5. Scope enforcement
        6. Audit record creation
        
        Args:
            agent_id: Agent recording memory
            content: Memory content
            memory_type: short_term | long_term | episodic
            sensitivity: pii | non_pii
            scope: agent | tenant
            provenance: Source event (optional)
            vector: optional embedding vector
            
        Returns:
            AuditRecord of the write operation
            
        Raises:
            AgentDisabledError: If agent is disabled
            PolicyEnforcementError: If policy validation fails
        """
        # Check if agent can write
        allowed, reason = self.kill_switch.check_allowed(agent_id, "write")
        if not allowed:
            raise AgentDisabledError(
                f"Agent {agent_id} write is disabled: {reason}"
            )
        
        # Create memory with governance contract
        try:
            memory_type_enum = MemoryType(memory_type)
            sensitivity_enum = Sensitivity(sensitivity)
            scope_enum = Scope(scope)
        except ValueError as e:
            raise PolicyEnforcementError(f"Invalid memory type/sensitivity/scope: {e}")
        
        # Assign TTL based on policy
        ttl_seconds = self._calculate_ttl(sensitivity_enum, scope_enum)
        
        # Create memory object
        policy = MemoryPolicy(
            memory_type=memory_type_enum,
            ttl_seconds=ttl_seconds,
            sensitivity=sensitivity_enum,
            scope=scope_enum,
            allow_read=True,
            allow_write=True,
            provenance=provenance,
        )
        
        memory = Memory(
            agent_id=agent_id,
            content=content,
            policy=policy,
            created_by=agent_id,
            vector=vector,
        )
        
        # Write through storage with audit
        audit = self.storage.write(memory, {
            "request_id": str(uuid4()),
            "policy_version": self.policy_version,
        })
        
        return audit

    def check_agent_enabled(self, agent_id: str, operation: str = "all") -> bool:
        """Check if agent is enabled for operation.
        
        Args:
            agent_id: Agent to check
            operation: "read", "write", or "all"
            
        Returns:
            True if agent can perform operation, False otherwise
        """
        if operation == "all":
            read_ok, _ = self.kill_switch.check_allowed(agent_id, "read")
            write_ok, _ = self.kill_switch.check_allowed(agent_id, "write")
            return read_ok and write_ok
        else:
            allowed, _ = self.kill_switch.check_allowed(agent_id, operation)
            return allowed

    def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get current agent status (enabled/disabled/frozen).
        
        Args:
            agent_id: Agent to check
            
        Returns:
            Status dict with state, write_allowed, timestamps
        """
        status = self.kill_switch.get_status(agent_id)
        
        return {
            "agent_id": agent_id,
            "state": status.state.value,
            "write_allowed": status.state.value == "enabled",
            "read_allowed": status.state.value in ["enabled", "frozen"],
            "disabled_at": status.disabled_at.isoformat() if status.disabled_at else None,
            "disabled_by": status.disabled_by,
            "reason": status.reason,
        }

    def audit_context(self, agent_id: str, request_id: str) -> Dict[str, Any]:
        """Provide audit context for framework integration.
        
        Framework can use this to include governance context in its own logs.
        
        Args:
            agent_id: Agent making request
            request_id: Request identifier
            
        Returns:
            Audit context dict for framework logging
        """
        status = self.kill_switch.get_status(agent_id)
        
        return {
            "request_id": request_id,
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_state": status.state.value,
            "policy_version": self.policy_version,
            "governance_applied": True,
        }

    def get_memory_usage(self, agent_id: str) -> Dict[str, Any]:
        """Get memory usage stats for agent.
        
        Useful for monitoring and debugging.
        
        Args:
            agent_id: Agent to analyze
            
        Returns:
            Stats on memory items, types, sensitivity levels
        """
        # Query all memory for this agent
        results, _ = self.storage.query(
            filters={"scope": Scope.AGENT.value},
            agent_id=agent_id,
            policy_check=PolicyCheck(agent_id=agent_id, allowed_scopes=[Scope.AGENT]),
        )
        
        stats = {
            "total_memories": len(results),
            "by_type": {},
            "by_sensitivity": {},
            "expiring_soon": 0,
            "total_characters": 0,
        }
        
        now = datetime.utcnow()
        one_day = 86400  # seconds
        
        for memory in results:
            # Count by type
            mem_type = memory.policy.memory_type.value
            stats["by_type"][mem_type] = stats["by_type"].get(mem_type, 0) + 1
            
            # Count by sensitivity
            sens = memory.policy.sensitivity.value
            stats["by_sensitivity"][sens] = stats["by_sensitivity"].get(sens, 0) + 1
            
            # Count expiring within 1 day
            if memory.expires_at:
                ttl_remaining = (memory.expires_at - now).total_seconds()
                if 0 < ttl_remaining < one_day:
                    stats["expiring_soon"] += 1
            
            # Sum content size
            stats["total_characters"] += len(memory.content)
        
        return stats

    def _calculate_ttl(self, sensitivity: Sensitivity, scope: Scope) -> int:
        """Calculate TTL based on sensitivity and scope.
        
        Policy:
        - PII, agent scope: 1 day (86400s)
        - PII, tenant scope: 7 days (604800s)
        - Non-PII, agent scope: 30 days (2592000s)
        - Non-PII, tenant scope: 90 days (7776000s)
        
        Args:
            sensitivity: Memory sensitivity level
            scope: Memory scope
            
        Returns:
            TTL in seconds
        """
        if sensitivity == Sensitivity.PII:
            if scope == Scope.AGENT:
                return 86400  # 1 day
            else:  # TENANT
                return 604800  # 7 days
        else:  # NON_PII
            if scope == Scope.AGENT:
                return 2592000  # 30 days
            else:  # TENANT
                return 7776000  # 90 days


class LangGraphStateSchema:
    """Helper class for LangGraph state schema definition.
    
    Provides type hints and validation for agent state with AMG.
    
    Usage:
        from langgraph.graph import StateGraph
        
        class AgentState(TypedDict):
            agent_id: str
            context: LangGraphStateSchema.governed_context_type
            memory_items: List[dict]
            messages: List[dict]
        
        graph = StateGraph(AgentState)
    """

    @staticmethod
    def governed_context_type() -> type:
        """Type hint for governed context field."""
        return Dict[str, Any]

    @staticmethod
    def memory_record_type() -> type:
        """Type hint for memory record."""
        return Dict[str, Any]

    @staticmethod
    def audit_record_type() -> type:
        """Type hint for audit record."""
        return Dict[str, Any]


# Re-export for convenience
from ..context import GovernedContext
from ..types import AuditRecord

__all__ = [
    "LangGraphMemoryAdapter",
    "LangGraphStateSchema",
    "GovernedContext",
    "AuditRecord",
]
