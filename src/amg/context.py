"""Governed Context Builder - single gateway for agent memory access.

Enforces all governance BEFORE context reaches the agent:
- Agent identity validation
- Kill switch check
- Memory-type filtering
- TTL enforcement
- Sensitivity filtering
- Scope isolation
- Token budget limits
- Audit logging
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

from .types import Memory, MemoryType, Scope, Sensitivity, AuditRecord
from .storage import StorageAdapter, PolicyCheck
from .kill_switch import KillSwitch, OperationType
from .errors import AgentDisabledError, PolicyEnforcementError


@dataclass
class ContextRequest:
    """Request for governed context."""
    agent_id: str
    request_id: str
    filters: Dict[str, Any] = field(default_factory=dict)
    max_items: int = 50
    max_tokens: int = 4000


@dataclass
class GovernedContext:
    """Context returned by context builder (already filtered by policy)."""
    agent_id: str
    request_id: str
    memories: List[Memory]
    metadata: Dict[str, Any] = field(default_factory=dict)
    audit_id: str = ""


class GovernedContextBuilder:
    """Build and serve context to agents with governance enforcement.
    
    Single gateway through which agents receive memory.
    Enforces governance BEFORE context reaches agent.
    """

    def __init__(
        self,
        storage: StorageAdapter,
        kill_switch: KillSwitch,
        policy_version: str = "1.0.0",
    ):
        """Initialize context builder.
        
        Args:
            storage: Storage adapter for memory retrieval
            kill_switch: Kill switch for agent state checks
            policy_version: Governance policy version
        """
        self.storage = storage
        self.kill_switch = kill_switch
        self.policy_version = policy_version

    def build(self, request: ContextRequest) -> GovernedContext:
        """Build context with governance enforcement."""
        return self._build_context(
            agent_id=request.agent_id,
            request_id=request.request_id,
            memory_filters=request.filters,
            max_items=request.max_items,
            max_tokens=request.max_tokens
        )

    def build_context(
        self,
        agent_id: str,
        memory_filters: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4000,
        max_items: int = 50,
    ) -> GovernedContext:
        """Simplified context building helper."""
        from uuid import uuid4
        return self._build_context(
            agent_id=agent_id,
            request_id=str(uuid4()),
            memory_filters=memory_filters or {},
            max_tokens=max_tokens,
            max_items=max_items
        )

    def _build_context(
        self,
        agent_id: str,
        request_id: str,
        memory_filters: Dict[str, Any],
        max_items: int,
        max_tokens: int
    ) -> GovernedContext:
        """Core context building logic."""
        # Step 1: Agent identity validation
        if not agent_id:
            raise PolicyEnforcementError("agent_id required")

        # Step 2: Kill switch check
        allowed, reason = self.kill_switch.check_allowed(
            agent_id, OperationType.READ
        )
        if not allowed:
            raise AgentDisabledError(f"Agent blocked: {reason}")

        # Step 3-7: Query with retrieval guard
        # StorageAdapter.query() enforces all governance constraints
        policy_check = PolicyCheck(
            agent_id=agent_id,
            allowed_scopes=[Scope.AGENT, Scope.TENANT],
        )

        memories, audit = self.storage.query(
            filters=memory_filters,
            agent_id=agent_id,
            policy_check=policy_check,
        )

        # Step 7: Token budget enforcement
        # Truncate if necessary
        truncated_memories, token_count = self._enforce_token_budget(
            memories, max_tokens
        )
        if len(truncated_memories) < len(memories):
            audit.metadata["truncated_by_token_budget"] = True
            audit.metadata["tokens_dropped"] = token_count - max_tokens

        # Step 8: Audit logging (already done by storage.query)
        audit.metadata["requested_by_agent"] = agent_id
        audit.metadata["token_count"] = token_count
        audit.metadata["request_id"] = request_id

        return GovernedContext(
            agent_id=agent_id,
            request_id=request_id,
            memories=truncated_memories[:max_items],
            metadata={
                "token_count": token_count,
                "returned_count": len(truncated_memories[:max_items]),
                "filtered_count": audit.metadata.get("filtered_count", 0),
                "total_examined": audit.metadata.get("total_records_examined", 0),
                "policy_version": "1.0.0",
                "audit_id": audit.audit_id,
            },
            audit_id=audit.audit_id
        )

    # Private helpers

    def _determine_allowed_scopes(self, request: ContextRequest) -> List[Scope]:
        """Determine which scopes agent can access."""
        # For now: agents access their own scope + tenant scope
        # In production: would check agent role/permissions
        return [Scope.AGENT, Scope.TENANT]

    def _build_filters(self, request: ContextRequest) -> Dict[str, Any]:
        """Build storage query filters from request."""
        filters: Dict[str, Any] = {}

        # Memory type filter
        if "memory_types" in request.filters:
            filters["memory_types"] = request.filters["memory_types"]

        # Sensitivity filter
        if "sensitivity" in request.filters:
            filters["sensitivity"] = request.filters["sensitivity"]

        # Other custom filters
        for key, value in request.filters.items():
            if key not in ["memory_types", "sensitivity"]:
                filters[key] = value

        return filters

    def _enforce_token_budget(
        self, memories: List[Memory], max_tokens: int
    ) -> tuple[List[Memory], int]:
        """Enforce token budget limit.
        
        Simple approximation: count tokens as len(content.split())
        
        Args:
            memories: List of memories
            max_tokens: Maximum allowed tokens
            
        Returns:
            Tuple of (truncated_memories, total_tokens_counted)
        """
        result = []
        token_count = 0

        for memory in memories:
            # Rough token count (words)
            content_tokens = len(memory.content.split()) + 10  # metadata overhead
            if token_count + content_tokens <= max_tokens:
                result.append(memory)
                token_count += content_tokens
            else:
                break

        return result, token_count
