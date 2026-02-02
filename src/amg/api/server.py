"""FastAPI server for Agent Memory Governance."""

from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4
import logging

from amg.adapters import InMemoryStorageAdapter
from amg.kill_switch import KillSwitch
from amg.context import GovernedContextBuilder
from amg.storage import PolicyCheck
from amg.types import Memory, MemoryPolicy, MemoryType, Sensitivity, Scope, AuditRecord
from amg.errors import (
    PolicyEnforcementError,
    AgentDisabledError,
    MemoryNotFoundError,
)
from amg.api.auth import verify_api_key

logger = logging.getLogger(__name__)


# ============================================================
# Pydantic Models (Request/Response)
# ============================================================

class MemoryWriteRequest(BaseModel):
    """Request to write memory."""
    agent_id: str = Field(..., description="Agent ID")
    content: str = Field(..., description="Memory content")
    memory_type: str = Field(..., description="short_term | long_term | episodic")
    sensitivity: str = Field(..., description="pii | non_pii")
    scope: str = Field(default="agent", description="agent | tenant")
    ttl_seconds: Optional[int] = Field(None, description="Custom TTL (optional)")


class MemoryQueryRequest(BaseModel):
    """Request to query memories."""
    agent_id: str = Field(..., description="Agent ID")
    memory_types: Optional[list] = Field(None, description="Filter by type")
    sensitivity: Optional[str] = Field(None, description="Filter by sensitivity")
    scope: Optional[str] = Field(None, description="Filter by scope")
    limit: int = Field(default=50, ge=1, le=500, description="Result limit")


class ContextBuildRequest(BaseModel):
    """Request to build governed context."""
    agent_id: str = Field(..., description="Agent ID")
    memory_types: Optional[list] = Field(None, description="Memory types to include")
    max_tokens: int = Field(default=4000, description="Token budget")
    max_items: int = Field(default=50, description="Max memory items")


class MemoryResponse(BaseModel):
    """Memory item response."""
    memory_id: str
    content: str
    memory_type: str
    sensitivity: str
    scope: str
    created_at: datetime
    expires_at: datetime


class ContextResponse(BaseModel):
    """Governed context response."""
    memories: list[MemoryResponse]
    metadata: dict


class AuditResponse(BaseModel):
    """Audit record response."""
    audit_id: str
    timestamp: datetime
    agent_id: str
    operation: str
    decision: str
    reason: str
    memory_id: Optional[str] = None
    metadata: dict


class AgentStatusResponse(BaseModel):
    """Agent status response."""
    agent_id: str
    enabled: bool
    state: str  # enabled | disabled | frozen
    memory_write: str  # allowed | frozen


class WriteResponse(BaseModel):
    """Memory write response."""
    memory_id: str
    audit_id: str
    decision: str


# ============================================================
# Dependency Injection
# ============================================================

_storage = None
_kill_switch = None
_context_builder = None


def get_storage():
    """Get storage adapter instance."""
    global _storage
    if _storage is None:
        _storage = InMemoryStorageAdapter()
    return _storage


def get_kill_switch():
    """Get kill switch instance."""
    global _kill_switch
    if _kill_switch is None:
        _kill_switch = KillSwitch()
    return _kill_switch


def get_context_builder():
    """Get context builder instance."""
    global _context_builder
    if _context_builder is None:
        _context_builder = GovernedContextBuilder(
            storage=get_storage(),
            kill_switch=get_kill_switch(),
        )
    return _context_builder


# ============================================================
# Routes
# ============================================================

