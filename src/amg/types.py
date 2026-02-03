"""Core data types for AMG memory governance."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List
from uuid import uuid4


class MemoryType(str, Enum):
    """Memory retention type."""
    SHORT_TERM = "short_term"      # Request-scoped only, never persisted
    LONG_TERM = "long_term"        # TTL required
    EPISODIC = "episodic"          # TTL + decay eligible


class Sensitivity(str, Enum):
    """Memory sensitivity classification."""
    PII = "pii"                    # Personally identifiable information
    NON_PII = "non_pii"            # Non-sensitive data


class Scope(str, Enum):
    """Memory visibility scope."""
    AGENT = "agent"                # Agent-scoped (isolated per agent)
    TENANT = "tenant"              # Tenant-scoped (shared within tenant)


@dataclass
class MemoryPolicy:
    """Governance contract for a memory item.
    
    Defines how memory should be stored, retained, and accessed.
    This is the regulated data asset contract.
    """
    memory_type: MemoryType
    ttl_seconds: int                # Retention duration in seconds
    sensitivity: Sensitivity
    scope: Scope
    allow_read: bool = True
    allow_write: bool = True
    provenance: Optional[str] = None  # Source event/request
    
    def __post_init__(self):
        """Validate policy constraints."""
        if self.ttl_seconds <= 0:
            raise ValueError(f"TTL must be positive, got {self.ttl_seconds}")
        if self.memory_type == MemoryType.SHORT_TERM and self.ttl_seconds > 0:
            # Short-term memory shouldn't have long TTLs
            pass


@dataclass
class Memory:
    """A governed memory item with full provenance."""
    memory_id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: str = ""              # Which agent this memory belongs to
    content: str = ""               # The actual memory content
    vector: Optional[List[float]] = None # Optional embedding for vector search
    policy: MemoryPolicy = field(default_factory=lambda: MemoryPolicy(
        memory_type=MemoryType.LONG_TERM,
        ttl_seconds=86400,
        sensitivity=Sensitivity.NON_PII,
        scope=Scope.AGENT
    ))
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    created_by: str = "agent"       # Request ID or actor that created this
    
    def __post_init__(self):
        """Calculate expiration time based on policy."""
        if self.expires_at is None:  # Only set if not provided
            from datetime import timedelta
            self.expires_at = self.created_at + timedelta(seconds=self.policy.ttl_seconds)
    
    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Check if memory has expired."""
        now = now or datetime.utcnow()
        return now >= self.expires_at


@dataclass(frozen=True)
class AuditRecord:
    """Immutable audit log entry for all governance decisions.
    
    Serves as source of truth for compliance, replay, and incident analysis.
    Must be append-only and never modified.
    """
    audit_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_id: str = ""
    request_id: str = ""
    operation: str = ""             # write | read | query | disable | freeze
    memory_id: Optional[str] = None # Nullable for query operations
    policy_version: str = "1.0.0"
    decision: str = ""              # allowed | denied | filtered
    reason: str = ""                # Why decision was made
    actor_id: str = ""              # Who triggered (agent_id or admin_id)
    metadata: Dict[str, Any] = field(default_factory=dict)
    signature: str = ""             # HMAC signature (prevents tampering)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "request_id": self.request_id,
            "operation": self.operation,
            "memory_id": self.memory_id,
            "policy_version": self.policy_version,
            "decision": self.decision,
            "reason": self.reason,
            "actor_id": self.actor_id,
            "metadata": self.metadata,
            "signature": self.signature,
        }
