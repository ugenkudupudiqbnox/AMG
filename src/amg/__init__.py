"""Agent Memory Governance (AMG) - Governance-first memory control plane."""

from .types import (
    MemoryType,
    Sensitivity,
    Scope,
    Memory,
    MemoryPolicy,
    AuditRecord,
)
from .storage import StorageAdapter, PolicyCheck
from .policy import PolicyEngine, PolicyDecision, PolicyEvaluationResult
from .kill_switch import KillSwitch, AgentState, OperationType
from .context import GovernedContextBuilder, ContextRequest, GovernedContext
from .adapters import InMemoryStorageAdapter

__version__ = "0.1.0"
__all__ = [
    # Types
    "MemoryType",
    "Sensitivity",
    "Scope",
    "Memory",
    "MemoryPolicy",
    "AuditRecord",
    # Storage
    "StorageAdapter",
    "PolicyCheck",
    "InMemoryStorageAdapter",
    # Policy
    "PolicyEngine",
    "PolicyDecision",
    "PolicyEvaluationResult",
    # Kill Switch
    "KillSwitch",
    "AgentState",
    "OperationType",
    # Context
    "GovernedContextBuilder",
    "ContextRequest",
    "GovernedContext",
]
