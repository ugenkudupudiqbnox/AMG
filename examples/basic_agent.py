"""
Basic Governed Agent Example.

Demonstrates a simple agent loop using AMG directly for memory governance
without any external frameworks.
"""

import time
from amg.policy import PolicyEngine
from amg.kill_switch import KillSwitch
from amg.adapters.in_memory import InMemoryStorageAdapter
from amg.context import GovernedContextBuilder

def simple_agent_loop():
    # 1. Setup AMG Infrastructure
    storage = InMemoryStorageAdapter()
    kill_switch = KillSwitch() # No arguments needed
    policy = PolicyEngine()
    context_builder = GovernedContextBuilder(storage, kill_switch, policy)

    agent_id = "agent-007"
    print(f"Starting Basic Governed Agent: {agent_id}")

    # 2. Record some initial memory
    # Note: Using the internal storage.write usually requires a Memory object.
    # We'll create one manually to show the governance contract.
    print("Recording initial user preference...")
    
    from amg.types import Memory, MemoryPolicy, MemoryType, Sensitivity, Scope
    from datetime import datetime, timedelta
    
    memory = Memory(
        agent_id=agent_id,
        content="User preferred coffee: Espresso.",
        policy=MemoryPolicy(
            memory_type=MemoryType.LONG_TERM,
            sensitivity=Sensitivity.NON_PII,
            scope=Scope.AGENT,
            ttl_seconds=3600
        )
    )
    
    storage.write(memory, {"request_id": "initial-setup"})

    # 3. Simulate a response cycle
    print("\nCycle 1: Thinking...")
    
    # Always build context through the GovernedContextBuilder
    context = context_builder.build_context(agent_id=agent_id)
    
    print(f"   Context retrieved: {len(context.memories)} items.")
    for mem in context.memories:
        print(f"   [Memory]: {mem.content}")

    # 4. Demonstrate Kill Switch Enforcement
    print("\nSimulating security incident: Disabling Agent...")
    kill_switch.disable(agent_id, reason="Manual override test", actor_id="admin-1")

    print("Cycle 2: Attempting to read memory after disable...")
    try:
        context_builder.build_context(agent_id=agent_id)
    except Exception as e:
        print(f"   Governance Blocked Access: {e}")

if __name__ == "__main__":
    simple_agent_loop()
