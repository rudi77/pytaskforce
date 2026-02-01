import pytest

from taskforce.application.communication_service import (
    CommunicationOptions,
    CommunicationService,
)
from taskforce.core.domain.models import ExecutionResult
from taskforce_extensions.infrastructure.communication.conversation_store import (
    InMemoryConversationStore,
)


class FakeExecutor:
    async def execute_mission(self, **kwargs) -> ExecutionResult:
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="Antwort",
        )


@pytest.mark.asyncio
async def test_service_tracks_history_and_session() -> None:
    store = InMemoryConversationStore()
    service = CommunicationService(
        executor=FakeExecutor(),
        conversation_store=store,
    )

    response = await service.handle_message(
        provider="telegram",
        conversation_id="conv-42",
        message="Hallo!",
        options=CommunicationOptions(profile="dev"),
    )

    session_id = await store.get_session_id("telegram", "conv-42")
    history = await store.load_history("telegram", "conv-42")

    assert response.session_id == session_id
    assert response.reply == "Antwort"
    assert history == [
        {"role": "user", "content": "Hallo!"},
        {"role": "assistant", "content": "Antwort"},
    ]
