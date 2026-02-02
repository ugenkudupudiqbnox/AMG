"""Langflow integration for AMG.

Provides templates and utility classes for using AMG Memory Governance
within Langflow environments.
"""

from typing import Optional, Any
import logging

try:
    # Langflow custom component base classes
    # These might be in flux depending on Langflow version
    # but we provide the standard logic.
    from langflow.interface.custom.custom_component import CustomComponent
    from langflow.field_typing import BaseChatMessageHistory
    LANGFLOW_AVAILABLE = True
except ImportError:
    class CustomComponent: pass
    LANGFLOW_AVAILABLE = False

from .langchain import AMGChatMessageHistory
from ..storage import StorageAdapter
from ..kill_switch import KillSwitch


class AMGLangflowComponent(CustomComponent):
    """Langflow Component for AMG Memory Governance.
    
    This can be pasted into a Langflow Custom Component to integrate
    governed memory into your flows.
    """
    
    display_name = "AMG Governed Memory"
    description = "Managed memory with TTL, sensitivity filtering, and kill switch."
    icon = "shield-check"

    def build_config(self):
        return {
            "agent_id": {"display_name": "Agent ID", "info": "The identity of the agent"},
            "api_endpoint": {"display_name": "AMG API Endpoint", "info": "URL of the AMG server"},
            "api_key": {"display_name": "API Key", "password": True},
            "memory_type": {
                "display_name": "Memory Type",
                "options": ["short_term", "long_term", "episodic"],
                "value": "short_term"
            },
            "sensitivity": {
                "display_name": "Sensitivity",
                "options": ["non_pii", "pii"],
                "value": "non_pii"
            }
        }

    def build(
        self,
        agent_id: str,
        storage: StorageAdapter,
        kill_switch: KillSwitch,
        memory_type: str = "short_term",
        sensitivity: str = "non_pii",
        session_id: Optional[str] = None,
    ) -> Any:
        """Construct the governed chat history."""
        return AMGChatMessageHistory(
            agent_id=agent_id,
            storage=storage,
            kill_switch=kill_switch,
            session_id=session_id or "langflow_session",
            memory_type=memory_type,
            sensitivity=sensitivity
        )


def get_langflow_template() -> str:
    """Returns a standalone Python script for a Langflow Custom Component."""
    return """
from langflow.interface.custom.custom_component import CustomComponent
from langflow.field_typing import BaseChatMessageHistory
from amg.adapters.langchain import AMGChatMessageHistory
from amg.adapters.postgres import PostgresStorageAdapter # Or other
from amg.kill_switch import KillSwitch

class AMGMirrorComponent(CustomComponent):
    display_name = "AMG Memory"
    def build(self, agent_id: str, db_url: str) -> BaseChatMessageHistory:
        # Example setup
        storage = PostgresStorageAdapter(connection_string=db_url)
        kill_switch = KillSwitch(storage)
        return AMGChatMessageHistory(agent_id=agent_id, storage=storage, kill_switch=kill_switch)
"""
