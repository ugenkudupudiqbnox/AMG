"""LangGraph Remote Agent Example using AMG.

Demonstrates non-invasive governance for stateful LangGraph workflows.
"""

import operator
from typing import Annotated, TypedDict, List
from amg.adapters.http import HTTPStorageAdapter, HTTPKillSwitch
from amg.adapters.langgraph import LangGraphMemoryAdapter

# Configuration
API_URL = "https://api.soc.qbnox.com"
API_KEY = "sk-prod-key"
AGENT_ID = "prod-agent"

# 1. Define State
class GraphState(TypedDict):
    agent_id: str
    messages: Annotated[List[str], operator.add]
    memory_content: str
    context: List[str]

# 2. Initialize Adapter
storage = HTTPStorageAdapter(API_URL, API_KEY)
kill_switch = HTTPKillSwitch(API_URL, API_KEY)
amg = LangGraphMemoryAdapter(storage, kill_switch)

# 3. Define Nodes
def research_node(state: GraphState):
    print("🔍 [Node: Research] Fetching governed memory...")
    # Fetch context from AMG
    ctx = amg.build_context(agent_id=state['agent_id'])
    return {"context": [m.content for m in ctx.memories]}

def write_node(state: GraphState):
    print("✍️ [Node: Memory] Recording new insight...")
    # Record memory through AMG governance
    amg.record_memory(
        agent_id=state['agent_id'],
        content="Insight: User preferrs secure-first architecture.",
        memory_type="long_term",
        sensitivity="non_pii"
    )
    return {"messages": ["Recorded insight to AMG"]}

def run_workflow():
    print(f"🌲 Executing LangGraph governed workflow for {AGENT_ID}...")
    
    # Simulate partial graph execution
    state: GraphState = {
        "agent_id": AGENT_ID,
        "messages": ["Start workflow"],
        "memory_content": "",
        "context": []
    }
    
    # Node 1: Research
    res = research_node(state)
    state.update(res)
    print(f"  Found {len(state['context'])} memories in AMG context.")
    
    # Node 2: Write
    res = write_node(state)
    state.update(res)
    
    print("\n✅ LangGraph workflow completed with AMG governance.")

if __name__ == "__main__":
    run_workflow()
