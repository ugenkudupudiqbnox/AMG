"""LangChain Remote Agent Example using AMG.

This example demonstrates how a LangChain agent running anywhere can be 
governed by a central AMG instance via HTTP.
"""

from amg.adapters.http import HTTPStorageAdapter, HTTPKillSwitch
from amg.adapters.langchain import AMGChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage

# Configuration
API_URL = "https://api.soc.qbnox.com"
API_KEY = "sk-prod-key"
AGENT_ID = "prod-agent"

def run_agent_workflow():
    print(f"🔗 Connecting to AMG at {API_URL}...")
    
    # 1. Initialize Remote AMG Adapters
    storage = HTTPStorageAdapter(API_URL, API_KEY)
    kill_switch = HTTPKillSwitch(API_URL, API_KEY)
    
    # 2. Setup Governed LangChain History
    # This history object will automatically sync with the remote AMG API
    history = AMGChatMessageHistory(
        agent_id=AGENT_ID,
        storage=storage,
        kill_switch=kill_switch,
        memory_type="long_term",
        sensitivity="non_pii"
    )
    
    print(f"🤖 Starting session for agent: {AGENT_ID}")
    
    # 3. Add messages (triggers remote AMG writes)
    history.add_message(HumanMessage(content="Hello! Can you remember my preference for dark mode?"))
    history.add_message(AIMessage(content="Of course! I've saved that to my long-term memory via AMG governance."))
    
    # 4. Retrieve messages (triggers remote AMG build_context)
    print("\n📜 Retrieving governed history:")
    for msg in history.messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        print(f"  [{role}]: {msg.content}")

if __name__ == "__main__":
    run_agent_workflow()
