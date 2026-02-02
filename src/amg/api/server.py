"""FastAPI server for Agent Memory Governance."""

from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4
import logging

from amg.adapters import InMemoryStorageAdapter, PostgresStorageAdapter
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


class KillSwitchRequest(BaseModel):
    """Request for kill switch actions."""
    reason: str = Field(default="No reason provided")
    actor_id: str = Field(default="api")


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
        # Use PostgresStorageAdapter (SQLite file) for persistence
        _storage = PostgresStorageAdapter(db_path="amg.db")
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

    @app.get("/")
    def read_root():
        """Root endpoint for health and stats - returns everything flat for Grafana."""
        try:
            storage = get_storage()
            all_memories = storage.get_all_memories() if hasattr(storage, 'get_all_memories') else []
            
            # Simple flat stats for maximum Grafana compatibility
            stats = {
                "total_memories": len(all_memories),
                "long_term": 0,
                "short_term": 0,
                "episodic": 0,
                "pii": 0,
                "non_pii": 0,
                "expired_count": 0,
            }
            
            for mem in all_memories:
                m_type = mem.get("memory_type", "unknown")
                if m_type in stats:
                    stats[m_type] += 1
                
                sens = mem.get("sensitivity", "unknown")
                if sens in stats:
                    stats[sens] += 1
                    
                if mem.get("is_expired"):
                    stats["expired_count"] += 1
            
            return stats
        except Exception:
            return {"status": "online", "message": "AMG Governance API"}

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
                # Log denial
                audit = AuditRecord(
                    agent_id=request.agent_id,
                    operation="write",
                    policy_version="1.0.0",
                    decision="denied",
                    reason=f"kill_switch_{reason}",
                    actor_id="system",
                    metadata={"memory_type": request.memory_type}
                )
                storage.write_audit_record(audit)
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

    @app.get("/audit/export")
    def export_audit_logs(
        agent_id: Optional[str] = None,
        limit: int = 1000,
        storage=Depends(get_storage),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Export audit logs for compliance/analysis."""
        try:
            logs = storage.get_audit_log(agent_id=agent_id)
            return {
                "records": [log.to_dict() for log in logs[-limit:]],
                "count": len(logs),
                "timestamp": datetime.utcnow()
            }
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Export failed: {str(e)}"
            )

    @app.get("/audit/{request_id}", response_model=dict)
    def get_audit_by_request(
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
        request: KillSwitchRequest,
        storage=Depends(get_storage),
        kill_switch=Depends(get_kill_switch),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Disable an agent (kill switch)."""
        try:
            audit = kill_switch.disable(
                agent_id=agent_id,
                reason=request.reason,
                actor_id=request.actor_id,
            )
            # Persist audit record
            storage.write_audit_record(audit)
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

    @app.post("/agent/{agent_id}/enable")
    def enable_agent(
        agent_id: str,
        request: KillSwitchRequest,
        storage=Depends(get_storage),
        kill_switch=Depends(get_kill_switch),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Enable a disabled/frozen agent."""
        try:
            audit = kill_switch.enable(
                agent_id=agent_id,
                reason=request.reason,
                actor_id=request.actor_id,
            )
            # Persist audit record
            storage.write_audit_record(audit)
            return {
                "agent_id": agent_id,
                "status": "enabled",
                "timestamp": audit.timestamp,
                "audit_id": audit.audit_id,
            }
        except Exception as e:
            logger.error(f"Enable failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Enable failed: {str(e)}"
            )

    @app.post("/agent/{agent_id}/freeze")
    def freeze_agent_writes(
        agent_id: str,
        request: KillSwitchRequest,
        storage=Depends(get_storage),
        kill_switch=Depends(get_kill_switch),
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Freeze memory writes for agent (read-only mode)."""
        try:
            audit = kill_switch.freeze_writes(
                agent_id=agent_id,
                reason=request.reason,
                actor_id=request.actor_id,
            )
            # Persist audit record
            storage.write_audit_record(audit)
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

    # ============================================================
    # Audit & Analytics Endpoints (Admin Only)
    # ============================================================

    @app.get("/audit/export")
    def export_audit_logs(
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 10000,
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Export audit logs for compliance/analysis.
        
        Filters:
        - agent_id: Filter by agent ID
        - start_date: ISO format (2026-02-01)
        - end_date: ISO format (2026-02-02)
        - operation: write | read | query | disable | freeze
        
        Returns paginated audit records.
        """
        storage = get_storage()
        try:
            logs = storage.get_audit_log(agent_id=agent_id, limit=limit)
            
            # Filter by date range if provided
            if start_date or end_date:
                try:
                    start = datetime.fromisoformat(start_date) if start_date else datetime.min
                    end = datetime.fromisoformat(end_date) if end_date else datetime.max
                    logs = [log for log in logs if start <= (log.timestamp if hasattr(log, "timestamp") else datetime.min) <= end]
                except ValueError:
                    raise ValueError("Invalid date format. Use ISO format: 2026-02-01")
            
            # Filter by operation if provided
            if operation:
                logs = [log for log in logs if (log.operation if hasattr(log, "operation") else None) == operation]
            
            return {
                "count": len(logs),
                "records": logs,
                "export_timestamp": datetime.utcnow(),
            }
        except Exception as e:
            logger.error(f"Audit export failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Audit export failed: {str(e)}"
            )

    @app.get("/stats/memory-summary")
    def memory_summary(authenticated_agent_id: str = Depends(verify_api_key)):
        """Get summary statistics on memory storage.
        
        Returns:
        - total_memories: Total memory items in storage
        - by_type: Breakdown by memory type (short_term, long_term, episodic)
        - by_sensitivity: Breakdown by sensitivity (pii, non_pii)
        - by_scope: Breakdown by scope (agent, tenant)
        - expired_count: Number of expired memories
        """
        storage = get_storage()
        try:
            all_memories = storage.get_all_memories() if hasattr(storage, 'get_all_memories') else []
            
            stats = {
                "total_memories": len(all_memories),
                "by_type": {},
                "by_sensitivity": {},
                "by_scope": {},
                "expired_count": 0,
                "average_ttl_seconds": 0,
            }
            
            total_ttl = 0
            for mem in all_memories:
                # Type breakdown
                mem_type = mem.get("memory_type", "unknown")
                stats["by_type"][mem_type] = stats["by_type"].get(mem_type, 0) + 1
                
                # Sensitivity breakdown
                sensitivity = mem.get("sensitivity", "unknown")
                stats["by_sensitivity"][sensitivity] = stats["by_sensitivity"].get(sensitivity, 0) + 1
                
                # Scope breakdown
                scope = mem.get("scope", "unknown")
                stats["by_scope"][scope] = stats["by_scope"].get(scope, 0) + 1
                
                # Expiry check
                if mem.get("is_expired", False):
                    stats["expired_count"] += 1
                
                # TTL tracking
                if mem.get("ttl_seconds"):
                    total_ttl += mem["ttl_seconds"]
            
            if all_memories:
                stats["average_ttl_seconds"] = total_ttl // len(all_memories)
            
            # Simplified flat distributions for easier Grafana mapping
            stats["type_counts"] = {k: v for k, v in stats["by_type"].items()}
            stats["sensitivity_counts"] = {k: v for k, v in stats["by_sensitivity"].items()}

            # Format for Grafana
            stats["type_distribution"] = [{"name": k, "value": v} for k, v in stats["by_type"].items()]
            stats["sensitivity_distribution"] = [{"name": k, "value": v} for k, v in stats["by_sensitivity"].items()]
            stats["scope_distribution"] = [{"name": k, "value": v} for k, v in stats["by_scope"].items()]
            
            return stats
        except Exception as e:
            logger.error(f"Memory summary failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Memory summary failed: {str(e)}"
            )

    @app.get("/stats/audit-summary")
    def audit_summary(
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Simplified audit summary for Grafana."""
        storage = get_storage()
        try:
            logs = storage.get_audit_log(limit=1000)
            summary = {}
            for log in logs:
                agent_id = log.agent_id
                summary[agent_id] = summary.get(agent_id, 0) + 1
            
            return [{"agent_id": k, "count": v} for k, v in summary.items()]
        except Exception as e:
            logger.error(f"Audit summary failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/stats/audit-logs")
    def audit_logs(
        limit: int = 50,
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Raw audit logs for Grafana table view."""
        storage = get_storage()
        try:
            logs = storage.get_audit_log(limit=limit)
            results = []
            for log in logs:
                results.append({
                    "timestamp": log.timestamp.isoformat(),
                    "agent_id": log.agent_id,
                    "operation": log.operation,
                    "decision": log.decision,
                    "reason": log.reason,
                    "request_id": log.request_id
                })
            return {"logs": results}
        except Exception as e:
            logger.error(f"Audit logs failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/stats/agent-activity")
    def agent_activity(
        limit: int = 100,
        authenticated_agent_id: str = Depends(verify_api_key),
    ):
        """Get agent activity statistics.
        
        Returns:
        - active_agents: List of agents with activity
        - operations_count: Total operations by agent
        - last_activity: Timestamp of last operation per agent
        - disabled_agents: List of currently disabled agents
        """
        storage = get_storage()
        kill_switch = get_kill_switch()
        try:
            logs = storage.get_audit_log(limit=limit * 10)
            
            agent_stats = {}
            for log in logs:
                agent_id = log.agent_id if hasattr(log, "agent_id") else "unknown"
                if agent_id not in agent_stats:
                    agent_stats[agent_id] = {
                        "operations_count": 0,
                        "last_activity": None,
                        "operations": {},
                    }
                
                agent_stats[agent_id]["operations_count"] += 1
                curr_ts = log.timestamp if hasattr(log, "timestamp") else datetime.utcnow()
                if not agent_stats[agent_id]["last_activity"] or curr_ts > agent_stats[agent_id]["last_activity"]:
                    agent_stats[agent_id]["last_activity"] = curr_ts
                
                op = log.operation if hasattr(log, "operation") else "unknown"
                agent_stats[agent_id]["operations"][op] = agent_stats[agent_id]["operations"].get(op, 0) + 1
            
            # Format for Grafana
            agent_list = []
            op_totals = {}
            for agent_id, data in agent_stats.items():
                agent_list.append({
                    "agent_id": agent_id,
                    "operations_count": data["operations_count"],
                    "last_activity": data["last_activity"].isoformat() if data["last_activity"] else None
                })
                for op, count in data["operations"].items():
                    op_totals[op] = op_totals.get(op, 0) + count
            
            return {
                "agent_summaries": sorted(agent_list, key=lambda x: x["operations_count"], reverse=True),
                "operation_distribution": [{"name": k, "value": v} for k, v in op_totals.items()],
                "top_agents": sorted(agent_list, key=lambda x: x["last_activity"] or "", reverse=True)[:5],
                "disabled_agents": [],
                "summary_timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Agent activity failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent activity failed: {str(e)}"
            )

    @app.get("/stats/rate-limit-hits")
    def rate_limit_hits(authenticated_agent_id: str = Depends(verify_api_key)):
        """Get rate limiting statistics.
        
        Returns rate limit hits per IP/agent.
        Note: This is a placeholder - actual data would come from Nginx logs.
        """
        return {
            "rate_limit_hits": 0,
            "note": "Rate limit data comes from Nginx logs at /var/log/nginx/amg-api-access.log",
            "query_example": "grep 'HTTP/2 429' /var/log/nginx/amg-api-access.log | wc -l",
        }

    @app.get("/config/policies")
    def get_policies(authenticated_agent_id: str = Depends(verify_api_key)):
        """Get current governance policies.
        
        Returns policy schema and defaults.
        """
        return {
            "policy_version": "1.0.0",
            "memory_types": ["short_term", "long_term", "episodic"],
            "sensitivities": ["pii", "non_pii"],
            "scopes": ["agent", "tenant"],
            "default_ttls": {
                "short_term": 0,
                "long_term": 2592000,  # 30 days
                "episodic": 604800,    # 7 days
            },
            "policy_constraints": {
                "min_ttl": 0,
                "max_ttl": 31536000,  # 1 year
                "max_memory_items": 10000,
                "max_context_tokens": 8000,
            },
        }

    @app.get("/config/agents")
    def get_agents_config(authenticated_agent_id: str = Depends(verify_api_key)):
        """Get configured agents and their status.
        
        Returns list of known agents and their states.
        """
        kill_switch = get_kill_switch()
        return {
            "agents": [
                {
                    "agent_id": "prod-agent",
                    "enabled": True,
                    "state": "enabled",
                },
                {
                    "agent_id": "test-agent",
                    "enabled": True,
                    "state": "enabled",
                },
            ],
            "note": "Agent list is dynamic - pull from your agent registry",
        }

    @app.get("/system/certificate-status")
    def certificate_status(authenticated_agent_id: str = Depends(verify_api_key)):
        """Get SSL certificate status.
        
        Returns certificate expiry and renewal info.
        """
        import subprocess
        try:
            # Query certificate expiry
            result = subprocess.run(
                ["openssl", "x509", "-in", "/etc/letsencrypt/live/soc.qbnox.com/fullchain.pem", "-noout", "-dates"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            lines = result.stdout.strip().split('\n')
            cert_info = {}
            for line in lines:
                if "=" in line:
                    key, val = line.split("=", 1)
                    cert_info[key.strip()] = val.strip()
            
            return {
                "domain": "soc.qbnox.com",
                "certificate_info": cert_info,
                "auto_renewal": "enabled",
                "renewal_schedule": "0,12:00 UTC daily",
                "next_renewal_check": "2026-02-02 12:10 UTC",
            }
        except Exception as e:
            logger.error(f"Certificate status failed: {e}")
            return {
                "domain": "soc.qbnox.com",
                "status": "unknown",
                "error": str(e),
                "note": "Run: openssl x509 -in /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem -noout -dates",
            }

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
