"""Authentication module for AMG HTTP API."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

import os
from datetime import datetime, timedelta
import hmac
import hashlib

# API Key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthConfig:
    """Authentication configuration."""
    
    def __init__(self):
        """Load auth settings from environment."""
        self.api_keys = {}
        self.load_api_keys()
        self.auth_disabled = os.getenv("AMG_AUTH_DISABLED", "false").lower() == "true"
    
    def load_api_keys(self):
        """Load API keys from environment.
        
        Expected format: AMG_API_KEYS="key1:agent-123,key2:agent-456"
        """
        keys_env = os.getenv("AMG_API_KEYS", "")
        if not keys_env:
            # Default test key (insecure - use env var in production)
            self.api_keys["test-key-12345"] = "test-agent"
            return
        
        for entry in keys_env.split(","):
            if ":" in entry:
                api_key, agent_id = entry.split(":", 1)
                self.api_keys[api_key.strip()] = agent_id.strip()
    
    def validate_api_key(self, api_key: Optional[str]) -> Optional[str]:
        """Validate API key and return agent_id.
        
        Returns:
            Agent ID if key is valid, None otherwise
        """
        if self.auth_disabled:
            return "default-agent"
        
        if not api_key:
            return None
        
        return self.api_keys.get(api_key)


# Global auth config
_auth_config = None


def get_auth_config() -> AuthConfig:
    """Get or create auth config."""
    global _auth_config
    if _auth_config is None:
        _auth_config = AuthConfig()
    return _auth_config


async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)) -> str:
    """Verify API key and return agent_id.
    
    Raises:
        HTTPException: If key is invalid or missing
    """
    config = get_auth_config()
    
    # If auth is disabled, allow all access
    if config.auth_disabled:
        return "default-agent"
    
    # Validate the API key
    agent_id = config.validate_api_key(api_key)
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return agent_id


def generate_api_key(agent_id: str, secret: str = "amg-secret") -> str:
    """Generate an API key for an agent.
    
    Args:
        agent_id: Agent identifier
        secret: Secret for HMAC (use strong secret in production)
    
    Returns:
        API key in format: {agent_id}.{signature}
    """
    message = f"{agent_id}:{datetime.utcnow().isoformat()}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()[:16]
    return f"{agent_id}.{signature}"
