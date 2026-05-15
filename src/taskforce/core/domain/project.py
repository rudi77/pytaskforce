"""
Project Domain Model

A Project is a directory on disk that acts as the workspace for one or
more conversations. The directory holds everything the agent needs for
that project: a ``CLAUDE.md`` (instructions/rules), a ``skills/`` folder,
plus any free-form context, data, drafts, logs, templates.

Conversations carry an optional ``project_id``. When set, the agent's
``working_dir`` for that conversation is resolved to the project's
``path`` instead of the global ``TASKFORCE_WORK_DIR``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class Project:
    """A project workspace rooted at an absolute filesystem path."""

    name: str
    path: str
    project_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
