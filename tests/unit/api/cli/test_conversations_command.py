"""Tests for the conversations CLI command (ADR-016)."""

import asyncio

import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner

from taskforce.api.cli.commands.conversations import app

runner = CliRunner()


@pytest.fixture
def populated_store(tmp_path, monkeypatch):
    """Set up a ConversationManager with some data."""
    monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))

    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.infrastructure.persistence.file_conversation_store import (
        FileConversationStore,
    )

    store = FileConversationStore(work_dir=str(tmp_path))
    mgr = ConversationManager(store)

    async def _setup():
        conv_id = await mgr.get_or_create("cli", "user-1")
        await mgr.append_message(conv_id, {"role": "user", "content": "Hello"})
        await mgr.append_message(conv_id, {"role": "assistant", "content": "Hi!"})
        return conv_id

    conv_id = asyncio.run(_setup())
    return conv_id, mgr


class TestListCommand:
    def test_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No conversations found" in result.output

    def test_list_active(self, populated_store):
        conv_id, _ = populated_store
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert conv_id in result.output

    def test_list_archived(self, populated_store):
        conv_id, mgr = populated_store
        asyncio.run(mgr.archive(conv_id, summary="Test archive"))
        result = runner.invoke(app, ["list", "--archived"])
        assert result.exit_code == 0


class TestShowCommand:
    def test_show_messages(self, populated_store):
        conv_id, _ = populated_store
        result = runner.invoke(app, ["show", conv_id])
        assert result.exit_code == 0
        assert "Hello" in result.output
        assert "Hi!" in result.output

    def test_show_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))
        result = runner.invoke(app, ["show", "nonexistent-id"])
        assert result.exit_code == 1


class TestArchiveCommand:
    def test_archive_conversation(self, populated_store):
        conv_id, _ = populated_store
        result = runner.invoke(app, ["archive", conv_id])
        assert result.exit_code == 0
        assert "archived" in result.output


class TestRenameCommand:
    def test_rename_updates_topic(self, populated_store):
        conv_id, mgr = populated_store
        result = runner.invoke(app, ["rename", conv_id, "Important chat"])
        assert result.exit_code == 0, result.output
        assert "renamed" in result.output.lower()
        # Verify through the manager directly — the Rich table column truncates
        # narrow widths in test output, so we can't assert via CLI list output.
        active = asyncio.run(mgr.list_active())
        match = next(c for c in active if c.conversation_id == conv_id)
        assert match.topic == "Important chat"

    def test_rename_unknown_id_exits_with_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))
        result = runner.invoke(app, ["rename", "ghost-id", "Title"])
        assert result.exit_code == 1

    def test_rename_empty_title_exits_with_invalid_input(self, populated_store):
        conv_id, _ = populated_store
        result = runner.invoke(app, ["rename", conv_id, "   "])
        # Validation error => exit 2 (typer.Exit(2)).
        assert result.exit_code == 2


class TestDeleteCommand:
    def test_delete_with_yes_skips_prompt(self, populated_store):
        conv_id, mgr = populated_store
        result = runner.invoke(app, ["delete", conv_id, "--yes"])
        assert result.exit_code == 0, result.output
        assert "deleted" in result.output.lower()
        # No longer in active list.
        list_result = runner.invoke(app, ["list"])
        assert conv_id not in list_result.output

    def test_delete_aborts_when_user_declines_confirmation(self, populated_store):
        conv_id, _ = populated_store
        # Send "n" to the typer confirm prompt.
        result = runner.invoke(app, ["delete", conv_id], input="n\n")
        assert result.exit_code == 1
        # Conversation must still be there.
        list_result = runner.invoke(app, ["list"])
        assert conv_id in list_result.output

    def test_delete_unknown_id_exits_with_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))
        result = runner.invoke(app, ["delete", "ghost-id", "--yes"])
        assert result.exit_code == 1
