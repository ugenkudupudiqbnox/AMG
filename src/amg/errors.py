"""AMG exception types."""


class AMGException(Exception):
    """Base exception for all AMG errors."""
    pass


class PolicyEnforcementError(AMGException):
    """Policy enforcement failed (access denied, invalid policy, etc.)."""
    pass


class MemoryNotFoundError(AMGException):
    """Requested memory does not exist."""
    pass


class InvalidPolicyError(AMGException):
    """Memory policy is invalid or violates constraints."""
    pass


class AuditIntegrityError(AMGException):
    """Audit log integrity check failed."""
    pass


class StorageError(AMGException):
    """Storage backend error."""
    pass


class IsolationViolationError(PolicyEnforcementError):
    """Agent or tenant isolation constraint violated."""
    pass


class UnauthorizedReadError(PolicyEnforcementError):
    """Agent attempted to read memory they lack permission for."""
    pass


class AgentDisabledError(PolicyEnforcementError):
    """Agent is disabled and cannot perform this operation."""
    pass
