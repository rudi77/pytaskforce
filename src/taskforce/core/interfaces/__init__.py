"""
Core Protocol Interfaces

This package defines protocol interfaces for all external dependencies in the
Taskforce framework. Protocols enable dependency inversion and testability by
defining contracts without coupling to concrete implementations.

Available Protocols:
    - StateManagerProtocol: Session state persistence
    - LLMProviderProtocol: Language model interactions
    - ToolProtocol: Tool execution capabilities

Usage:
    from taskforce.core.interfaces import StateManagerProtocol, LLMProviderProtocol

    def create_lean_agent(
        state_manager: StateManagerProtocol,
        llm_provider: LLMProviderProtocol
    ):
        # LeanAgent implementation uses protocols, not concrete classes
        pass
"""

from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol

__all__ = [
    "StateManagerProtocol",
    "LLMProviderProtocol",
    "ToolProtocol",
    "ApprovalRiskLevel",
]
