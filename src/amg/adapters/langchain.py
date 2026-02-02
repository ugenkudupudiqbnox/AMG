"""LangChain framework adapter for AMG.

Integrates AMG governance into LangChain ecosystems.
Provides:
- AMGChatMessageHistory: A governed implementation of BaseChatMessageHistory
- LangChainGovernedContext: A utility to fetch memory as LangChain documents
"""

from typing import List, Optional, Any, Dict
from datetime import datetime
import logging

# Check for LangChain availability
try:
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
    from langchain_core.documents import Document
    LANGCHAIN_AVAILABLE = True
except ImportError:
    # Define stubs if LangChain is not installed to allow the module to load
    class BaseChatMessageHistory: pass
    class BaseMessage: pass
    class Document: pass
    LANGCHAIN_AVAILABLE = False

from ..types import MemoryType, Sensitivity, Scope
from ..storage import StorageAdapter
from ..kill_switch import KillSwitch
from ..context import GovernedContextBuilder

logger = logging.getLogger(__name__)

class AMGChatMessageHistory(BaseChatMessageHistory):
    """LangChain Chat Message History protected by AMG governance.
    
    This adapter allows LangChain agents to store and retrieve chat history
    through AMG's governance plane.
    
    All reads are subject to:
    - TTL enforcement
    - Sensitivity filtering
    - Kill switch status
    
    All writes are subject to:
    - Policy validation
    - Audit logging
    """

    def __init__(
        self,
        agent_id: str,
        storage: StorageAdapter,
        kill_switch: KillSwitch,
        session_id: str = "default",
        memory_type: str = "short_term",
        sensitivity: str = "non_pii",
        scope: str = "agent",
    ):
        """Initialize AMG-governed chat history.
        
        Args:
            agent_id: The ID of the agent owning this history
            storage: AMG storage adapter
            kill_switch: AMG kill switch instance
            session_id: Logical session/conversation ID (stored in provenance)
            memory_type: AMG memory type (short_term | long_term | episodic)
            sensitivity: Content sensitivity (pii | non_pii)
            scope: Access scope (agent | tenant)
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain is required for AMGChatMessageHistory. "
                              "Install it with 'pip install langchain-core'.")
        
        self.agent_id = agent_id
        self.storage = storage
        self.kill_switch = kill_switch
        self.session_id = session_id
        self.memory_type = memory_type
        self.sensitivity = sensitivity
        self.scope = scope
        self.context_builder = GovernedContextBuilder(storage, kill_switch)

    @property
    def messages(self) -> List[BaseMessage]:
        """Retrieve governed chat history."""
        # Use context builder to fetch filtered/governed memories
        context = self.context_builder.build_context(
            agent_id=self.agent_id,
            memory_filters={"memory_types": [self.memory_type], "scope": self.scope}
        )
        
        messages = []
        for mem in context.memories:
            # Check provenance to filter by session_id if needed
            # (In V1, we use memory metadata for simplicity)
            content = mem.content
            
            # Simple heuristic for message type reconstruction
            # In a production system, you'd store structured data in content
            if content.startswith("Human: "):
                messages.append(HumanMessage(content=content[7:]))
            elif content.startswith("AI: "):
                messages.append(AIMessage(content=content[4:]))
            elif content.startswith("System: "):
                messages.append(SystemMessage(content=content[8:]))
            else:
                messages.append(HumanMessage(content=content))
                
        return messages

    def add_message(self, message: BaseMessage) -> None:
        """Store a new message with AMG governance."""
        # Check kill switch first
        if not self.kill_switch.check_allowed(self.agent_id, "write"):
            logger.warning(f"Memory write denied for agent {self.agent_id}: Kill switch active")
            return

        # Prepare content with prefix for reconstruction
        prefix = ""
        if isinstance(message, HumanMessage): prefix = "Human: "
        elif isinstance(message, AIMessage): prefix = "AI: "
        elif isinstance(message, SystemMessage): prefix = "System: "
        
        content = f"{prefix}{message.content}"
        
        # Write to AMG storage using the correct Interface
        from ..types import Memory, MemoryPolicy
        memory = Memory(
            agent_id=self.agent_id,
            content=content,
            policy=MemoryPolicy(
                memory_type=MemoryType.LONG_TERM if self.memory_type == "long_term" else MemoryType.SHORT_TERM,
                sensitivity=Sensitivity.PII if self.sensitivity == "pii" else Sensitivity.NON_PII,
                scope=Scope.TENANT if self.scope == "tenant" else Scope.AGENT,
                ttl_seconds=86400 # 24h default
            )
        )
        
        self.storage.write(
            memory=memory,
            policy_metadata={"session_id": self.session_id, "source": "langchain_adapter"}
        )

    def clear(self) -> None:
        """Clear session history (governed)."""
        # Decisions on deletion belong to storage policy
        # For LangChain compliance, we might implement a bulk delete
        # but AMG V1 prefers explicit lifecycle management.
        pass


class LangChainGovernedContext:
    """Utility to convert AMG GovernedContext to LangChain Documents."""
    
    @staticmethod
    def get_documents(context: Any) -> List[Document]:
        """Convert memories in context to LangChain Document objects."""
        return [
            Document(
                page_content=mem.content,
                metadata={
                    "memory_id": mem.memory_id,
                    "type": mem.memory_type,
                    "sensitivity": mem.sensitivity,
                    "scope": mem.scope,
                    "created_at": mem.created_at.isoformat() if mem.created_at else None
                }
            )
            for mem in context.memories
        ]
