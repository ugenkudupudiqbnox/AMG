"""Storage adapter interface and contracts.

All storage adapters must implement StorageAdapter interface.
Adapters are deterministic, versioned, and never opaque about operations.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from .types import Memory, MemoryPolicy, AuditRecord, Scope


class PolicyCheck:
    """Runtime policy enforcement context.
    
    Passed to storage adapters to enforce governance at retrieval time.
    """
    def __init__(self, agent_id: str, allowed_scopes: List[Scope], 
                 allow_read: bool = True, allow_write: bool = True):
        self.agent_id = agent_id
        self.allowed_scopes = allowed_scopes
        self.allow_read = allow_read
        self.allow_write = allow_write


class StorageAdapter(ABC):
    """Storage adapter interface contract.
    
    All adapters must implement these operations with governance guarantees:
    - No hidden behavior (every operation is loggable)
    - Policy-aware reads (enforce sensitivity/scope filters at retrieval time)
    - TTL enforcement (respect memory expiration)
    - Append-only audit (write-once audit trail)
    - Isolation guarantees (non-bypassable agent/tenant boundaries)
    """

    @abstractmethod
    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Write memory with full provenance.
        
        Must include:
        - Agent scope validation
        - Tenant scope validation
        - TTL recording
        - Immutable audit record creation
        
        Args:
            memory: Memory item with policy contract
            policy_metadata: Policy engine metadata (version, decision context)
            
        Returns:
            AuditRecord for this write operation
            
        Raises:
            PolicyEnforcementError: If policy violation detected
        """
        pass

    @abstractmethod
    def read(self, memory_id: str, agent_id: str, 
             policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read memory enforcing policy at retrieval time.
        
        Must:
        - Verify agent has permission to read
        - Check sensitivity filters
        - Check scope isolation
        - Log attempt in audit trail (even denials)
        
        Args:
            memory_id: ID of memory to retrieve
            agent_id: Agent requesting access
            policy_check: Runtime policy enforcement context
            
        Returns:
            Tuple of (Memory or None, AuditRecord)
            
        Raises:
            MemoryNotFoundError: If memory doesn't exist
        """
        pass

    @abstractmethod
    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Delete memory permanently (no soft deletes for compliance).
        
        Must:
        - Be hard delete (not soft/logical delete)
        - Record deletion in audit trail
        - Return immutable audit record
        
        Args:
            memory_id: ID of memory to delete
            actor_id: Who triggered deletion (admin_id, kill_switch_id)
            reason: Reason for deletion (e.g., "ttl_expired", "compliance_purge")
            
        Returns:
            AuditRecord for this deletion
        """
        pass

    @abstractmethod
    def query(self, filters: Dict[str, Any], agent_id: str, 
              policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Query memories with retrieval guard enforcement.
        
        Retrieval guard enforces policy BEFORE returning:
        - Filter by agent scope
        - Filter by tenant scope
        - Filter by sensitivity
        - Filter by TTL (exclude expired)
        - Enforce read permissions
        
        Must never return unauthorized memory.
        
        Args:
            filters: Query filters (memory_types, scope, etc.)
            agent_id: Agent performing query
            policy_check: Runtime policy enforcement context
            
        Returns:
            Tuple of (List[Memory], AuditRecord)
            - Memory list is ALREADY FILTERED by policy
            - AuditRecord contains metadata on filtering (filtered_count)
        """
        pass

    @abstractmethod
    def get_audit_log(self, agent_id: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      limit: int = 100) -> List[AuditRecord]:
        """Retrieve audit log for compliance/analysis.
        
        Must:
        - Return write-once records (never modified)
        - Maintain chronological order
        - Support filtering by agent, time range
        - Verify signatures if available
        
        Args:
            agent_id: Filter by agent (optional)
            start_time: Filter by start time (optional)
            end_time: Filter by end time (optional)
            
        Returns:
            List of AuditRecord in chronological order
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if storage backend is operational."""
        pass

    @abstractmethod
    def write_audit_record(self, record: AuditRecord) -> None:
        """Persist an externally generated audit record.
        
        Used for governance events like kill-switch activations.
        """
        pass
