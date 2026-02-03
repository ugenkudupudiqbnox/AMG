"""Qdrant storage adapter for AMG.

Governs memory stored in Qdrant vector database.
Implements the StorageAdapter interface.
"""

import logging
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as rest
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

from ..types import Memory, MemoryPolicy, AuditRecord, Scope, MemoryType, Sensitivity
from ..storage import StorageAdapter, PolicyCheck
from ..errors import MemoryNotFoundError, PolicyEnforcementError, StorageError

logger = logging.getLogger(__name__)

class QdrantStorageAdapter(StorageAdapter):
    """Qdrant adapter with governance enforcement.
    
    Uses Qdrant payload for metadata storage and Qdrant filtering
    for efficient retrieval guard execution.
    """

    def __init__(
        self, 
        url: str = None, 
        api_key: str = None, 
        path: str = None, 
        collection_name: str = "amg_memories"
    ):
        """Initialize Qdrant adapter.
        
        Args:
            url: Qdrant server URL
            api_key: API key
            path: Local path for persistent storage
            collection_name: Collection name
        """
        if not QDRANT_AVAILABLE:
            raise ImportError("qdrant-client is required. Install with 'pip install qdrant-client'.")
        
        self.client = QdrantClient(url=url, api_key=api_key, path=path)
        self.collection_name = collection_name
        self.audit_collection = f"{collection_name}_audit"
        self.policy_version = "1.0.0"
        
        self._ensure_collections()

    def _ensure_collections(self):
        """Ensure Qdrant collections exist."""
        # Simple check/create loop (in production, specify vector params)
        collections = [c.name for c in self.client.get_collections().collections]
        
        if self.collection_name not in collections:
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=rest.VectorParams(size=1536, distance=rest.Distance.COSINE),
            )
            
        if self.audit_collection not in collections:
            logger.info(f"Creating Qdrant audit collection: {self.audit_collection}")
            self.client.create_collection(
                collection_name=self.audit_collection,
                vectors_config={}, # No vectors for audit logs
            )

    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Write memory to Qdrant."""
        if not memory.agent_id:
            raise PolicyEnforcementError("Memory must have agent_id")
        if not memory.vector:
            raise PolicyEnforcementError("Qdrant requires a vector for storage")

        payload = {
            "agent_id": memory.agent_id,
            "content": memory.content,
            "memory_type": memory.policy.memory_type.value,
            "sensitivity": memory.policy.sensitivity.value,
            "scope": memory.policy.scope.value,
            "ttl_seconds": memory.policy.ttl_seconds,
            "created_at": memory.created_at.isoformat(),
            "expires_at": memory.expires_at.isoformat(),
            "created_by": memory.created_by,
            "allow_read": memory.policy.allow_read,
        }

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    rest.PointStruct(
                        id=memory.memory_id,
                        vector=memory.vector,
                        payload=payload
                    )
                ]
            )

            audit = AuditRecord(
                agent_id=memory.agent_id,
                request_id=policy_metadata.get("request_id", ""),
                operation="write",
                memory_id=memory.memory_id,
                policy_version=self.policy_version,
                decision="allowed",
                reason="policy_enforcement_passed",
                actor_id=memory.agent_id,
                metadata={
                    "memory_type": memory.policy.memory_type.value,
                    "sensitivity": memory.policy.sensitivity.value,
                },
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)

            return audit
        except Exception as e:
            raise StorageError(f"Qdrant write failed: {str(e)}")

    def read(self, memory_id: str, agent_id: str, 
             policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read from Qdrant with policy check."""
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[memory_id],
                with_vectors=True
            )
            
            if not points:
                audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_not_found")
                return None, audit

            point = points[0]
            memory = self._point_to_memory(point)

            if memory.is_expired():
                audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_expired")
                return None, audit

            if memory.policy.scope == Scope.AGENT and memory.agent_id != agent_id:
                audit = self._create_denied_audit(agent_id, "read", memory_id, "scope_violation")
                return None, audit

            audit = AuditRecord(
                agent_id=agent_id,
                operation="read",
                memory_id=memory_id,
                policy_version=self.policy_version,
                decision="allowed",
                reason="policy_checks_passed",
                actor_id=agent_id,
                metadata={"scope": memory.policy.scope.value}
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)

            return memory, audit
        except Exception as e:
            raise StorageError(f"Qdrant read failed: {str(e)}")

    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Permanently delete from Qdrant."""
        try:
            points = self.client.retrieve(collection_name=self.collection_name, ids=[memory_id])
            agent_id = points[0].payload.get("agent_id", "unknown") if points else "unknown"

            self.client.delete(
                collection_name=self.collection_name,
                points_selector=rest.PointIdsList(points=[memory_id])
            )

            audit = AuditRecord(
                agent_id=agent_id,
                operation="delete",
                memory_id=memory_id,
                policy_version=self.policy_version,
                decision="allowed",
                reason=reason,
                actor_id=actor_id,
                metadata={"deletion_reason": reason}
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)
            return audit
        except Exception as e:
            raise StorageError(f"Qdrant delete failed: {str(e)}")

    def query(self, filters: Dict[str, Any], agent_id: str, 
              policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Query Qdrant with hybrid retrieval guard."""
        try:
            query_vector = filters.get("vector")
            limit = filters.get("limit", 100)
            
            # Build Qdrant filter
            must_filters = []
            if "memory_types" in filters:
                must_filters.append(rest.FieldCondition(
                    key="memory_type", 
                    match=rest.MatchAny(any=filters["memory_types"])
                ))
            if "sensitivity" in filters:
                must_filters.append(rest.FieldCondition(
                    key="sensitivity", 
                    match=rest.MatchValue(value=filters["sensitivity"])
                ))
            
            q_filter = rest.Filter(must=must_filters)

            if query_vector:
                search_res = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=q_filter,
                    limit=limit * 2,
                    with_payload=True,
                    with_vectors=True
                )
            else:
                # Scroll if no vector
                search_res, _ = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=q_filter,
                    limit=limit * 2,
                    with_payload=True,
                    with_vectors=True
                )

            results = []
            filtered_count = 0
            now = datetime.utcnow()

            for point in search_res:
                memory = self._point_to_memory(point)

                if memory.is_expired(now):
                    filtered_count += 1
                    continue

                if memory.policy.scope == Scope.AGENT and memory.agent_id != agent_id:
                    filtered_count += 1
                    continue

                if not memory.policy.allow_read:
                    filtered_count += 1
                    continue

                results.append(memory)

            audit = AuditRecord(
                agent_id=agent_id,
                operation="query",
                policy_version=self.policy_version,
                decision="allowed",
                reason="retrieval_guard_enforced",
                actor_id=agent_id,
                metadata={
                    "total_returned": len(results),
                    "filtered_count": filtered_count
                }
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)

            return results[:limit], audit
        except Exception as e:
            raise StorageError(f"Qdrant query failed: {str(e)}")

    def get_audit_log(self, agent_id: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      limit: int = 100) -> List[AuditRecord]:
        """Fetch audit records from Qdrant scroll."""
        try:
            must_filters = []
            if agent_id:
                must_filters.append(rest.FieldCondition(key="agent_id", match=rest.MatchValue(value=agent_id)))
            
            res, _ = self.client.scroll(
                collection_name=self.audit_collection,
                scroll_filter=rest.Filter(must=must_filters),
                limit=limit
            )

            records = []
            for point in res:
                p = point.payload
                record = AuditRecord(
                    audit_id=str(point.id),
                    timestamp=datetime.fromisoformat(p["timestamp"]),
                    agent_id=p["agent_id"],
                    operation=p["operation"],
                    decision=p["decision"],
                    reason=p["reason"],
                    actor_id=p["actor_id"],
                    memory_id=p.get("memory_id"),
                    metadata=p.get("metadata", {})
                )
                object.__setattr__(record, 'signature', p.get("signature", ""))
                records.append(record)
            
            return sorted(records, key=lambda x: x.timestamp, reverse=True)
        except Exception:
            return []

    def health_check(self) -> bool:
        """Check Qdrant health."""
        try:
            return self.client.get_collections() is not None
        except Exception:
            return False

    def write_audit_record(self, record: AuditRecord) -> None:
        """Persist audit record to Qdrant."""
        import uuid
        payload = {
            "timestamp": record.timestamp.isoformat(),
            "agent_id": record.agent_id,
            "operation": record.operation,
            "decision": record.decision,
            "reason": record.reason,
            "actor_id": record.actor_id,
            "memory_id": record.memory_id,
            "signature": record.signature,
            "metadata": record.metadata
        }
        self.client.upsert(
            collection_name=self.audit_collection,
            points=[rest.PointStruct(id=str(uuid.uuid4()), vector={}, payload=payload)]
        )

    # Private Helpers

    def _point_to_memory(self, point: Any) -> Memory:
        """Convert Qdrant point to Memory."""
        p = point.payload
        return Memory(
            memory_id=str(point.id),
            agent_id=p["agent_id"],
            content=p["content"],
            policy=MemoryPolicy(
                memory_type=MemoryType(p["memory_type"]),
                ttl_seconds=p["ttl_seconds"],
                sensitivity=Sensitivity(p["sensitivity"]),
                scope=Scope(p["scope"]),
                allow_read=p.get("allow_read", True),
            ),
            created_at=datetime.fromisoformat(p["created_at"]),
            expires_at=datetime.fromisoformat(p["expires_at"]),
            created_by=p["created_by"],
            vector=point.vector
        )

    def _create_denied_audit(self, agent_id: str, operation: str, memory_id: Optional[str], reason: str) -> AuditRecord:
        """Helper to create and log denied audit."""
        audit = AuditRecord(
            agent_id=agent_id,
            operation=operation,
            memory_id=memory_id,
            policy_version=self.policy_version,
            decision="denied",
            reason=reason,
            actor_id=agent_id,
        )
        object.__setattr__(audit, 'signature', self._sign_record(audit))
        self.write_audit_record(audit)
        return audit

    def _sign_record(self, record: AuditRecord) -> str:
        """Deterministic signature."""
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
