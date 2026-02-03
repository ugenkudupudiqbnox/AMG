"""
LangGraph Integration Example with AMG.

Demonstrates how to wrap a LangGraph state machine with AMG governance
to ensure all memory access is audited and policy-enforced.
"""

from typing import Annotated, TypedDict, List
import operator
from langgraph.graph import StateGraph, END

from amg.adapters.in_memory import InMemoryStorageAdapter
from amg.kill_switch import KillSwitch
from amg.adapters.langgraph import LangGraphMemoryAdapter

# 1. Define the Graph State
class AgentState(TypedDict):
    agent_id: str
    input: str
    output: str
    # We use Annotated for simple list accumulation in LangGraph
    history: Annotated[List[str], operator.add]

# 2. Setup AMG Adapter
# In production, this would use PostgresStorageAdapter and HTTPKillSwitch
storage = InMemoryStorageAdapter()
kill_switch = KillSwitch() # No arguments needed
amg = LangGraphMemoryAdapter(storage, kill_switch)

# 3. Define the Nodes
def gather_context_node(state: AgentState):
    print(f"🔍 [AMG] Building governed context for {state['agent_id']}...")
    
    # Retrieve memories through the AMG governance layer
    context = amg.build_context(agent_id=state['agent_id'])
    
    # Simulate adding the retrieved context to histoy
    current_history = [m.content for m in context.memories]
    return {"history": current_history}

def process_node(state: AgentState):
    print("🤖 Processing request based on context...")
    response = f"Processed input '{state['input']}' with {len(state['history'])} context items."
    return {"output": response}

def record_insight_node(state: AgentState):
    print("✍️ [AMG] Recording new episodic memory...")
    
    # Save the interaction to AMG
    amg.record_memory(
        agent_id=state['agent_id'],
        content=f"Human said: {state['input']}. Resolution: {state['output']}",
        memory_type="episodic",
        sensitivity="non_pii"
    )
    return {}

# 4. Construct the Graph
workflow = StateGraph(AgentState)

workflow.add_node("gather_context", gather_context_node)
workflow.add_node("process", process_node)
workflow.add_node("record_insight", record_insight_node)

workflow.set_entry_point("gather_context")
workflow.add_edge("gather_context", "process")
workflow.add_edge("process", "record_insight")
workflow.add_edge("record_insight", END)

# 5. Compile and Run
app = workflow.compile()

if __name__ == "__main__":
    test_agent = "governed-graph-agent-01"
    
    print(f"--- Running LangGraph with AMG Governance ---")
    initial_state = {
        "agent_id": test_agent,
        "input": "How can I improve my infrastructure security?",
        "history": [],
        "output": ""
    }
    
    # First Run (Empty memory)
    print("\n--- Interaction 1 ---")
    app.invoke(initial_state)

    # Second Run (Should see memory from Interaction 1)
    print("\n--- Interaction 2 ---")
    app.invoke({**initial_state, "input": "Tell me what we talked about last time."})

    print("\n✅ Multi-turn interaction governed by AMG complete.")
