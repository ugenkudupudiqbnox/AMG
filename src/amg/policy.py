"""Policy engine for evaluating and enforcing governance rules."""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from enum import Enum

from .types import Memory, MemoryType, Sensitivity, Scope, MemoryPolicy


class PolicyDecision(str, Enum):
    """Policy evaluation decision."""
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class PolicyEvaluationResult:
    """Result of policy evaluation."""
    decision: PolicyDecision
    reason: str
    metadata: Dict[str, Any]


class PolicyEngine:
    """Evaluate and enforce governance rules.
    
    Policy decisions happen BEFORE any memory operation.
    Non-bypassable: agents cannot override policy decisions.
    """

    def __init__(self, policy_config: Optional[Dict[str, Any]] = None):
        """Initialize with optional policy configuration.
        
        Args:
            policy_config: Optional policy rules in declarative format
        """
        self.config = policy_config or self._default_config()
        self.policy_version = "1.0.0"

    def _default_config(self) -> Dict[str, Any]:
        """Default policy configuration."""
        return {
            "ttl": {
                "pii_agent_scope": 86400,        # 1 day
                "pii_tenant_scope": 604800,      # 7 days
                "non_pii_agent_scope": 2592000,  # 30 days
                "non_pii_tenant_scope": 7776000, # 90 days
                "default": 86400,
            },
            "context_budget": {
                "max_tokens": 4000,
                "max_memory_items": 50,
            },
            "sensitivity_tags": {
                "pii_patterns": [
                    "email",
                    "phone",
                    "ssn",
                    "credit_card",
                    "password",
                ],
                "non_pii_patterns": [
                    "timestamp",
                    "count",
                    "status",
                ],
            },
            "isolation": {
                "agent_scope_bypassable": False,
                "tenant_scope_bypassable": False,
            },
        }

    def evaluate_write(self, memory: Memory, agent_id: str) -> PolicyEvaluationResult:
        """Evaluate if memory write is allowed.
        
        Args:
            memory: Memory item to write
            agent_id: Agent requesting write
            
        Returns:
            PolicyEvaluationResult with decision
        """
        # Verify agent ownership
        if memory.agent_id != agent_id:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="agent_ownership_violation",
                metadata={"expected_agent": memory.agent_id, "requesting_agent": agent_id},
            )

        # Verify TTL is set
        if memory.policy.ttl_seconds <= 0:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="invalid_ttl",
                metadata={"ttl": memory.policy.ttl_seconds},
            )

        # Check TTL against policy limits
        max_ttl = self._get_max_ttl(memory.policy.sensitivity, memory.policy.scope)
        if memory.policy.ttl_seconds > max_ttl:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="ttl_exceeds_policy",
                metadata={
                    "ttl": memory.policy.ttl_seconds,
                    "max_allowed": max_ttl,
                    "sensitivity": memory.policy.sensitivity.value,
                    "scope": memory.policy.scope.value,
                },
            )

        # Verify write permission
        if not memory.policy.allow_write:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="write_not_allowed",
                metadata={},
            )

        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOWED,
            reason="all_policy_checks_passed",
            metadata={
                "ttl_seconds": memory.policy.ttl_seconds,
                "sensitivity": memory.policy.sensitivity.value,
                "scope": memory.policy.scope.value,
            },
        )

    def evaluate_read(self, memory: Memory, agent_id: str) -> PolicyEvaluationResult:
        """Evaluate if memory read is allowed.
        
        Args:
            memory: Memory item to read
            agent_id: Agent requesting read
            
        Returns:
            PolicyEvaluationResult with decision
        """
        # Check scope isolation
        if memory.policy.scope == Scope.AGENT and memory.agent_id != agent_id:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="scope_isolation_violation",
                metadata={"scope": Scope.AGENT.value},
            )

        # Check read permission
        if not memory.policy.allow_read:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="read_not_allowed",
                metadata={},
            )

        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOWED,
            reason="all_policy_checks_passed",
            metadata={"scope": memory.policy.scope.value},
        )

    def calculate_ttl(
        self, sensitivity: Sensitivity, scope: Scope
    ) -> int:
        """Calculate TTL based on sensitivity and scope.
        
        Args:
            sensitivity: Memory sensitivity level
            scope: Memory visibility scope
            
        Returns:
            TTL in seconds
        """
        if sensitivity == Sensitivity.PII:
            if scope == Scope.AGENT:
                return self.config["ttl"]["pii_agent_scope"]
            else:
                return self.config["ttl"]["pii_tenant_scope"]
        else:
            if scope == Scope.AGENT:
                return self.config["ttl"]["non_pii_agent_scope"]
            else:
                return self.config["ttl"]["non_pii_tenant_scope"]

    def validate_policy(self, policy: MemoryPolicy) -> PolicyEvaluationResult:
        """Validate a memory policy against governance rules.
        
        Args:
            policy: MemoryPolicy to validate
            
        Returns:
            PolicyEvaluationResult with validation result
        """
        if policy.ttl_seconds <= 0:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="invalid_ttl",
                metadata={"ttl": policy.ttl_seconds},
            )

        max_ttl = self._get_max_ttl(policy.sensitivity, policy.scope)
        if policy.ttl_seconds > max_ttl:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENIED,
                reason="ttl_exceeds_policy",
                metadata={"ttl": policy.ttl_seconds, "max_allowed": max_ttl},
            )

        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOWED,
            reason="policy_valid",
            metadata={},
        )

    # Private helpers

    def _get_max_ttl(self, sensitivity: Sensitivity, scope: Scope) -> int:
        """Get maximum allowed TTL for sensitivity/scope."""
        if sensitivity == Sensitivity.PII:
            if scope == Scope.AGENT:
                return self.config["ttl"]["pii_agent_scope"]
            else:
                return self.config["ttl"]["pii_tenant_scope"]
        else:
            if scope == Scope.AGENT:
                return self.config["ttl"]["non_pii_agent_scope"]
            else:
                return self.config["ttl"]["non_pii_tenant_scope"]
