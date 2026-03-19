"""Tests for YAML I/O utilities.

Verifies atomic write and safe load operations, including error handling
and edge cases for cross-platform YAML file operations.
"""

import pytest
import yaml

from taskforce.infrastructure.persistence.yaml_io import atomic_write_yaml, safe_load_yaml


class TestAtomicWriteYaml:
    """Tests for atomic_write_yaml."""

    def test_writes_yaml_to_new_file(self, tmp_path):
        path = tmp_path / "output.yaml"
        data = {"key": "value", "number": 42}

        atomic_write_yaml(path, data)

        assert path.exists()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded == data

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / "output.yaml"
        path.write_text("old: data\n", encoding="utf-8")

        new_data = {"new": "content"}
        atomic_write_yaml(path, new_data)

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded == new_data

    def test_preserves_unicode(self, tmp_path):
        path = tmp_path / "unicode.yaml"
        data = {"greeting": "Hello, world!", "emoji": "Cafe\u0301"}

        atomic_write_yaml(path, data)

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded["greeting"] == "Hello, world!"
        assert loaded["emoji"] == "Cafe\u0301"

    def test_preserves_key_order(self, tmp_path):
        path = tmp_path / "ordered.yaml"
        data = {"zebra": 1, "alpha": 2, "middle": 3}

        atomic_write_yaml(path, data)

        text = path.read_text(encoding="utf-8")
        lines = [line.split(":")[0] for line in text.strip().splitlines()]
        assert lines == ["zebra", "alpha", "middle"]

    def test_writes_nested_structures(self, tmp_path):
        path = tmp_path / "nested.yaml"
        data = {
            "agent": {"name": "test", "tools": ["python", "file_read"]},
            "config": {"nested": {"deep": True}},
        }

        atomic_write_yaml(path, data)

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded == data

    def test_writes_empty_dict(self, tmp_path):
        path = tmp_path / "empty.yaml"

        atomic_write_yaml(path, {})

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded == {}

    def test_no_temp_files_left_on_success(self, tmp_path):
        path = tmp_path / "clean.yaml"
        atomic_write_yaml(path, {"key": "value"})

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "clean.yaml"

    def test_no_temp_files_left_on_error(self, tmp_path):
        path = tmp_path / "nonexistent_dir" / "output.yaml"

        with pytest.raises(OSError):
            atomic_write_yaml(path, {"key": "value"})

        # Parent dir doesn't exist, so nothing should be created
        assert not (tmp_path / "nonexistent_dir").exists()

    def test_cleans_up_temp_on_rename_failure(self, tmp_path, monkeypatch):
        """If rename fails after writing temp file, temp file is cleaned up."""
        path = tmp_path / "output.yaml"
        original_rename = type(path).rename

        def fail_rename(self_path, target):
            raise OSError("Simulated rename failure")

        monkeypatch.setattr("pathlib.Path.rename", fail_rename)

        with pytest.raises(OSError, match="Simulated rename failure"):
            atomic_write_yaml(path, {"key": "value"})

        # Temp files should be cleaned up
        tmp_files = [f for f in tmp_path.iterdir() if f.suffix == ".tmp"]
        assert len(tmp_files) == 0


class TestSafeLoadYaml:
    """Tests for safe_load_yaml."""

    def test_loads_valid_yaml(self, tmp_path):
        path = tmp_path / "valid.yaml"
        path.write_text("key: value\nnumber: 42\n", encoding="utf-8")

        result = safe_load_yaml(path)

        assert result == {"key": "value", "number": 42}

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        path = tmp_path / "missing.yaml"

        result = safe_load_yaml(path)

        assert result is None

    def test_returns_none_for_invalid_yaml(self, tmp_path):
        path = tmp_path / "invalid.yaml"
        path.write_text("{{invalid: yaml: content}}", encoding="utf-8")

        result = safe_load_yaml(path)

        assert result is None

    def test_loads_nested_yaml(self, tmp_path):
        path = tmp_path / "nested.yaml"
        data = {"agent": {"tools": ["python"], "config": {"key": "val"}}}
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

        result = safe_load_yaml(path)

        assert result == data

    def test_loads_empty_yaml_file(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")

        result = safe_load_yaml(path)

        assert result is None

    def test_loads_list_yaml(self, tmp_path):
        path = tmp_path / "list.yaml"
        path.write_text("- one\n- two\n- three\n", encoding="utf-8")

        result = safe_load_yaml(path)

        assert result == ["one", "two", "three"]

    def test_roundtrip_with_atomic_write(self, tmp_path):
        """Data written by atomic_write_yaml can be read back by safe_load_yaml."""
        path = tmp_path / "roundtrip.yaml"
        data = {"agent_id": "test-agent", "tools": ["python", "shell"], "enabled": True}

        atomic_write_yaml(path, data)
        result = safe_load_yaml(path)

        assert result == data
