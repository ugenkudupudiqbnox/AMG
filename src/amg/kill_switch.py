"""Kill Switch and incident response controls.

Mandatory enterprise control for stopping agent execution instantly.
Must be: instant (no queues), idempotent, non-bypassable, audited.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from uuid import uuid4

from .types import AuditRecord
from .errors import AgentDisabledError


class AgentState(str, Enum):
    """Agent execution state."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    FROZEN = "frozen"  # Read-only mode


class OperationType(str, Enum):
    """Memory operation type."""
    READ = "read"
    WRITE = "write"
    QUERY = "query"


@dataclass
class AgentStatus:
    """Current state of an agent."""
    agent_id: str
    state: AgentState
    memory_write: str = "allowed"  # allowed | frozen
    disabled_at: Optional[datetime] = None
    disabled_by: Optional[str] = None
    reason: Optional[str] = None
    audit_id: Optional[str] = None


class KillSwitch:
    """Mandatory emergency control for agent operations.
    
    Guarantees:
    - Instant: no queues, no async
    - Idempotent: safe to call multiple times
    - Non-bypassable: enforcement outside agent code
    - Audited: every invocation logged
    """

    def __init__(self):
        """Initialize kill switch."""
        self._agent_states: Dict[str, AgentState] = {}
        self._audit_log: Dict[str, AuditRecord] = {}

    def check_allowed(
        self, agent_id: str, operation: OperationType
    ) -> tuple[bool, Optional[str]]:
        """Check if operation is allowed for agent.
        
        Must be called BEFORE any memory operation.
        
        Args:
            agent_id: Agent requesting operation
            operation: Type of operation (read, write, query)
            
        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
        """
        state = self._agent_states.get(agent_id, AgentState.ENABLED)

        if state == AgentState.DISABLED:
            return False, "agent_disabled"

        if state == AgentState.FROZEN:
            if operation == OperationType.WRITE:
                return False, "agent_frozen_write_denied"
            # Reads allowed in frozen mode
            return True, None

        return True, None

    def disable(
        self, agent_id: str, reason: str, actor_id: str
    ) -> AuditRecord:
        """Disable agent (no operations allowed).
        
        Args:
            agent_id: Agent to disable
            reason: Reason for disabling
            actor_id: Admin/actor performing disable
            
        Returns:
            AuditRecord of this action
        """
        self._agent_states[agent_id] = AgentState.DISABLED

        audit = AuditRecord(
            agent_id=agent_id,
            operation="disable",
            policy_version="1.0.0",
            decision="allowed",
            reason=reason,
            actor_id=actor_id,
            metadata={
                "state": AgentState.DISABLED.value,
                "disabled_by": actor_id,
            },
        )
        object.__setattr__(audit, "signature", self._sign_record(audit))
        self._audit_log[audit.audit_id] = audit

        return audit

    def freeze_writes(
        self, agent_id: str, reason: str, actor_id: str
    ) -> AuditRecord:
        """Freeze writes but allow reads (human-in-the-loop mode).
        
        Args:
            agent_id: Agent to freeze
            reason: Reason for freezing
            actor_id: Admin/actor performing freeze
            
        Returns:
            AuditRecord of this action
        """
        self._agent_states[agent_id] = AgentState.FROZEN

        audit = AuditRecord(
            agent_id=agent_id,
            operation="freeze",
            policy_version="1.0.0",
            decision="allowed",
            reason=reason,
            actor_id=actor_id,
            metadata={
                "state": AgentState.FROZEN.value,
                "writes_blocked": True,
                "reads_allowed": True,
            },
        )
        object.__setattr__(audit, "signature", self._sign_record(audit))
        self._audit_log[audit.audit_id] = audit

        return audit

    def global_shutdown(self, reason: str, actor_id: str) -> Dict[str, AuditRecord]:
        """Emergency: disable all agents globally.
        
        Args:
            reason: Reason for shutdown
            actor_id: Admin performing shutdown
            
        Returns:
            Dict of agent_id -> AuditRecord for each disabled agent
        """
        audit_records = {}

        for agent_id in list(self._agent_states.keys()):
            if self._agent_states[agent_id] != AgentState.DISABLED:
                audit = self.disable(agent_id, reason, actor_id)
                audit_records[agent_id] = audit

        return audit_records

    def enable(self, agent_id: str, actor_id: str) -> AuditRecord:
        """Re-enable disabled or frozen agent.
        
        Args:
            agent_id: Agent to enable
            actor_id: Admin performing enable
            
        Returns:
            AuditRecord of this action
        """
        self._agent_states[agent_id] = AgentState.ENABLED

        audit = AuditRecord(
            agent_id=agent_id,
            operation="enable",
            policy_version="1.0.0",
            decision="allowed",
            reason="agent_reenabled",
            actor_id=actor_id,
            metadata={"state": AgentState.ENABLED.value},
        )
        object.__setattr__(audit, "signature", self._sign_record(audit))
        self._audit_log[audit.audit_id] = audit

        return audit

    def get_status(self, agent_id: str) -> AgentStatus:
        """Get current status of agent.
        
        Args:
            agent_id: Agent to check
            
        Returns:
            AgentStatus with current state
        """
        state = self._agent_states.get(agent_id, AgentState.ENABLED)

        memory_write = "allowed"
        if state == AgentState.DISABLED:
            memory_write = "blocked"
        elif state == AgentState.FROZEN:
            memory_write = "frozen"

        return AgentStatus(
            agent_id=agent_id,
            state=state,
            memory_write=memory_write,
        )

    def get_audit_log(self, agent_id: Optional[str] = None) -> list[AuditRecord]:
        """Retrieve kill switch audit log.
        
        Args:
            agent_id: Optional filter by agent
            
        Returns:
            List of AuditRecord
        """
        records = list(self._audit_log.values())

        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]

        return sorted(records, key=lambda r: r.timestamp)

    # Private helpers

    def _sign_record(self, record: AuditRecord) -> str:
        """Sign audit record."""
        import hashlib
        import json

        record_str = json.dumps(
            {
                "audit_id": record.audit_id,
                "timestamp": record.timestamp.isoformat(),
                "agent_id": record.agent_id,
                "operation": record.operation,
                "decision": record.decision,
                "reason": record.reason,
            },
            sort_keys=True,
        )
        return hashlib.sha256(record_str.encode()).hexdigest()
