from __future__ import annotations

from datetime import datetime
from pathlib import Path

from taskforce.api.cli.long_running_harness import (
    build_longrun_mission,
    ensure_harness_files,
    load_metadata,
    resolve_longrun_paths,
    save_metadata,
    validate_auto_runs,
    validate_mission_input,
)


def test_resolve_longrun_paths_defaults(tmp_path: Path) -> None:
    paths = resolve_longrun_paths(
        harness_dir=tmp_path,
        features_path=None,
        progress_path=None,
        init_script_path=None,
    )

    assert paths.features == (tmp_path / "longrun" / "feature_list.json").resolve()
    assert paths.progress == (tmp_path / "longrun" / "progress.md").resolve()
    assert paths.init_script == (tmp_path / "longrun" / "init.sh").resolve()


def test_ensure_harness_files_creates_defaults(tmp_path: Path) -> None:
    paths = resolve_longrun_paths(
        harness_dir=tmp_path,
        features_path=None,
        progress_path=None,
        init_script_path=None,
    )
    fixed_time = datetime(2024, 1, 2, 3, 4, 5)

    ensure_harness_files(paths, now=fixed_time)

    assert paths.features.exists()
    assert paths.progress.exists()
    assert paths.init_script.exists()
    progress_text = paths.progress.read_text(encoding="utf-8")
    assert "2024-01-02T03:04:05" in progress_text
    assert paths.init_script.stat().st_mode & 0o111


def test_save_and_load_metadata(tmp_path: Path) -> None:
    paths = resolve_longrun_paths(
        harness_dir=tmp_path,
        features_path=None,
        progress_path=None,
        init_script_path=None,
    )
    fixed_time = datetime(2024, 2, 3, 4, 5, 6)

    metadata = save_metadata(
        path=paths.metadata,
        mission="Build a long-running flow",
        session_id="session-123",
        now=fixed_time,
    )

    loaded = load_metadata(paths.metadata)

    assert metadata == loaded
    assert loaded is not None
    assert loaded.mission == "Build a long-running flow"
    assert loaded.session_id == "session-123"


def test_auto_runs_validation() -> None:
    try:
        validate_auto_runs(auto=True, max_runs=0)
    except ValueError as exc:
        assert "--max-runs must be >= 1" in str(exc)


def test_longrun_requires_mission_without_prompt_path() -> None:
    try:
        validate_mission_input(None, None)
    except ValueError as exc:
        assert "MISSION is required" in str(exc)


def test_build_longrun_mission_includes_paths(tmp_path: Path) -> None:
    paths = resolve_longrun_paths(
        harness_dir=tmp_path,
        features_path=None,
        progress_path=None,
        init_script_path=None,
    )

    mission_text = build_longrun_mission("Ship feature X", paths, init_mode=True)

    assert "Ship feature X" in mission_text
    assert str(paths.features) in mission_text
    assert str(paths.progress) in mission_text
    assert str(paths.init_script) in mission_text


def test_build_longrun_mission_uses_prompt_file(tmp_path: Path) -> None:
    paths = resolve_longrun_paths(
        harness_dir=tmp_path,
        features_path=None,
        progress_path=None,
        init_script_path=None,
    )
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Custom Prompt", encoding="utf-8")

    mission_text = build_longrun_mission(
        "Ship feature Y",
        paths,
        init_mode=False,
        mission_path=prompt_file,
    )

    assert "User mission: Custom Prompt" in mission_text
