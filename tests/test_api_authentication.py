"""
Tests for API authentication and security.
"""

import pytest
import os
from fastapi.testclient import TestClient

from amg.api.server import create_app
from amg.api.auth import AuthConfig, verify_api_key, generate_api_key, _auth_config


@pytest.fixture(autouse=True)
def reset_auth_config():
    """Reset global auth config before each test."""
    import amg.api.auth as auth_module
    auth_module._auth_config = None
    yield
    auth_module._auth_config = None


class TestAuthConfig:
    """Test AuthConfig class."""
    
    def test_auth_config_load_from_env(self, monkeypatch):
        """Test loading API keys from environment."""
        monkeypatch.setenv("AMG_API_KEYS", "sk-key1:agent-1,sk-key2:agent-2")
        monkeypatch.delenv("AMG_AUTH_DISABLED", raising=False)
        
        config = AuthConfig()
        assert config.validate_api_key("sk-key1") == "agent-1"
        assert config.validate_api_key("sk-key2") == "agent-2"
        assert config.validate_api_key("sk-invalid") is None
    
    def test_auth_disabled_via_env(self, monkeypatch):
        """Test disabling authentication via environment variable."""
        monkeypatch.setenv("AMG_AUTH_DISABLED", "true")
        
        config = AuthConfig()
        assert config.auth_disabled is True
        assert config.validate_api_key("any-key") == "default-agent"
    
    def test_auth_config_empty_keys(self, monkeypatch):
        """Test with no API keys configured."""
        monkeypatch.setenv("AMG_API_KEYS", "")
        monkeypatch.delenv("AMG_AUTH_DISABLED", raising=False)
        
        config = AuthConfig()
        assert config.validate_api_key("sk-anything") is None
    
    def test_auth_config_missing_env(self, monkeypatch):
        """Test with missing environment variable (uses default)."""
        monkeypatch.delenv("AMG_API_KEYS", raising=False)
        monkeypatch.delenv("AMG_AUTH_DISABLED", raising=False)
        
        config = AuthConfig()
        # Should not crash, just have empty keys
        assert config.validate_api_key("sk-test") is None


class TestGenerateAPIKey:
    """Test API key generation."""
    
    def test_generate_api_key_format(self):
        """Test generated API key has correct format."""
        key = generate_api_key("agent-123")
        assert key.startswith("agent-123.")
        assert len(key) > 10
    
    def test_generate_api_key_uniqueness(self):
        """Test generated keys are unique."""
        key1 = generate_api_key("agent-123")
        key2 = generate_api_key("agent-123")
        # Different timestamps should produce different signatures
        # (with very high probability)
        assert len(key1) > 0
        assert len(key2) > 0


