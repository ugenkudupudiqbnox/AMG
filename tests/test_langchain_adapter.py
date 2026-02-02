"""Tests for LangChain framework adapter."""

import pytest
from unittest.mock import MagicMock
from amg.adapters.langchain import AMGChatMessageHistory, LANGCHAIN_AVAILABLE

if not LANGCHAIN_AVAILABLE:
    pytest.skip("LangChain not installed, skipping adapter tests", allow_module_level=True)

from langchain_core.messages import HumanMessage, AIMessage

@pytest.fixture
def mock_amg():
    storage = MagicMock()
    kill_switch = MagicMock()
    kill_switch.check_allowed.return_value = True
    return storage, kill_switch

def test_langchain_history_add_message(mock_amg):
    storage, kill_switch = mock_amg
    history = AMGChatMessageHistory(
        agent_id="test-agent",
        storage=storage,
        kill_switch=kill_switch
    )

    msg = HumanMessage(content="Hello AMG")
    history.add_message(msg)

    # Verify storage write was called with correct mapping
    storage.write.assert_called_once()
    args, kwargs = storage.write.call_args
    assert kwargs['agent_id'] == "test-agent"
    assert "Human: Hello AMG" in kwargs['content']
    assert kwargs['memory_type'] == "short_term"

def test_langchain_history_get_messages(mock_amg):
    storage, kill_switch = mock_amg
    history = AMGChatMessageHistory(
        agent_id="test-agent",
        storage=storage,
        kill_switch=kill_switch
    )

    # Mock context builder response
    mock_mem = MagicMock()
    mock_mem.content = "AI: I am a governed AI"
    
    mock_context = MagicMock()
    mock_context.memories = [mock_mem]
    
    history.context_builder.build_context = MagicMock(return_value=mock_context)

    messages = history.messages
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)
    assert messages[0].content == "I am a governed AI"

def test_langchain_kill_switch_enforcement(mock_amg):
    storage, kill_switch = mock_amg
    kill_switch.check_allowed.return_value = False # Agent disabled
    
    history = AMGChatMessageHistory(
        agent_id="disabled-agent",
        storage=storage,
        kill_switch=kill_switch
    )
    
    history.add_message(HumanMessage(content="This should fail"))
    
    # Storage should never be called
    storage.write.assert_not_called()
