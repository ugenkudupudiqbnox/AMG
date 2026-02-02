import requests
import os

# AMG Langflow Tool Helper
# This can be copy-pasted into a Langflow 'Python Function' or 'Custom Component'
# to give Langflow agents access to the Governance Plane.

class AMGGovernanceTool:
    def __init__(self, api_key: str = "sk-prod-key", base_url: str = "https://api.soc.qbnox.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}

    def record_memory(self, agent_id: str, content: str, memory_type: str = "long_term"):
        """Record memory through the governance plane."""
        payload = {
            "agent_id": agent_id,
            "content": content,
            "memory_type": memory_type,
            "sensitivity": "non_pii",
            "scope": "agent"
        }
        response = requests.post(f"{self.base_url}/memory/write", json=payload, headers=self.headers)
        return response.json()

    def get_context(self, agent_id: str):
        """Build governed context for the agent."""
        payload = {"agent_id": agent_id}
        response = requests.post(f"{self.base_url}/context/build", json=payload, headers=self.headers)
        return response.json()

# Example usage for Langflow Python Component:
# tool = AMGGovernanceTool()
# history = tool.get_context("langflow-agent")
# tool.record_memory("langflow-agent", "User preference: darker theme")
