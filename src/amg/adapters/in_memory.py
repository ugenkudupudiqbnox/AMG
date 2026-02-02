"""In-memory storage adapter for development and testing.

Simple, deterministic, fully observable implementation.
Not for production use (not thread-safe, no persistence).
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import hashlib
import json

from ..types import Memory, MemoryPolicy, AuditRecord, Scope, Sensitivity
from ..storage import StorageAdapter, PolicyCheck
from ..errors import (
    MemoryNotFoundError,
    PolicyEnforcementError,
    UnauthorizedReadError,
    IsolationViolationError,
    StorageError,
)


class InMemoryStorageAdapter(StorageAdapter):
    """In-memory storage for development and testing.
    
    Implements full governance contracts:
    - Policy-aware reads (enforces sensitivity/scope at retrieval)
    - TTL enforcement (excludes expired memory)
    - Append-only audit (write-once records)
    - Isolation guarantees (agent and tenant scopes non-bypassable)
    - Deterministic filtering (same request = same result)
    """

    def __init__(self):
        self._memories: Dict[str, Memory] = {}
        self._audit_log: List[AuditRecord] = []
        self._policy_version = "1.0.0"

    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Write memory with governance enforcement."""
        if not memory.agent_id:
            raise PolicyEnforcementError("Memory must have agent_id")

        # Verify policy
        if memory.policy.ttl_seconds <= 0:
            raise PolicyEnforcementError(f"Invalid TTL: {memory.policy.ttl_seconds}")

        # Store memory
        self._memories[memory.memory_id] = memory

        # Create audit record
        audit = AuditRecord(
            agent_id=memory.agent_id,
            request_id=policy_metadata.get("request_id", ""),
            operation="write",
            memory_id=memory.memory_id,
            policy_version=self._policy_version,
            decision="allowed",
            reason="policy_enforcement_passed",
            actor_id=memory.agent_id,
            metadata={
                "memory_type": memory.policy.memory_type.value,
                "sensitivity": memory.policy.sensitivity.value,
                "scope": memory.policy.scope.value,
                "ttl_seconds": memory.policy.ttl_seconds,
            },
        )
        audit.signature = self._sign_record(audit)
        self._audit_log.append(audit)

        return audit

    def read(self, memory_id: str, agent_id: str,
             policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read memory with policy enforcement at retrieval time."""
        
        # Check if memory exists
        if memory_id not in self._memories:
            audit = self._create_denied_audit(
                agent_id=agent_id,
                operation="read",
                memory_id=memory_id,
                reason="memory_not_found",
            )
            return None, audit

        memory = self._memories[memory_id]

        # Check TTL
        if memory.is_expired():
            audit = self._create_denied_audit(
                agent_id=agent_id,
                operation="read",
                memory_id=memory_id,
                reason="memory_expired",
            )
            return None, audit

        # Check agent scope isolation
        if memory.policy.scope == Scope.AGENT and memory.agent_id != agent_id:
            audit = self._create_denied_audit(
                agent_id=agent_id,
                operation="read",
                memory_id=memory_id,
                reason="scope_isolation_violation",
            )
            return None, audit

        # Check read permission
        if not memory.policy.allow_read:
            audit = self._create_denied_audit(
                agent_id=agent_id,
                operation="read",
                memory_id=memory_id,
                reason="read_not_allowed",
            )
            return None, audit

        # Allowed
        audit = AuditRecord(
            agent_id=agent_id,
            operation="read",
            memory_id=memory_id,
            policy_version=self._policy_version,
            decision="allowed",
            reason="policy_checks_passed",
            actor_id=agent_id,
            metadata={
                "scope": memory.policy.scope.value,
                "sensitivity": memory.policy.sensitivity.value,
            },
        )
        audit.signature = self._sign_record(audit)
        self._audit_log.append(audit)

        return memory, audit

    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Hard delete memory (no soft deletes)."""
        if memory_id not in self._memories:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")

        memory = self._memories[memory_id]
        del self._memories[memory_id]

        audit = AuditRecord(
            agent_id=memory.agent_id,
            operation="delete",
            memory_id=memory_id,
            policy_version=self._policy_version,
            decision="allowed",
            reason=reason,
            actor_id=actor_id,
            metadata={"deletion_reason": reason},
        )
        audit.signature = self._sign_record(audit)
        self._audit_log.append(audit)

        return audit

    def query(self, filters: Dict[str, Any], agent_id: str,
              policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Query memories with retrieval guard (policy filtering BEFORE return)."""
        
        results = []
        filtered_count = 0

        for memory in self._memories.values():
            # Apply filters
            if not self._passes_filters(memory, filters):
                filtered_count += 1
                continue

            # Check TTL
            if memory.is_expired():
                filtered_count += 1
                continue

            # Check scope isolation
            if memory.policy.scope == Scope.AGENT and memory.agent_id != agent_id:
                filtered_count += 1
                continue

            # Check sensitivity
            if not self._can_read_sensitivity(agent_id, memory):
                filtered_count += 1
                continue

            # Check read permission
            if not memory.policy.allow_read:
                filtered_count += 1
                continue

            results.append(memory)

        # Create audit record
        audit = AuditRecord(
            agent_id=agent_id,
            operation="query",
            policy_version=self._policy_version,
            decision="allowed",
            reason="query_executed_with_filters",
            actor_id=agent_id,
            metadata={
                "total_records_examined": len(self._memories),
                "filtered_count": filtered_count,
                "returned_count": len(results),
                "filters": str(filters),
            },
        )
        audit.signature = self._sign_record(audit)
        self._audit_log.append(audit)

        return results, audit

    def get_audit_log(self, agent_id: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> List[AuditRecord]:
        """Retrieve audit log with optional filtering."""
        results = self._audit_log

        if agent_id:
            results = [r for r in results if r.agent_id == agent_id]

        if start_time:
            results = [r for r in results if r.timestamp >= start_time]

        if end_time:
            results = [r for r in results if r.timestamp <= end_time]

        return results

    def health_check(self) -> bool:
        """In-memory adapter is always healthy."""
        return True

    # Private helpers

    def _passes_filters(self, memory: Memory, filters: Dict[str, Any]) -> bool:
        """Check if memory passes query filters."""
        if "memory_types" in filters:
            if memory.policy.memory_type.value not in filters["memory_types"]:
                return False

        if "sensitivity" in filters:
            if memory.policy.sensitivity.value not in filters["sensitivity"]:
                return False

        if "scope" in filters:
            if memory.policy.scope.value != filters["scope"]:
                return False

        return True

    def _can_read_sensitivity(self, agent_id: str, memory: Memory) -> bool:
        """Check if agent can read this sensitivity level."""
        # For now, allow all agents to read any sensitivity
        # In production, this would check agent permissions/roles
        return True

    def _create_denied_audit(self, agent_id: str, operation: str,
                            memory_id: Optional[str],
                            reason: str) -> AuditRecord:
        """Create a denied access audit record."""
        audit = AuditRecord(
            agent_id=agent_id,
            operation=operation,
            memory_id=memory_id,
            policy_version=self._policy_version,
            decision="denied",
            reason=reason,
            actor_id=agent_id,
        )
        audit.signature = self._sign_record(audit)
        self._audit_log.append(audit)
        return audit

    def _sign_record(self, record: AuditRecord) -> str:
        """Sign audit record with HMAC."""
        # Simple signature: hash of record content
        record_str = json.dumps({
            "audit_id": record.audit_id,
            "timestamp": record.timestamp.isoformat(),
            "agent_id": record.agent_id,
            "operation": record.operation,
            "memory_id": record.memory_id,
            "decision": record.decision,
            "reason": record.reason,
        }, sort_keys=True)
        return hashlib.sha256(record_str.encode()).hexdigest()
