from taskforce.application.slash_command_registry import SlashCommandRegistry


def test_builtin_commands_include_plugins_and_skills() -> None:
    registry = SlashCommandRegistry()

    assert registry.is_builtin("plugins") is True
    assert registry.is_builtin("skills") is True

    builtin_names = {command["name"] for command in registry.list_commands()}
    assert "plugins" in builtin_names
    assert "skills" in builtin_names
