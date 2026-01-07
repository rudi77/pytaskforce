"""Helpers for long-running CLI harness workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Final

from taskforce.core.prompts.autonomous_prompts import (
    LONGRUN_CODING_PROMPT,
    LONGRUN_INITIALIZER_PROMPT,
)

DEFAULT_HARNESS_SUBDIR: Final[str] = "longrun"
DEFAULT_FEATURES_FILENAME: Final[str] = "feature_list.json"
DEFAULT_PROGRESS_FILENAME: Final[str] = "progress.md"
DEFAULT_INIT_SCRIPT_FILENAME: Final[str] = "init.sh"
DEFAULT_METADATA_FILENAME: Final[str] = "harness.json"


@dataclass(frozen=True)
class LongRunPaths:
    """Resolved paths for long-running harness artifacts."""

    features: Path
    progress: Path
    init_script: Path
    metadata: Path


@dataclass(frozen=True)
class LongRunMetadata:
    """Metadata for long-running harness sessions."""

    mission: str
    session_id: str | None
    created_at: str
    updated_at: str


def resolve_longrun_paths(
    *,
    harness_dir: Path,
    features_path: str | None,
    progress_path: str | None,
    init_script_path: str | None,
    metadata_path: str | None = None,
) -> LongRunPaths:
    """Resolve harness file paths with defaults under the harness directory."""
    harness_dir = harness_dir.resolve()
    default_dir = harness_dir / DEFAULT_HARNESS_SUBDIR
    features = Path(features_path) if features_path else default_dir / DEFAULT_FEATURES_FILENAME
    progress = Path(progress_path) if progress_path else default_dir / DEFAULT_PROGRESS_FILENAME
    init_script = (
        Path(init_script_path)
        if init_script_path
        else default_dir / DEFAULT_INIT_SCRIPT_FILENAME
    )
    metadata = (
        Path(metadata_path)
        if metadata_path
        else default_dir / DEFAULT_METADATA_FILENAME
    )
    return LongRunPaths(
        features=features.resolve(),
        progress=progress.resolve(),
        init_script=init_script.resolve(),
        metadata=metadata.resolve(),
    )


def ensure_harness_files(paths: LongRunPaths, now: datetime | None = None) -> None:
    """Create default harness files if they do not exist."""
    for path in (paths.features, paths.progress, paths.init_script, paths.metadata):
        path.parent.mkdir(parents=True, exist_ok=True)
    _write_feature_list_if_missing(paths.features)
    _write_progress_log_if_missing(paths.progress, now=now)
    _write_init_script_if_missing(paths.init_script)


def _write_feature_list_if_missing(path: Path) -> None:
    if path.exists():
        return
    payload: list[dict[str, object]] = []
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_progress_log_if_missing(path: Path, now: datetime | None = None) -> None:
    if path.exists():
        return
    timestamp = (now or datetime.now()).isoformat()
    content = (
        "# Long-Running Agent Progress\n\n"
        f"- Created: {timestamp}\n"
        "- Notes:\n"
        "  - Initial harness created by Taskforce CLI.\n"
    )
    path.write_text(content, encoding="utf-8")


def _write_init_script_if_missing(path: Path) -> None:
    if path.exists():
        return
    content = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "echo \"[taskforce] Start your dev server here\"\n"
        "# Example:\n"
        "# uvicorn taskforce.api.server:app --reload\n"
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def load_metadata(path: Path) -> LongRunMetadata | None:
    """Load harness metadata from disk if present."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    mission = payload.get("mission", "")
    created_at = payload.get("created_at", "")
    updated_at = payload.get("updated_at", "")
    session_id = payload.get("session_id")
    if not mission or not created_at or not updated_at:
        return None
    return LongRunMetadata(
        mission=mission,
        session_id=session_id,
        created_at=created_at,
        updated_at=updated_at,
    )


def save_metadata(
    *,
    path: Path,
    mission: str,
    session_id: str | None,
    now: datetime | None = None,
) -> LongRunMetadata:
    """Persist harness metadata to disk."""
    timestamp = (now or datetime.now()).isoformat()
    existing = load_metadata(path)
    created_at = existing.created_at if existing else timestamp
    metadata = LongRunMetadata(
        mission=mission,
        session_id=session_id,
        created_at=created_at,
        updated_at=timestamp,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mission": metadata.mission,
                "session_id": metadata.session_id,
                "created_at": metadata.created_at,
                "updated_at": metadata.updated_at,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata


def build_longrun_mission(
    mission: str,
    paths: LongRunPaths,
    init_mode: bool,
    mission_path: Path | None = None,
) -> str:
    """Compose mission text for the long-running harness flow."""
    mission_text = (
        mission_path.read_text(encoding="utf-8").strip()
        if mission_path
        else mission
    )
    prompt = LONGRUN_INITIALIZER_PROMPT if init_mode else LONGRUN_CODING_PROMPT
    return (
        f"{prompt}\n\n"
        f"User mission: {mission_text}\n\n"
        "Harness files:\n"
        f"- Feature list: {paths.features}\n"
        f"- Progress log: {paths.progress}\n"
        f"- Init script: {paths.init_script}\n"
    )


def validate_auto_runs(auto: bool, max_runs: int) -> None:
    """Validate auto-run parameters."""
    if auto and max_runs < 1:
        raise ValueError("--max-runs must be >= 1 when using --auto.")


def validate_mission_input(mission: str | None, mission_path: Path | None) -> None:
    """Validate mission input requirements."""
    if mission is None and mission_path is None:
        raise ValueError("MISSION is required unless --prompt-path is provided.")
