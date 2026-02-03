
import pytest
from amg.types import Memory, MemoryPolicy, MemoryType, Sensitivity, Scope
from amg.adapters import InMemoryStorageAdapter, PostgresStorageAdapter
from amg.storage import PolicyCheck

@pytest.mark.parametrize("adapter_class", [InMemoryStorageAdapter, PostgresStorageAdapter])
def test_vector_similarity_search(adapter_class):
    """Test that vector similarity search returns most similar items first."""
    if adapter_class == PostgresStorageAdapter:
        adapter = adapter_class(":memory:")
    else:
        adapter = adapter_class()
        
    policy = MemoryPolicy(
        memory_type=MemoryType.LONG_TERM,
        ttl_seconds=86400,
        sensitivity=Sensitivity.NON_PII,
        scope=Scope.AGENT,
    )
    
    # Create memories with distinct vectors
    m1 = Memory(
        agent_id="agent-123",
        content="Vector [1, 0]",
        policy=policy,
        vector=[1.0, 0.0]
    )
    m2 = Memory(
        agent_id="agent-123",
        content="Vector [0, 1]",
        policy=policy,
        vector=[0.0, 1.0]
    )
    m3 = Memory(
        agent_id="agent-123",
        content="Vector [0.7, 0.7]",
        policy=policy,
        vector=[0.7, 0.7]
    )
    
    adapter.write(m1, {})
    adapter.write(m2, {})
    adapter.write(m3, {})
    
    policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
    
    # Query with vector [1, 0]
    memories, _ = adapter.query(
        filters={"vector": [1.0, 0.0]},
        agent_id="agent-123",
        policy_check=policy_check
    )
    
    assert len(memories) == 3
    assert memories[0].memory_id == m1.memory_id
    assert memories[1].content == "Vector [0.7, 0.7]" # Closer to [1,0] than [0,1] is
    assert memories[2].memory_id == m2.memory_id

def test_vector_passthrough_api():
    """Test that vector field persists through write/read."""
    adapter = InMemoryStorageAdapter()
    policy = MemoryPolicy(
        memory_type=MemoryType.LONG_TERM,
        ttl_seconds=86400,
        sensitivity=Sensitivity.NON_PII,
        scope=Scope.AGENT,
    )
    
    vector = [0.1, 0.2, 0.3]
    m = Memory(
        agent_id="agent-123",
        content="Test vector",
        policy=policy,
        vector=vector
    )
    
    adapter.write(m, {})
    
    policy_check = PolicyCheck(agent_id="agent-123", allowed_scopes=[Scope.AGENT])
    memory, _ = adapter.read(m.memory_id, "agent-123", policy_check)
    
    assert memory.vector == vector
