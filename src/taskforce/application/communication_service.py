"""Application service for handling external communication messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from taskforce.application.executor import AgentExecutor
from taskforce.core.domain.enums import MessageRole
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.interfaces.communication import ConversationStoreProtocol


@dataclass(frozen=True)
class CommunicationResponse:
    """Result of handling an inbound communication message."""

    session_id: str
    status: str
    reply: str
    history: list[dict[str, Any]]


@dataclass(frozen=True)
class CommunicationOptions:
    """Execution options for communication handling."""

    profile: str = "dev"
    session_id: str | None = None
    user_context: dict[str, Any] | None = None
    agent_id: str | None = None
    planning_strategy: str | None = None
    planning_strategy_params: dict[str, Any] | None = None
    plugin_path: str | None = None


class CommunicationService:
    """Coordinate inbound messages, history, and agent execution."""

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        conversation_store: ConversationStoreProtocol,
    ) -> None:
        self._executor = executor
        self._conversation_store = conversation_store

    async def handle_message(
        self,
        *,
        provider: str,
        conversation_id: str,
        message: str,
        options: CommunicationOptions | None = None,
    ) -> CommunicationResponse:
        """Handle a message from an external communication provider."""
        resolved_options = options or CommunicationOptions()
        resolved_session_id, updated_history = await self._prepare_history(
            provider=provider,
            conversation_id=conversation_id,
            session_id=resolved_options.session_id,
            message=message,
        )
        return await self._execute_and_store(
            provider=provider,
            conversation_id=conversation_id,
            message=message,
            profile=resolved_options.profile,
            session_id=resolved_session_id,
            conversation_history=updated_history,
            user_context=resolved_options.user_context,
            agent_id=resolved_options.agent_id,
            planning_strategy=resolved_options.planning_strategy,
            planning_strategy_params=resolved_options.planning_strategy_params,
            plugin_path=resolved_options.plugin_path,
        )

    async def _prepare_history(
        self,
        *,
        provider: str,
        conversation_id: str,
        session_id: str | None,
        message: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        resolved_session_id = await self._resolve_session_id(
            provider=provider,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        history = await self._conversation_store.load_history(provider, conversation_id)
        updated_history = self._append_message(
            history,
            MessageRole.USER.value,
            message,
        )
        return resolved_session_id, updated_history

    async def _execute_and_store(
        self,
        *,
        provider: str,
        conversation_id: str,
        message: str,
        profile: str,
        session_id: str,
        conversation_history: list[dict[str, Any]],
        user_context: dict[str, Any] | None,
        agent_id: str | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
        plugin_path: str | None,
    ) -> CommunicationResponse:
        result = await self._execute_agent(
            message=message,
            profile=profile,
            session_id=session_id,
            conversation_history=conversation_history,
            user_context=user_context,
            agent_id=agent_id,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            plugin_path=plugin_path,
        )
        final_history = self._append_message(
            conversation_history,
            MessageRole.ASSISTANT.value,
            result.final_message,
        )
        await self._conversation_store.save_history(provider, conversation_id, final_history)
        return CommunicationResponse(
            session_id=session_id,
            status=result.status,
            reply=result.final_message,
            history=final_history,
        )

    async def _execute_agent(
        self,
        *,
        message: str,
        profile: str,
        session_id: str,
        conversation_history: list[dict[str, Any]],
        user_context: dict[str, Any] | None,
        agent_id: str | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
        plugin_path: str | None,
    ) -> ExecutionResult:
        return await self._executor.execute_mission(
            mission=message,
            profile=profile,
            session_id=session_id,
            conversation_history=conversation_history,
            user_context=user_context,
            agent_id=agent_id,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            plugin_path=plugin_path,
        )

    async def _resolve_session_id(
        self,
        *,
        provider: str,
        conversation_id: str,
        session_id: str | None,
    ) -> str:
        if session_id:
            await self._conversation_store.set_session_id(
                provider,
                conversation_id,
                session_id,
            )
            return session_id
        existing = await self._conversation_store.get_session_id(
            provider,
            conversation_id,
        )
        if existing:
            return existing
        generated = str(uuid4())
        await self._conversation_store.set_session_id(
            provider,
            conversation_id,
            generated,
        )
        return generated

    @staticmethod
    def _append_message(
        history: list[dict[str, Any]],
        role: str,
        content: str,
    ) -> list[dict[str, Any]]:
        return [*history, {"role": role, "content": content}]
