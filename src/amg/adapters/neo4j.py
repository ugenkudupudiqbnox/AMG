"""Neo4j graph storage adapter for AMG.

Governs memory stored as nodes in a Neo4j database.
Implements the StorageAdapter interface.
Enforces governance at the node level.
"""

import logging
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

from ..types import Memory, MemoryPolicy, AuditRecord, Scope, MemoryType, Sensitivity
from ..storage import StorageAdapter, PolicyCheck
from ..errors import MemoryNotFoundError, PolicyEnforcementError, StorageError

logger = logging.getLogger(__name__)

class Neo4jStorageAdapter(StorageAdapter):
    """Neo4j adapter with governance enforcement.
    
    Stores memories as :Memory nodes.
    Governance rules are stored as node properties.
    """

    def __init__(
        self, 
        uri: str = "bolt://localhost:7687", 
        user: str = "neo4j", 
        password: str = "password",
        database: str = "neo4j"
    ):
        """Initialize Neo4j adapter.
        
        Args:
            uri: Neo4j URI
            user: Username
            password: Password
            database: Target database
        """
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j driver is required. Install with 'pip install neo4j'.")
        
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.policy_version = "1.0.0"
        self._initialize_constraints()

    def close(self):
        """Close driver connection."""
        self.driver.close()

    def _initialize_constraints(self):
        """Ensure uniqueness constraints exist."""
        with self.driver.session(database=self.database) as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (m:Memory) REQUIRE m.memory_id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:AuditLog) REQUIRE a.audit_id IS UNIQUE")

    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Write memory as a node with governance metadata."""
        if not memory.agent_id:
            raise PolicyEnforcementError("Memory must have agent_id")

        query = """
        MERGE (m:Memory {memory_id: $memory_id})
        SET m.agent_id = $agent_id,
            m.content = $content,
            m.memory_type = $memory_type,
            m.sensitivity = $sensitivity,
            m.scope = $scope,
            m.ttl_seconds = $ttl_seconds,
            m.created_at = $created_at,
            m.expires_at = $expires_at,
            m.created_by = $created_by,
            m.allow_read = $allow_read,
            m.allow_write = $allow_write,
            m.vector = $vector
        RETURN m
        """
        
        params = {
            "memory_id": memory.memory_id,
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
            "allow_write": memory.policy.allow_write,
            "vector": json.dumps(memory.vector) if memory.vector else None
        }

        try:
            with self.driver.session(database=self.database) as session:
                session.run(query, **params)

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
            raise StorageError(f"Neo4j write failed: {str(e)}")

    def read(self, memory_id: str, agent_id: str, 
             policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read node with policy check."""
        query = "MATCH (m:Memory {memory_id: $memory_id}) RETURN m"
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, {"memory_id": memory_id})
                record = result.single()
                
                if not record:
                    audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_not_found")
                    return None, audit
                
                node = record["m"]
                memory = self._node_to_memory(node)

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
            raise StorageError(f"Neo4j read failed: {str(e)}")

    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Permanently delete node and its relationships."""
        query = "MATCH (m:Memory {memory_id: $memory_id}) DETACH DELETE m RETURN m.agent_id as agent_id"
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, {"memory_id": memory_id})
                record = result.single()
                agent_id = record["agent_id"] if record else "unknown"

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
            raise StorageError(f"Neo4j delete failed: {str(e)}")

    def query(self, filters: Dict[str, Any], agent_id: str, 
              policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Query Neo4j with retrieval guard (filters applied in Cypher)."""
        where_clauses = ["(m.scope = 'tenant' OR m.agent_id = $agent_id)"]
        params = {"agent_id": agent_id}

        if "memory_types" in filters:
            where_clauses.append("m.memory_type IN $memory_types")
            params["memory_types"] = filters["memory_types"]
        
        if "sensitivity" in filters:
            where_clauses.append("m.sensitivity = $sensitivity")
            params["sensitivity"] = filters["sensitivity"]

        where_sql = " AND ".join(where_clauses)
        limit = filters.get("limit", 100)
        
        query = f"""
        MATCH (m:Memory)
        WHERE {where_sql}
        RETURN m
        ORDER BY m.created_at DESC
        LIMIT $limit
        """
        params["limit"] = limit

        try:
            results = []
            filtered_count = 0
            now = datetime.utcnow()

            with self.driver.session(database=self.database) as session:
                records = session.run(query, **params)
                for record in records:
                    memory = self._node_to_memory(record["m"])

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

            return results, audit
        except Exception as e:
            raise StorageError(f"Neo4j query failed: {str(e)}")

    def get_audit_log(self, agent_id: Optional[str] = None, **kwargs) -> List[AuditRecord]:
        """Fetch audit records from Neo4j."""
        where = "WHERE a.agent_id = $agent_id" if agent_id else ""
        query = f"MATCH (a:AuditLog) {where} RETURN a ORDER BY a.timestamp DESC LIMIT $limit"
        
        try:
            records = []
            with self.driver.session(database=self.database) as session:
                res = session.run(query, {"agent_id": agent_id, "limit": kwargs.get("limit", 100)})
                for r in res:
                    node = r["a"]
                    record = AuditRecord(
                        audit_id=node["audit_id"],
                        timestamp=datetime.fromisoformat(node["timestamp"]),
                        agent_id=node["agent_id"],
                        operation=node["operation"],
                        decision=node["decision"],
                        reason=node["reason"],
                        actor_id=node["actor_id"],
                        memory_id=node.get("memory_id"),
                        metadata=json.loads(node.get("metadata_json", "{}"))
                    )
                    object.__setattr__(record, 'signature', node.get("signature", ""))
                    records.append(record)
            return records
        except Exception:
            return []

    def health_check(self) -> bool:
        """Check Neo4j status."""
        try:
            with self.driver.session(database=self.database) as session:
                session.run("RETURN 1")
            return True
        except Exception:
            return False

    def write_audit_record(self, record: AuditRecord) -> None:
        """Persist audit record to Neo4j."""
        query = """
        CREATE (a:AuditLog {
            audit_id: $audit_id,
            timestamp: $timestamp,
            agent_id: $agent_id,
            operation: $operation,
            decision: $decision,
            reason: $reason,
            actor_id: $actor_id,
            memory_id: $memory_id,
            metadata_json: $metadata_json,
            signature: $signature
        })
        """
        params = {
            "audit_id": record.audit_id,
            "timestamp": record.timestamp.isoformat(),
            "agent_id": record.agent_id,
            "operation": record.operation,
            "decision": record.decision,
            "reason": record.reason,
            "actor_id": record.actor_id,
            "memory_id": record.memory_id or "",
            "metadata_json": json.dumps(record.metadata),
            "signature": record.signature
        }
        with self.driver.session(database=self.database) as session:
            session.run(query, **params)

    # Private Helpers

    def _node_to_memory(self, node: Any) -> Memory:
        """Convert Neo4j node to Memory."""
        return Memory(
            memory_id=node["memory_id"],
            agent_id=node["agent_id"],
            content=node["content"],
            policy=MemoryPolicy(
                memory_type=MemoryType(node["memory_type"]),
                ttl_seconds=int(node["ttl_seconds"]),
                sensitivity=Sensitivity(node["sensitivity"]),
                scope=Scope(node["scope"]),
                allow_read=bool(node["allow_read"]),
            ),
            created_at=datetime.fromisoformat(node["created_at"]),
            expires_at=datetime.fromisoformat(node["expires_at"]),
            created_by=node["created_by"],
            vector=json.loads(node["vector"]) if node.get("vector") else None
        )

    def _create_denied_audit(self, agent_id: str, operation: str, memory_id: Optional[str], reason: str) -> AuditRecord:
        """Create and log denied audit."""
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