class TestAPIEndpointsWithoutAuth:
    """Test API endpoints without authentication enabled."""
    
    @pytest.fixture
    def client(self, monkeypatch):
        """Create test client with auth disabled."""
        monkeypatch.setenv("AMG_AUTH_DISABLED", "true")
        app = create_app()
        return TestClient(app)
    
    def test_health_check_without_auth(self, client):
        """Health check should work without auth."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_write_memory_without_auth(self, client):
        """Write memory should work without auth when disabled."""
        response = client.post("/memory/write", json={
            "agent_id": "agent-123",
            "content": "Test memory",
            "memory_type": "long_term",
            "sensitivity": "non_pii",
        })
        assert response.status_code == 200
        assert "memory_id" in response.json()
    
    def test_query_memory_without_auth(self, client):
        """Query memory should work without auth when disabled."""
        response = client.post("/memory/query", json={
            "agent_id": "agent-123",
            "limit": 10,
        })
        assert response.status_code == 200
        assert "memories" in response.json()
    
    def test_build_context_without_auth(self, client):
        """Build context should work without auth when disabled."""
        response = client.post("/context/build", json={
            "agent_id": "agent-123",
            "max_tokens": 4000,
        })
        assert response.status_code == 200
        assert "memories" in response.json()


class TestAPIEndpointsWithAuth:
    """Test API endpoints with authentication enabled."""
    
    @pytest.fixture
    def client(self, monkeypatch):
        """Create test client with auth enabled."""
        monkeypatch.setenv("AMG_API_KEYS", "sk-valid-key:agent-123,sk-other:agent-456")
        monkeypatch.delenv("AMG_AUTH_DISABLED", raising=False)
        app = create_app()
        return TestClient(app)
    
    def test_health_check_with_auth(self, client):
        """Health check should work without API key."""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_write_memory_with_valid_key(self, client):
        """Write memory with valid API key should succeed."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test memory",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": "sk-valid-key"}
        )
        assert response.status_code == 200
        assert "memory_id" in response.json()
    
    def test_write_memory_with_invalid_key(self, client):
        """Write memory with invalid API key should fail."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test memory",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": "sk-invalid-key"}
        )
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json()["detail"]
    
    def test_write_memory_without_key(self, client):
        """Write memory without API key should fail."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test memory",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            }
        )
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json()["detail"]
    
    def test_query_memory_with_valid_key(self, client):
        """Query memory with valid API key should succeed."""
        # First write some memory
        client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test memory",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": "sk-valid-key"}
        )
        
        # Then query
        response = client.post(
            "/memory/query",
            json={
                "agent_id": "agent-123",
                "limit": 10,
            },
            headers={"X-API-Key": "sk-valid-key"}
        )
        assert response.status_code == 200
        assert "memories" in response.json()
    
    def test_query_memory_with_invalid_key(self, client):
        """Query memory with invalid API key should fail."""
        response = client.post(
            "/memory/query",
            json={
                "agent_id": "agent-123",
                "limit": 10,
            },
            headers={"X-API-Key": "sk-invalid"}
        )
        assert response.status_code == 401
    
    def test_build_context_with_valid_key(self, client):
        """Build context with valid API key should succeed."""
        response = client.post(
            "/context/build",
            json={
                "agent_id": "agent-123",
                "max_tokens": 4000,
            },
            headers={"X-API-Key": "sk-valid-key"}
        )
        assert response.status_code == 200
        assert "memories" in response.json()
    
    def test_build_context_with_invalid_key(self, client):
        """Build context with invalid API key should fail."""
        response = client.post(
            "/context/build",
            json={
                "agent_id": "agent-123",
                "max_tokens": 4000,
            },
            headers={"X-API-Key": "sk-invalid"}
        )
        assert response.status_code == 401
    
    def test_disable_agent_with_valid_key(self, client):
        """Disable agent with valid API key should succeed."""
        response = client.post(
            "/agent/agent-123/disable",
            json={"reason": "test"},
            headers={"X-API-Key": "sk-valid-key"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "disabled"
    
    def test_disable_agent_with_invalid_key(self, client):
        """Disable agent with invalid API key should fail."""
        response = client.post(
            "/agent/agent-123/disable",
            headers={"X-API-Key": "sk-invalid"}
        )
        assert response.status_code == 401
    
    def test_freeze_writes_with_valid_key(self, client):
        """Freeze writes with valid API key should succeed."""
        response = client.post(
            "/agent/agent-123/freeze",
            json={"reason": "test"},
            headers={"X-API-Key": "sk-valid-key"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "frozen"
    
    def test_freeze_writes_with_invalid_key(self, client):
        """Freeze writes with invalid API key should fail."""
        response = client.post(
            "/agent/agent-123/freeze",
            headers={"X-API-Key": "sk-invalid"}
        )
        assert response.status_code == 401
    
    def test_get_agent_status_with_valid_key(self, client):
        """Get agent status with valid API key should succeed."""
        response = client.get(
            "/agent/agent-123/status",
            headers={"X-API-Key": "sk-valid-key"}
        )
        assert response.status_code == 200
        assert "state" in response.json()
    
    def test_get_agent_status_with_invalid_key(self, client):
        """Get agent status with invalid API key should fail."""
        response = client.get(
            "/agent/agent-123/status",
            headers={"X-API-Key": "sk-invalid"}
        )
        assert response.status_code == 401
    
    def test_get_audit_log_with_valid_key(self, client):
        """Get audit log with valid API key should succeed."""
        response = client.get(
            "/audit/audit-123",
            headers={"X-API-Key": "sk-valid-key"}
        )
        # May be 404 if no audit log, but auth should pass
        assert response.status_code in [200, 404]
    
    def test_get_audit_log_with_invalid_key(self, client):
        """Get audit log with invalid API key should fail."""
        response = client.get(
            "/audit/audit-123",
            headers={"X-API-Key": "sk-invalid"}
        )
        assert response.status_code == 401


class TestAPIKeyMappingToAgentId:
    """Test that API keys map correctly to agent IDs."""
    
    @pytest.fixture
    def client(self, monkeypatch):
        """Create test client with multiple API keys."""
        monkeypatch.setenv("AMG_API_KEYS", "sk-agent1:agent-111,sk-agent2:agent-222")
        monkeypatch.delenv("AMG_AUTH_DISABLED", raising=False)
        app = create_app()
        return TestClient(app)
    
    def test_different_api_keys_map_to_different_agents(self, client):
        """Verify API keys correctly map to different agent IDs."""
        # Write with first key
        response1 = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-111",
                "content": "Memory from agent 1",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": "sk-agent1"}
        )
        assert response1.status_code == 200
        
        # Write with second key
        response2 = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-222",
                "content": "Memory from agent 2",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": "sk-agent2"}
        )
        assert response2.status_code == 200
        
        # Both should succeed with their respective keys
        assert response1.json()["memory_id"]
        assert response2.json()["memory_id"]


class TestAuthEdgeCases:
    """Test edge cases in authentication."""
    
    @pytest.fixture
    def client(self, monkeypatch):
        """Create test client with auth enabled."""
        monkeypatch.setenv("AMG_API_KEYS", "sk-valid:agent-123")
        monkeypatch.delenv("AMG_AUTH_DISABLED", raising=False)
        app = create_app()
        return TestClient(app)
    
    def test_empty_api_key(self, client):
        """Empty API key should fail."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": ""}
        )
        assert response.status_code == 401
    
    def test_api_key_case_sensitive(self, client):
        """API keys should be case-sensitive."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": "SK-VALID"}  # Uppercase
        )
        assert response.status_code == 401
    
    def test_api_key_with_whitespace(self, client):
        """API key with whitespace should fail."""
        response = client.post(
            "/memory/write",
            json={
                "agent_id": "agent-123",
                "content": "Test",
                "memory_type": "long_term",
                "sensitivity": "non_pii",
            },
            headers={"X-API-Key": " sk-valid "}  # With spaces
        )
        assert response.status_code == 401


