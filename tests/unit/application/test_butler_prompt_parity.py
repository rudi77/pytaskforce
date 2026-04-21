"""Parity test: the new butler.agent.md body must match BUTLER_SPECIALIST_PROMPT.

Before this migration, the butler's persona came from a hardcoded
``BUTLER_SPECIALIST_PROMPT`` string in
``src/taskforce/core/prompts/autonomous_prompts.py``. The migration moved that
text into ``agents/butler/configs/butler.agent.md`` as the markdown body. This
test asserts the two are byte-equivalent so the resulting system prompt does
not regress.

The original Python constant is reconstructed from the pre-migration blob
checked in at ``tests/fixtures/butler_specialist_prompt_baseline.txt`` so the
parity check survives future edits to ``autonomous_prompts.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application.agent_file_loader import (
    agent_file_to_config,
    load_agent_md,
)
from taskforce.core.utils.paths import get_base_path

_BUTLER_AGENT_MD = get_base_path() / "agents" / "butler" / "configs" / "butler.agent.md"
_BASELINE_PATH = (
    Path(__file__).parent.parent.parent / "fixtures" / "butler_specialist_prompt_baseline.txt"
)


@pytest.mark.skipif(
    not _BUTLER_AGENT_MD.is_file(),
    reason="butler.agent.md not present (butler package not installed in this layout)",
)
def test_butler_agent_md_body_matches_legacy_prompt() -> None:
    """``butler.agent.md`` body, as loaded, equals the legacy prompt byte-for-byte."""
    if not _BASELINE_PATH.is_file():
        pytest.skip(
            f"Baseline fixture missing: {_BASELINE_PATH}. "
            "Run tests/fixtures/regen_butler_baseline.py to regenerate."
        )
    expected = _BASELINE_PATH.read_text(encoding="utf-8")

    agent_file = load_agent_md(_BUTLER_AGENT_MD)
    cfg = agent_file_to_config(agent_file)
    assert cfg["system_prompt"] == expected