def create_app():
    """Create and configure FastAPI app."""
    app = FastAPI(
        title="Agent Memory Governance API",
        description="REST API for deterministic, auditable agent memory",
        version="1.0.0",
    )

    @app.get("/health")
    def health_check():
        """Health check endpoint."""
        storage = get_storage()
        try:
            storage.health_check()
            return {"status": "healthy", "timestamp": datetime.utcnow()}
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Service unhealthy: {str(e)}"
            )

    @app.post("/memory/write", response_model=WriteResponse)
    def write_memory(
        request: MemoryWriteRequest,
        storage=Depends(get_storage),
        kill_switch=Depends(get_kill_switch),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Write memory with governance enforcement."""
        try:
            # Check kill switch first
            allowed, reason = kill_switch.check_allowed(request.agent_id, "write")
            if not allowed:
                raise AgentDisabledError(f"Write not allowed: {reason}")
            # Map request to Memory type
            memory_type_map = {
                "short_term": MemoryType.SHORT_TERM,
                "long_term": MemoryType.LONG_TERM,
                "episodic": MemoryType.EPISODIC,
            }
            sensitivity_map = {
                "pii": Sensitivity.PII,
                "non_pii": Sensitivity.NON_PII,
            }
            scope_map = {
                "agent": Scope.AGENT,
                "tenant": Scope.TENANT,
            }

            if request.memory_type not in memory_type_map:
                raise ValueError(f"Invalid memory_type: {request.memory_type}")
            if request.sensitivity not in sensitivity_map:
                raise ValueError(f"Invalid sensitivity: {request.sensitivity}")
            if request.scope not in scope_map:
                raise ValueError(f"Invalid scope: {request.scope}")

            policy = MemoryPolicy(
                memory_type=memory_type_map[request.memory_type],
                ttl_seconds=request.ttl_seconds or 86400,
                sensitivity=sensitivity_map[request.sensitivity],
                scope=scope_map[request.scope],
            )
            memory = Memory(
                agent_id=request.agent_id,
                content=request.content,
                policy=policy,
            )

            audit = storage.write(memory, {"request_id": str(uuid4())})
            return WriteResponse(
                memory_id=memory.memory_id,
                audit_id=audit.audit_id,
                decision=audit.decision,
            )

        except AgentDisabledError as e:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Agent disabled: {str(e)}"
            )
        except PolicyEnforcementError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Policy enforcement failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Write failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Write failed: {str(e)}"
            )

    @app.post("/memory/query", response_model=dict)
    def query_memory(
        request: MemoryQueryRequest,
        storage=Depends(get_storage),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Query memories with governance enforcement."""
        try:
            filters = {}
            if request.memory_types:
                filters["memory_types"] = request.memory_types
            if request.sensitivity:
                filters["sensitivity"] = request.sensitivity
            if request.scope:
                filters["scope"] = request.scope

            policy_check = PolicyCheck(
                agent_id=request.agent_id,
                allowed_scopes=[Scope.AGENT, Scope.TENANT],
                allow_read=True
            )
            memories, audit = storage.query(
                filters=filters,
                agent_id=request.agent_id,
                policy_check=policy_check,
            )

            return {
                "memories": [
                    {
                        "memory_id": m.memory_id,
                        "content": m.content,
                        "memory_type": m.policy.memory_type.value,
                        "sensitivity": m.policy.sensitivity.value,
                        "scope": m.policy.scope.value,
                        "created_at": m.created_at,
                        "expires_at": m.expires_at,
                    }
                    for m in memories[:request.limit]  # Apply limit on result
                ],
                "metadata": {
                    "total": len(memories),
                    "filtered": audit.metadata.get("filtered_count", 0),
                    "audit_id": audit.audit_id,
                }
            }

        except PolicyEnforcementError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Policy enforcement failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Query failed: {str(e)}"
            )

    @app.post("/context/build", response_model=ContextResponse)
    def build_context(
        request: ContextBuildRequest,
        context_builder=Depends(get_context_builder),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Build governed context for agent."""
        try:
            from amg.context import ContextRequest

            filters = {}
            if request.memory_types:
                filters["memory_types"] = request.memory_types

            ctx_request = ContextRequest(
                agent_id=request.agent_id,
                request_id=str(uuid4()),
                filters=filters,
                max_items=request.max_items,
                max_tokens=request.max_tokens,
            )

            context = context_builder.build(ctx_request)

            return ContextResponse(
                memories=[
                    {
                        "memory_id": m.memory_id,
                        "content": m.content,
                        "memory_type": m.policy.memory_type.value,
                        "sensitivity": m.policy.sensitivity.value,
                        "scope": m.policy.scope.value,
                        "created_at": m.created_at,
                        "expires_at": m.expires_at,
                    }
                    for m in context.memories
                ],
                metadata=context.metadata,
            )

        except AgentDisabledError as e:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Agent disabled: {str(e)}"
            )
        except PolicyEnforcementError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Policy enforcement failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Context build failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Context build failed: {str(e)}"
            )

    @app.get("/audit/{request_id}", response_model=dict)
    def get_audit_log(
        request_id: str,
        storage=Depends(get_storage),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Retrieve audit log for request."""
        try:
            # In this simple implementation, search by audit_id (not request_id)
            # In production, would need request_id tracking
            logs = storage.get_audit_log()
            matching = [
                {
                    "audit_id": l.audit_id,
                    "timestamp": l.timestamp,
                    "agent_id": l.agent_id,
                    "operation": l.operation,
                    "decision": l.decision,
                    "reason": l.reason,
                    "memory_id": l.memory_id,
                    "metadata": l.metadata,
                }
                for l in logs
                if l.audit_id == request_id or l.request_id == request_id
            ]

            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Audit log not found: {request_id}"
                )

            return {
                "records": matching,
                "count": len(matching),
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Audit retrieval failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Audit retrieval failed: {str(e)}"
            )

    @app.post("/agent/{agent_id}/disable")
    def disable_agent(
        agent_id: str,
        reason: str = "No reason provided",
        actor_id: str = "api",
        kill_switch=Depends(get_kill_switch),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Disable an agent (kill switch)."""
        try:
            audit = kill_switch.disable(
                agent_id=agent_id,
                reason=reason,
                actor_id=actor_id,
            )
            return {
                "agent_id": agent_id,
                "status": "disabled",
                "timestamp": audit.timestamp,
                "audit_id": audit.audit_id,
            }
        except Exception as e:
            logger.error(f"Disable failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Disable failed: {str(e)}"
            )

    @app.post("/agent/{agent_id}/freeze")
    def freeze_agent_writes(
        agent_id: str,
        reason: str = "No reason provided",
        actor_id: str = "api",
        kill_switch=Depends(get_kill_switch),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Freeze memory writes for agent (read-only mode)."""
        try:
            audit = kill_switch.freeze_writes(
                agent_id=agent_id,
                reason=reason,
                actor_id=actor_id,
            )
            return {
                "agent_id": agent_id,
                "status": "frozen",
                "timestamp": audit.timestamp,
                "audit_id": audit.audit_id,
            }
        except Exception as e:
            logger.error(f"Freeze failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Freeze failed: {str(e)}"
            )

    @app.get("/agent/{agent_id}/status")
    def get_agent_status(
        agent_id: str,
        kill_switch=Depends(get_kill_switch),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Get agent governance status."""
        try:
            status_info = kill_switch.get_status(agent_id)
            return {
                "agent_id": agent_id,
                "state": status_info.state.value,
                "memory_write": status_info.memory_write,
                "disabled_at": status_info.disabled_at,
            }
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status check failed: {str(e)}"
            )

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
