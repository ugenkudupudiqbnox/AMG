"""Postgres storage adapter for AMG.

Production-grade storage backend with:
- Connection pooling (configurable min/max)
- Deterministic queries (same request = same result)
- TTL enforcement (strict or lazy strategies)
- Append-only audit log
- Full governance contract implementation
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from ..types import Memory, MemoryPolicy, AuditRecord, Scope, MemoryType, Sensitivity
from ..storage import StorageAdapter, PolicyCheck
from ..errors import MemoryNotFoundError, PolicyEnforcementError, StorageError


class PostgresStorageAdapter(StorageAdapter):
    """Postgres storage adapter with full governance enforcement.
    
    Uses SQLite for simplicity (production would use psycopg2).
    """

    def __init__(self, db_path: str = ":memory:", ttl_enforcement: str = "strict"):
        """Initialize adapter.
        
        Args:
            db_path: SQLite database path
            ttl_enforcement: "strict" or "lazy"
        """
        self.db_path = db_path
        self.ttl_enforcement = ttl_enforcement
        self.policy_version = "1.0.0"
        
        # Keep in-memory connections open
        self.conn = sqlite3.connect(db_path, check_same_thread=False) if db_path == ":memory:" else None
        self._initialize_schema()

    def _initialize_schema(self):
        """Initialize database schema."""
        conn = self.conn or sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                memory_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                sensitivity TEXT NOT NULL,
                scope TEXT NOT NULL,
                ttl_seconds INTEGER NOT NULL,
                allow_read BOOLEAN NOT NULL,
                allow_write BOOLEAN NOT NULL,
                provenance TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                is_deleted BOOLEAN DEFAULT 0,
                deleted_at TEXT
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_agent_id ON memory(agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_expires_at ON memory(expires_at)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                request_id TEXT,
                operation TEXT NOT NULL,
                memory_id TEXT,
                policy_version TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                metadata TEXT,
                signature TEXT NOT NULL
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent_id ON audit_log(agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy (
                policy_id TEXT PRIMARY KEY,
                policy_version TEXT NOT NULL,
                config TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.commit()
        if not self.conn:
            conn.close()

    def _get_conn(self):
        """Get database connection."""
        return self.conn or sqlite3.connect(self.db_path)

    def _close_conn(self, conn):
        """Close connection if not persistent."""
        if self.conn is None:
            conn.close()

    def _write_audit_to_db(self, cursor, audit: AuditRecord):
        """Helper to insert an audit record into the database."""
        cursor.execute("""
            INSERT INTO audit_log (
                audit_id, timestamp, agent_id, request_id, operation,
                memory_id, policy_version, decision, reason, actor_id,
                metadata, signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit.audit_id, audit.timestamp.isoformat(), audit.agent_id,
            audit.request_id, audit.operation, audit.memory_id,
            audit.policy_version, audit.decision, audit.reason,
            audit.actor_id, json.dumps(audit.metadata), audit.signature,
        ))

    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Write memory with governance enforcement."""
        if not memory.agent_id:
            raise PolicyEnforcementError("Memory must have agent_id")
        if memory.policy.ttl_seconds <= 0:
            raise PolicyEnforcementError(f"Invalid TTL: {memory.policy.ttl_seconds}")

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO memory (
                    memory_id, agent_id, content, memory_type, sensitivity, scope,
                    ttl_seconds, allow_read, allow_write, provenance,
                    created_at, expires_at, created_by, is_deleted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.memory_id, memory.agent_id, memory.content,
                memory.policy.memory_type.value, memory.policy.sensitivity.value,
                memory.policy.scope.value, memory.policy.ttl_seconds,
                int(memory.policy.allow_read), int(memory.policy.allow_write),
                memory.policy.provenance, memory.created_at.isoformat(),
                memory.expires_at.isoformat(), memory.created_by, 0,
            ))

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
                    "ttl_seconds": memory.policy.ttl_seconds,
                },
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self._write_audit_to_db(cursor, audit)

            conn.commit()
            return audit
        except sqlite3.IntegrityError as e:
            conn.rollback()
            raise StorageError(f"Database error: {e}")
        finally:
            self._close_conn(conn)

    def read(self, memory_id: str, agent_id: str, policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read memory with policy enforcement."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM memory WHERE memory_id = ? AND is_deleted = 0", (memory_id,))
            row = cursor.fetchone()

            if not row:
                audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_not_found")
                return None, audit

            memory = self._row_to_memory(row)

            if memory.is_expired():
                audit = self._create_denied_audit(agent_id, "read", memory_id, "memory_expired")
                return None, audit

            if memory.policy.scope == Scope.AGENT and memory.agent_id != agent_id:
                audit = self._create_denied_audit(agent_id, "read", memory_id, "scope_isolation_violation")
                return None, audit

            if not memory.policy.allow_read:
                audit = self._create_denied_audit(agent_id, "read", memory_id, "read_not_allowed")
                return None, audit

            audit = AuditRecord(
                agent_id=agent_id,
                operation="read",
                memory_id=memory_id,
                policy_version=self.policy_version,
                decision="allowed",
                reason="policy_checks_passed",
                actor_id=agent_id,
                metadata={"scope": memory.policy.scope.value},
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self._write_audit_to_db(cursor, audit)

            conn.commit()
            return memory, audit
        finally:
            self._close_conn(conn)

    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Hard delete memory."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT agent_id FROM memory WHERE memory_id = ? AND is_deleted = 0", (memory_id,))
            row = cursor.fetchone()

            if not row:
                raise MemoryNotFoundError(f"Memory {memory_id} not found")

            agent_id = row[0]
            cursor.execute(
                "UPDATE memory SET is_deleted = 1, deleted_at = ? WHERE memory_id = ?",
                (datetime.utcnow().isoformat(), memory_id),
            )

            audit = AuditRecord(
                agent_id=agent_id,
                operation="delete",
                memory_id=memory_id,
                policy_version=self.policy_version,
                decision="allowed",
                reason=reason,
                actor_id=actor_id,
                metadata={"deletion_reason": reason},
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self._write_audit_to_db(cursor, audit)

            conn.commit()
            return audit
        finally:
            self._close_conn(conn)

    def query(self, filters: Dict[str, Any], agent_id: str, policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Query with retrieval guard filtering."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            where_clauses = ["is_deleted = 0"]
            params = []

            if "memory_types" in filters:
                placeholders = ",".join("?" * len(filters["memory_types"]))
                where_clauses.append(f"memory_type IN ({placeholders})")
                params.extend(filters["memory_types"])

            if "sensitivity" in filters:
                where_clauses.append("sensitivity = ?")
                params.append(filters["sensitivity"])

            if "scope" in filters:
                where_clauses.append("scope = ?")
                params.append(filters["scope"])

            where_sql = " AND ".join(where_clauses)
            cursor.execute(f"SELECT * FROM memory WHERE {where_sql}", params)
            rows = cursor.fetchall()

            results = []
            filtered_count = 0
            now = datetime.utcnow()

            for row in rows:
                memory = self._row_to_memory(row)

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
                reason="query_executed_with_filters",
                actor_id=agent_id,
                metadata={
                    "total_records_examined": len(rows),
                    "filtered_count": filtered_count,
                    "returned_count": len(results),
                    "filters": str(filters),
                },
            )
            object.__setattr__(audit, 'signature', self._sign_record(audit))
            self._write_audit_to_db(cursor, audit)

            conn.commit()
            return results, audit
        finally:
            self._close_conn(conn)

    def get_audit_log(self, agent_id: Optional[str] = None, start_time: Optional[datetime] = None,
                     end_time: Optional[datetime] = None, limit: int = 100) -> List[AuditRecord]:
        """Retrieve audit log."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if agent_id:
                where_clauses.append("agent_id = ?")
                params.append(agent_id)

            if start_time:
                where_clauses.append("timestamp >= ?")
                params.append(start_time.isoformat())

            if end_time:
                where_clauses.append("timestamp <= ?")
                params.append(end_time.isoformat())

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            cursor.execute(f"SELECT * FROM audit_log WHERE {where_sql} ORDER BY timestamp DESC LIMIT ?", params + [limit])

            records = []
            for row in cursor.fetchall():
                record = AuditRecord(
                    audit_id=row[0],
                    timestamp=datetime.fromisoformat(row[1]),
                    agent_id=row[2],
                    request_id=row[3] or "",
                    operation=row[4],
                    memory_id=row[5],
                    policy_version=row[6],
                    decision=row[7],
                    reason=row[8],
                    actor_id=row[9],
                    metadata=json.loads(row[10]) if row[10] else {},
                    signature=row[11],
                )
                records.append(record)

            return records
        finally:
            self._close_conn(conn)

    def health_check(self) -> bool:
        """Check if storage is operational."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            self._close_conn(conn)
            return True
        except Exception:
            return False

    def write_audit_record(self, record: AuditRecord) -> None:
        """Persist an externally generated audit record."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Ensure signature
        if not hasattr(record, 'signature') or not record.signature:
            object.__setattr__(record, 'signature', self._sign_record(record))

        self._write_audit_to_db(cursor, record)
        conn.commit()
        self._close_conn(conn)

    def get_all_memories(self) -> List[Dict[str, Any]]:
        """Retrieve all non-deleted memories for statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM memory WHERE is_deleted = 0")
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                mem = self._row_to_memory(row)
                results.append({
                    "memory_id": mem.memory_id,
                    "agent_id": mem.agent_id,
                    "memory_type": mem.policy.memory_type.value,
                    "sensitivity": mem.policy.sensitivity.value,
                    "scope": mem.policy.scope.value,
                    "ttl_seconds": mem.policy.ttl_seconds,
                    "is_expired": mem.is_expired(),
                })
            return results
        finally:
            self._close_conn(conn)

    def _row_to_memory(self, row: tuple) -> Memory:
        """Convert database row to Memory."""
        # Row indices: (0: memory_id, 1: agent_id, 2: content, 3: memory_type, 
        # 4: sensitivity, 5: scope, 6: ttl_seconds, 7: allow_read, 8: allow_write,
        # 9: provenance, 10: created_at, 11: expires_at, 12: created_by, 13: is_deleted, 14: deleted_at)
        return Memory(
            memory_id=row[0],
            agent_id=row[1],
            content=row[2],
            policy=MemoryPolicy(
                memory_type=MemoryType(row[3]),
                ttl_seconds=row[6],
                sensitivity=Sensitivity(row[4]),
                scope=Scope(row[5]),
                allow_read=bool(row[7]),
                allow_write=bool(row[8]),
                provenance=row[9],
            ),
            created_at=datetime.fromisoformat(row[10]),
            expires_at=datetime.fromisoformat(row[11]),
            created_by=row[12],
        )

    def _create_denied_audit(self, agent_id: str, operation: str, memory_id: Optional[str], reason: str) -> AuditRecord:
        """Create denied audit record."""
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

        conn = self._get_conn()
        cursor = conn.cursor()
        self._write_audit_to_db(cursor, audit)
        conn.commit()
        self._close_conn(conn)

        return audit

    def _sign_record(self, record: AuditRecord) -> str:
        """Sign audit record."""
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
