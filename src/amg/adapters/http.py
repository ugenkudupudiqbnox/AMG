"""HTTP Client Adapter for AMG.

Allows remote agents to communicate with the AMG Governance Plane via REST API.
Implements the StorageAdapter interface to allow use with framework adapters.
"""

import requests
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from ..types import Memory, MemoryType, Sensitivity, Scope, AuditRecord
from ..storage import StorageAdapter, PolicyCheck

logger = logging.getLogger(__name__)

class HTTPStorageAdapter(StorageAdapter):
    """Storage adapter that proxies calls to a remote AMG API.
    
    This allows LangChain/LangGraph adapters to run on remote clients
    while maintaining governance on the central AMG server.
    """
    
    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }

    def write(self, memory: Memory, policy_metadata: Dict[str, Any]) -> AuditRecord:
        """Proxy write to remote API."""
        url = f"{self.api_base_url}/memory/write"
        
        # Map types back to strings for JSON
        type_str = {
            MemoryType.SHORT_TERM: "short_term",
            MemoryType.LONG_TERM: "long_term",
            MemoryType.EPISODIC: "episodic"
        }.get(memory.policy.memory_type, "short_term")

        sens_str = {
            Sensitivity.PII: "pii",
            Sensitivity.NON_PII: "non_pii"
        }.get(memory.policy.sensitivity, "non_pii")

        scope_str = {
            Scope.AGENT: "agent",
            Scope.TENANT: "tenant"
        }.get(memory.policy.scope, "agent")

        payload = {
            "agent_id": memory.agent_id,
            "content": memory.content,
            "memory_type": type_str,
            "sensitivity": sens_str,
            "scope": scope_str,
            "ttl_seconds": memory.policy.ttl_seconds
        }
        
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        
        # In a real system, we'd reconstruct the full AuditRecord
        # For the proxy, we return a simplified version
        return AuditRecord(
            audit_id=data.get("audit_id", "remote-write"),
            timestamp=datetime.utcnow(),
            agent_id=memory.agent_id,
            operation="write",
            decision=data.get("decision", "allowed"),
            reason="remote_api_proxy",
            metadata=data
        )

    def read(self, memory_id: str, agent_id: str, 
             policy_check: PolicyCheck) -> Tuple[Optional[Memory], AuditRecord]:
        """Read is currently simplified via build_context in V1 API."""
        # For now, we raise NotImplemented or proxy to a search if available
        # The V1 API focuses on build_context for retrieval
        raise NotImplementedError("Direct read not supported via HTTP proxy. Use build_context.")

    def query(self, filters: Dict[str, Any], agent_id: str, 
              policy_check: PolicyCheck) -> Tuple[List[Memory], AuditRecord]:
        """Proxy query/build_context to remote API."""
        url = f"{self.api_base_url}/context/build"
        
        # Map filters for context build API
        payload = {
            "agent_id": agent_id,
            "memory_types": filters.get("memory_types"),
            "max_items": filters.get("max_items", 50),
            "max_tokens": filters.get("max_tokens", 4000)
        }
        
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        
        # Reconstruct Memory objects from response
        memories = []
        for mem_data in data.get("memories", []):
            # For brevity in proxy, we reconstruct minimal Memory objects
            # In a full impl, we'd need more careful type conversion
            from ..types import MemoryPolicy
            m = Memory(
                memory_id=mem_data["memory_id"],
                agent_id=agent_id,
                content=mem_data["content"],
                policy=MemoryPolicy(
                    memory_type=MemoryType.SHORT_TERM, # Default
                    sensitivity=Sensitivity.NON_PII,
                    scope=Scope.AGENT,
                    ttl_seconds=86400
                )
            )
            memories.append(m)
            
        audit = AuditRecord(
            audit_id=data.get("metadata", {}).get("audit_id", "remote-query"),
            timestamp=datetime.utcnow(),
            agent_id=agent_id,
            operation="query",
            decision="allowed",
            reason="remote_api_proxy",
            metadata=data.get("metadata", {})
        )
        return memories, audit

    def get_audit_log(self, agent_id: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      operation: Optional[str] = None,
                      limit: int = 100,
                      offset: int = 0) -> List[AuditRecord]:
        """Proxy audit log retrieval."""
        url = f"{self.api_base_url}/audit/export"
        params = {"limit": limit, "offset": offset}
        if agent_id: params["agent_id"] = agent_id
        if start_time: params["start_date"] = start_time.isoformat()
        if end_time: params["end_date"] = end_time.isoformat()
        if operation: params["operation"] = operation
        
        response = requests.get(url, params=params, headers=self.headers)
        
        response = requests.get(url, params=params, headers=self.headers)
        if response.status_code != 200: return []
        
        records = []
        for rec in response.json().get("records", []):
            records.append(AuditRecord(
                audit_id=rec["audit_id"],
                timestamp=datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")),
                agent_id=rec["agent_id"],
                operation=rec["operation"],
                decision=rec["decision"],
                reason=rec["reason"],
                metadata=rec["metadata"]
            ))
        return records

    def delete(self, memory_id: str, actor_id: str, reason: str) -> AuditRecord:
        """Call DELETE on remote API (if implemented)."""
        raise NotImplementedError("Delete not yet supported via HTTP proxy.")

    def health_check(self) -> bool:
        """Check remote API health."""
        try:
            resp = requests.get(f"{self.api_base_url}/health", headers=self.headers)
            return resp.status_code == 200
        except:
            return False

    def write_audit_record(self, record: AuditRecord) -> None:
        """HTTP proxy doesn't support direct audit persistence (server handles it)."""
        pass

class HTTPKillSwitch:
    """Kill switch proxy for remote APIs."""
    
    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}

    def check_allowed(self, agent_id: str, operation: str) -> Tuple[bool, str]:
        """Check if agent is allowed to perform operation."""
        try:
            resp = requests.get(f"{self.api_base_url}/agent/{agent_id}/status", headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                if operation == "write":
                    return data.get("memory_write") == "allowed", data.get("state", "unknown")
                return data.get("enabled", True), data.get("state", "unknown")
            return True, "status_check_failed"
        except:
            return True, "network_error"

class HTTPAMGClient:
    """A client for the AMG API.
    
    This is NOT a full StorageAdapter (as it doesn't handle the DB), 
    but it provides a similar interface for remote agents.
    """
    
    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }

    def write(self, agent_id: str, content: str, memory_type: str, 
              sensitivity: str, scope: str = "agent", ttl_seconds: Optional[int] = None) -> Dict:
        """Call /memory/write."""
        url = f"{self.api_base_url}/memory/write"
        payload = {
            "agent_id": agent_id,
            "content": content,
            "memory_type": memory_type,
            "sensitivity": sensitivity,
            "scope": scope,
            "ttl_seconds": ttl_seconds
        }
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def build_context(self, agent_id: str, memory_types: Optional[List[str]] = None, 
                      max_tokens: int = 4000, max_items: int = 50) -> Dict:
        """Call /context/build."""
        url = f"{self.api_base_url}/context/build"
        payload = {
            "agent_id": agent_id,
            "memory_types": memory_types,
            "max_tokens": max_tokens,
            "max_items": max_items
        }
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def check_status(self, agent_id: str) -> Dict:
        """Call /agent/{agent_id}/status."""
        url = f"{self.api_base_url}/agent/{agent_id}/status"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
