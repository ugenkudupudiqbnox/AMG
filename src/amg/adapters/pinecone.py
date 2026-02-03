"""Pinecone storage adapter for AMG.

Governs memory stored in Pinecone vector database.
Implements the StorageAdapter interface.
"""

import logging
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union

try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

from ..types import Memory, MemoryPolicy, AuditRecord, Scope, MemoryType, Sensitivity
from ..storage import StorageAdapter, PolicyCheck
from ..errors import MemoryNotFoundError, PolicyEnforcementError, StorageError

logger = logging.getLogger(__name__)

class PineconeStorageAdapter(StorageAdapter):
    """Pinecone adapter with governance enforcement.
    
    Stores memory content and policy in Pinecone metadata.
    Enforces governance at retrieval time.
    """

    def __init__(
        self, 
        api_key: str, 
        index_name: str, 
        dimension: int = 1536,
        environment: Optional[str] = None,
        namespace: str = "amg-memories"
    ):
        """Initialize Pinecone adapter.
        
        Args:
            api_key: Pinecone API key
            index_name: Name of the index
            dimension: Vector dimension
            environment: Pinecone environment (deprecated in some versions)
            namespace: Namespace for memory storage
        """
        if not PINECONE_AVAILABLE:
            raise ImportError("pinecone-client is required. Install with 'pip install pinecone-client'.")
        
        self.pc = Pinecone(api_key=api_key)
        self.index_name = index_name
        self.namespace = namespace
        self.policy_version = "1.0.0"
        
        # Ensure index exists (simplified for V1)
        if index_name not in [idx.name for idx in self.pc.list_indexes()]:
            logger.info(f"Creating Pinecone index: {index_name}")
            self.pc.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
            
        self.index = self.pc.Index(index_name)
        self._audit_namespace = f"{namespace}-audit"

    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Write memory to Pinecone with metadata."""
        if not memory.agent_id:
            raise PolicyEnforcementError("Memory must have agent_id")
        if not memory.vector:
            raise PolicyEnforcementError("Pinecone requires a vector for storage")

        metadata = {
            "agent_id": memory.agent_id,
            "content": memory.content,
            "memory_type": memory.policy.memory_type.value,
            "sensitivity": memory.policy.sensitivity.value,
            "scope": memory.policy.scope.value,
            "ttl_seconds": memory.policy.ttl_seconds,
            "created_at": memory.created_at.isoformat(),
            "expires_at": memory.expires_at.isoformat(),
            "created_by": memory.created_by,
            "provenance": memory.policy.provenance or "",
            "allow_read": int(memory.policy.allow_read),
            "allow_write": int(memory.policy.allow_write),
        }

        try:
            self.index.upsert(
                vectors=[(memory.memory_id, memory.vector, metadata)],
                namespace=self.namespace
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
                    "scope": memory.policy.scope.value,
                },
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            
            # For Pinecone, we "store" audit records in a separate namespace as metadata-only vectors
            # This is a fallback since Pinecone is not a relational DB
            self.write_audit_record(audit)

            return audit
        except Exception as e:
            raise StorageError(f"Pinecone write failed: {str(e)}")

    def read(self, memory_id: str, agent_id: str, 
             policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read from Pinecone with policy enforcement."""
        try:
            res = self.index.fetch(ids=[memory_id], namespace=self.namespace)
            if memory_id not in res.vectors:
                audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_not_found")
                return None, audit

            vec = res.vectors[memory_id]
            metadata = vec.metadata
            memory = self._metadata_to_memory(memory_id, vec.values, metadata)

            if memory.is_expired():
                audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_expired")
                return None, audit

            # Scope check
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
            raise StorageError(f"Pinecone read failed: {str(e)}")

    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Permanently delete from Pinecone."""
        try:
            # We need the agent_id for the audit record, so we fetch it first
            res = self.index.fetch(ids=[memory_id], namespace=self.namespace)
            agent_id = "unknown"
            if memory_id in res.vectors:
                agent_id = res.vectors[memory_id].metadata.get("agent_id", "unknown")

            self.index.delete(ids=[memory_id], namespace=self.namespace)

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
            raise StorageError(f"Pinecone delete failed: {str(e)}")

    def query(self, filters: Dict[str, Any], agent_id: str, 
              policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Query Pinecone with similarity search and retrieval guard."""
        try:
            query_vector = filters.get("vector")
            limit = filters.get("limit", 100)
            
            # Construct Pinecone filter
            pc_filter = {}
            if "memory_types" in filters:
                pc_filter["memory_type"] = {"$in": filters["memory_types"]}
            if "sensitivity" in filters:
                pc_filter["sensitivity"] = filters["sensitivity"]
            if "scope" in filters:
                pc_filter["scope"] = filters["scope"]

            # Governance constraint: default filter for agent/tenant scope
            # Is handled during post-filtering to be secure, but can be optimized here
            # pc_filter["$or"] = [{"scope": "tenant"}, {"agent_id": agent_id}]

            if query_vector:
                res = self.index.query(
                    vector=query_vector,
                    top_k=limit * 2, # Fetch more for post-filtering
                    namespace=self.namespace,
                    filter=pc_filter,
                    include_metadata=True,
                    include_values=True
                )
            else:
                # Pinecone without vector is tricky, we use a dummy zero vector for metadata-only filtering
                # Note: This is inefficient but works for V1 interface
                dummy_vector = [0.0] * self.index.describe_index_stats().dimension
                res = self.index.query(
                    vector=dummy_vector,
                    top_k=limit * 2,
                    namespace=self.namespace,
                    filter=pc_filter,
                    include_metadata=True,
                    include_values=True
                )

            results = []
            filtered_count = 0
            now = datetime.utcnow()

            for match in res.matches:
                memory = self._metadata_to_memory(match.id, match.values, match.metadata)

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
                    "filtered_count": filtered_count,
                    "has_vector": bool(query_vector)
                }
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)

            return results[:limit], audit
        except Exception as e:
            raise StorageError(f"Pinecone query failed: {str(e)}")

    def get_audit_log(self, agent_id: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      limit: int = 100) -> List[AuditRecord]:
        """Fetch audit records from Pinecone audit namespace."""
        # Note: Implementing historical audit query via Pinecone is limited
        # In production, use Postgres for audit logs even if vectors are in Pinecone.
        try:
            # We use dummy vector search to fetch audit records stored as metadata
            dummy_vector = [0.0] * self.index.describe_index_stats().dimension
            pc_filter = {}
            if agent_id:
                pc_filter["agent_id"] = agent_id

            res = self.index.query(
                vector=dummy_vector,
                top_k=limit,
                namespace=self._audit_namespace,
                filter=pc_filter,
                include_metadata=True
            )

            records = []
            for match in res.matches:
                meta = match.metadata
                record = AuditRecord(
                    audit_id=match.id,
                    timestamp=datetime.fromisoformat(meta["timestamp"]),
                    agent_id=meta["agent_id"],
                    operation=meta["operation"],
                    decision=meta["decision"],
                    reason=meta["reason"],
                    actor_id=meta["actor_id"],
                    memory_id=meta.get("memory_id"),
                    metadata=json.loads(meta.get("metadata_json", "{}"))
                )
                object.__setattr__(record, 'signature', meta.get("signature", ""))
                records.append(record)
            
            return sorted(records, key=lambda x: x.timestamp, reverse=True)
        except Exception:
            return []

    def health_check(self) -> bool:
        """Check Pinecone connection."""
        try:
            self.index.describe_index_stats()
            return True
        except Exception:
            return False

    def write_audit_record(self, record: AuditRecord) -> None:
        """Persist audit record to specialized namespace."""
        # Use a zero vector for audit logs as they are metadata-only
        dim = self.index.describe_index_stats().dimension
        zero_vec = [0.0] * dim
        metadata = {
            "timestamp": record.timestamp.isoformat(),
            "agent_id": record.agent_id,
            "operation": record.operation,
            "decision": record.decision,
            "reason": record.reason,
            "actor_id": record.actor_id,
            "memory_id": record.memory_id or "",
            "signature": record.signature or "",
            "metadata_json": json.dumps(record.metadata)
        }
        self.index.upsert(
            vectors=[(record.audit_id, zero_vec, metadata)],
            namespace=self._audit_namespace
        )

    # Private Helpers

    def _metadata_to_memory(self, memory_id: str, vector: List[float], metadata: Dict[str, Any]) -> Memory:
        """Convert Pinecone metadata back to Memory object."""
        return Memory(
            memory_id=memory_id,
            agent_id=metadata["agent_id"],
            content=metadata["content"],
            policy=MemoryPolicy(
                memory_type=MemoryType(metadata["memory_type"]),
                ttl_seconds=int(metadata["ttl_seconds"]),
                sensitivity=Sensitivity(metadata["sensitivity"]),
                scope=Scope(metadata["scope"]),
                allow_read=bool(int(metadata["allow_read"])),
                allow_write=bool(int(metadata["allow_write"])),
                provenance=metadata.get("provenance"),
            ),
            created_at=datetime.fromisoformat(metadata["created_at"]),
            expires_at=datetime.fromisoformat(metadata["expires_at"]),
            created_by=metadata["created_by"],
            vector=vector
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
        """Deterministic signature for audit logs."""
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
