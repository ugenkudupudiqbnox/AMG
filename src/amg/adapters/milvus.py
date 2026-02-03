"""Milvus storage adapter for AMG.

Governs memory stored in Milvus vector database.
Implements the StorageAdapter interface.
"""

import logging
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

try:
    from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
    MILVUS_AVAILABLE = True
except ImportError:
    MILVUS_AVAILABLE = False

from ..types import Memory, MemoryPolicy, AuditRecord, Scope, MemoryType, Sensitivity
from ..storage import StorageAdapter, PolicyCheck
from ..errors import MemoryNotFoundError, PolicyEnforcementError, StorageError

logger = logging.getLogger(__name__)

class MilvusStorageAdapter(StorageAdapter):
    """Milvus adapter with governance enforcement.
    
    Ensures absolute separation of agent memory and enforces governance
    using Milvus expression filters.
    """

    def __init__(
        self, 
        host: str = "localhost", 
        port: str = "19530", 
        collection_name: str = "amg_memories",
        dimension: int = 1536
    ):
        """Initialize Milvus adapter."""
        if not MILVUS_AVAILABLE:
            raise ImportError("pymilvus is required. Install with 'pip install pymilvus'.")
        
        self.collection_name = collection_name
        self.audit_collection_name = f"{collection_name}_audit"
        self.policy_version = "1.0.0"
        
        connections.connect("default", host=host, port=port)
        self._ensure_collections(dimension)

    def _ensure_collections(self, dimension: int):
        """Create Milvus collections if needed."""
        if not utility.has_collection(self.collection_name):
            fields = [
                FieldSchema(name="memory_id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                FieldSchema(name="agent_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dimension),
                FieldSchema(name="memory_type", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="sensitivity", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="scope", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="ttl_seconds", dtype=DataType.INT64),
                FieldSchema(name="created_at", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="expires_at", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="created_by", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="allow_read", dtype=DataType.BOOL),
            ]
            schema = CollectionSchema(fields, "AMG Memory Storage")
            Collection(self.collection_name, schema)
            
        if not utility.has_collection(self.audit_collection_name):
            fields = [
                FieldSchema(name="audit_id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="agent_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="operation", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="decision", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="reason", dtype=DataType.VARCHAR, max_length=200),
                FieldSchema(name="actor_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="memory_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="signature", dtype=DataType.VARCHAR, max_length=200),
            ]
            schema = CollectionSchema(fields, "AMG Audit Logs")
            Collection(self.audit_collection_name, schema)

        self.collection = Collection(self.collection_name)
        self.audit_collection = Collection(self.audit_collection_name)
        
        # Ensure indexes
        if not self.collection.has_index():
            self.collection.create_index("vector", {"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 128}})
        self.collection.load()
        self.audit_collection.load()

    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Write memory to Milvus."""
        if not memory.agent_id:
            raise PolicyEnforcementError("Memory must have agent_id")
        if not memory.vector:
            raise PolicyEnforcementError("Milvus requires a vector for storage")

        data = [
            [memory.memory_id], [memory.agent_id], [memory.content], [memory.vector],
            [memory.policy.memory_type.value], [memory.policy.sensitivity.value],
            [memory.policy.scope.value], [memory.policy.ttl_seconds],
            [memory.created_at.isoformat()], [memory.expires_at.isoformat()],
            [memory.created_by], [memory.policy.allow_read]
        ]

        try:
            self.collection.insert(data)

            audit = AuditRecord(
                agent_id=memory.agent_id,
                request_id=policy_metadata.get("request_id", ""),
                operation="write",
                memory_id=memory.memory_id,
                policy_version=self.policy_version,
                decision="allowed",
                reason="policy_enforcement_passed",
                actor_id=memory.agent_id,
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)

            return audit
        except Exception as e:
            raise StorageError(f"Milvus write failed: {str(e)}")

    def read(self, memory_id: str, agent_id: str, 
             policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read from Milvus with query."""
        try:
            res = self.collection.query(expr=f"memory_id == '{memory_id}'", output_fields=["*"])
            
            if not res:
                audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_not_found")
                return None, audit

            res = res[0]
            memory = self._row_to_memory(res)

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
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)

            return memory, audit
        except Exception as e:
            raise StorageError(f"Milvus read failed: {str(e)}")

    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Delete from Milvus."""
        try:
            res = self.collection.query(expr=f"memory_id == '{memory_id}'", output_fields=["agent_id"])
            agent_id = res[0]["agent_id"] if res else "unknown"

            self.collection.delete(f"memory_id in ['{memory_id}']")

            audit = AuditRecord(
                agent_id=agent_id,
                operation="delete",
                memory_id=memory_id,
                policy_version=self.policy_version,
                decision="allowed",
                reason=reason,
                actor_id=actor_id,
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)
            return audit
        except Exception as e:
            raise StorageError(f"Milvus delete failed: {str(e)}")

    def query(self, filters: Dict[str, Any], agent_id: str, 
              policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Query Milvus with retrieval guard."""
        try:
            query_vector = filters.get("vector")
            limit = filters.get("limit", 100)
            
            # Build Milvus expression
            expr_parts = []
            if "memory_types" in filters:
                types = ", ".join([f"'{t}'" for t in filters["memory_types"]])
                expr_parts.append(f"memory_type in [{types}]")
            if "sensitivity" in filters:
                expr_parts.append(f"sensitivity == '{filters['sensitivity']}'")
            
            # Governance: restrict by agent/tenant scope
            expr_parts.append(f"(scope == 'tenant' or agent_id == '{agent_id}')")
            
            expr = " and ".join(expr_parts)

            if query_vector:
                search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
                res = self.collection.search(
                    data=[query_vector],
                    anns_field="vector",
                    param=search_params,
                    limit=limit * 2,
                    expr=expr,
                    output_fields=["*"]
                )
                res = res[0] # Single query vector
            else:
                res = self.collection.query(expr=expr, output_fields=["*"], limit=limit * 2)

            results = []
            filtered_count = 0
            now = datetime.utcnow()

            for hit in res:
                # hit is different for search vs query
                row = hit.entity if hasattr(hit, 'entity') else hit
                memory = self._row_to_memory(row)

                if memory.is_expired(now):
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
                metadata={"total_returned": len(results), "filtered_count": filtered_count}
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self.write_audit_record(audit)

            return results[:limit], audit
        except Exception as e:
            raise StorageError(f"Milvus query failed: {str(e)}")

    def get_audit_log(self, agent_id: Optional[str] = None, **kwargs) -> List[AuditRecord]:
        """Fetch audit logs."""
        try:
            expr = f"agent_id == '{agent_id}'" if agent_id else ""
            res = self.audit_collection.query(expr=expr, output_fields=["*"], limit=kwargs.get("limit", 100))
            
            records = []
            for r in res:
                record = AuditRecord(
                    audit_id=r["audit_id"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    agent_id=r["agent_id"],
                    operation=r["operation"],
                    decision=r["decision"],
                    reason=r["reason"],
                    actor_id=r["actor_id"],
                    memory_id=r.get("memory_id"),
                )
                object.__setattr__(record, 'signature', r.get("signature", ""))
                records.append(record)
            return sorted(records, key=lambda x: x.timestamp, reverse=True)
        except Exception:
            return []

    def health_check(self) -> bool:
        """Check Milvus status."""
        try:
            return utility.has_collection(self.collection_name)
        except Exception:
            return False

    def write_audit_record(self, record: AuditRecord) -> None:
        """Persist audit record."""
        data = [
            [record.audit_id], [record.timestamp.isoformat()], [record.agent_id],
            [record.operation], [record.decision], [record.reason],
            [record.actor_id], [record.memory_id or ""], [record.signature or ""]
        ]
        self.audit_collection.insert(data)

    def _row_to_memory(self, row: Dict[str, Any]) -> Memory:
        """Convert Milvus row to Memory."""
        return Memory(
            memory_id=row["memory_id"],
            agent_id=row["agent_id"],
            content=row["content"],
            policy=MemoryPolicy(
                memory_type=MemoryType(row["memory_type"]),
                ttl_seconds=int(row["ttl_seconds"]),
                sensitivity=Sensitivity(row["sensitivity"]),
                scope=Scope(row["scope"]),
                allow_read=row.get("allow_read", True),
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_by=row["created_by"],
            vector=row.get("vector")
        )

    def _create_denied_audit(self, agent_id: str, operation: str, memory_id: Optional[str], reason: str) -> AuditRecord:
        """Create denied audit."""
        audit = AuditRecord(agent_id=agent_id, operation=operation, memory_id=memory_id, 
                             policy_version=self.policy_version, decision="denied", reason=reason, actor_id=agent_id)
        object.__setattr__(audit, 'signature', self._sign_record(audit))
        self.write_audit_record(audit)
        return audit

    def _sign_record(self, record: AuditRecord) -> str:
        """Sign record."""
        record_str = json.dumps({"audit_id": record.audit_id, "timestamp": record.timestamp.isoformat(), "agent_id": record.agent_id, "operation": record.operation, "memory_id": record.memory_id, "decision": record.decision, "reason": record.reason}, sort_keys=True)
        return hashlib.sha256(record_str.encode()).hexdigest()