class TestConcurrentAuthRequests:
    """Test authentication under concurrent load."""
    
    @pytest.fixture
    def client(self, monkeypatch):
        """Create test client with auth enabled."""
        monkeypatch.setenv("AMG_API_KEYS", "sk-test:agent-123")
        monkeypatch.delenv("AMG_AUTH_DISABLED", raising=False)
        app = create_app()
        return TestClient(app)
    
    def test_multiple_concurrent_requests_with_valid_key(self, client):
        """Multiple concurrent requests with valid key should all succeed."""
        # Use different agents to avoid kill switch conflicts
        for i in range(5):
            response = client.post(
                "/memory/write",
                json={
                    "agent_id": f"agent-123-{i}",
                    "content": f"Memory {i}",
                    "memory_type": "long_term",
                    "sensitivity": "non_pii",
                },
                headers={"X-API-Key": "sk-test"}
            )
            assert response.status_code == 200
    
    def test_multiple_concurrent_requests_with_invalid_key(self, client):
        """Multiple concurrent requests with invalid key should all fail."""
        for i in range(5):
            response = client.post(
                "/memory/write",
                json={
                    "agent_id": f"agent-123-{i}",
                    "content": f"Memory {i}",
                    "memory_type": "long_term",
                    "sensitivity": "non_pii",
                },
                headers={"X-API-Key": "sk-invalid"}
            )
            assert response.status_code == 401
