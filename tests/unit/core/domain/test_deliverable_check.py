"""Unit tests for the pre-finalize deliverable check (#405)."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.core.domain.planning.deliverable_check import (
    build_checklist_section,
    build_nudge,
    extract_candidate_dirs,
    extract_checklist_bullets,
    extract_deliverables,
    find_missing,
)


class TestExtractDeliverables:
    def test_market_research_prompt(self) -> None:
        """Real PinchBench prompt: ``save your report to a file named exactly `market_research.md```."""
        prompt = (
            "Create a competitive landscape analysis for the enterprise observability "
            "and APM market segment. **IMPORTANT: You MUST save your report to a file "
            "named exactly `market_research.md` in the current working directory.**"
        )
        assert extract_deliverables(prompt) == ["market_research.md"]

    def test_syslog_boot_prompt(self) -> None:
        """Real PinchBench prompt: ``Write your findings to `boot_report.md```."""
        prompt = (
            "Analyze the Linux syslog file at `linux_syslog.log` and produce a boot "
            "sequence report. ... Write your findings to `boot_report.md` as a "
            "structured markdown document."
        )
        # The input file (linux_syslog.log) is mentioned with the verb
        # "produce" within the proximity window — accept either one or two
        # detections, but boot_report.md MUST be present.
        result = extract_deliverables(prompt)
        assert "boot_report.md" in result

    def test_iris_summary_prompt_skips_input_file(self) -> None:
        """Input file `iris_flowers.csv` is far from any output verb — must not match."""
        prompt = (
            "I have a CSV file `iris_flowers.csv` in my workspace containing the "
            "classic Iris flowers dataset. It has 150 rows and 5 columns: "
            "`SepalLength`, `SepalWidth`, `PetalLength`, `PetalWidth`, and `Name` "
            "(the species). Please compute a statistical summary and write it to "
            "`iris_summary.md`. Your report should include the following sections..."
        )
        result = extract_deliverables(prompt)
        assert "iris_summary.md" in result
        assert "iris_flowers.csv" not in result

    def test_no_filenames(self) -> None:
        assert extract_deliverables("Tell me a joke") == []

    def test_empty_or_none(self) -> None:
        assert extract_deliverables("") == []
        assert extract_deliverables(None) == []

    def test_filename_without_verb_is_ignored(self) -> None:
        """A backtick-quoted filename without nearby output verb stays out."""
        prompt = "The configuration is in `settings.json` and that's all."
        assert extract_deliverables(prompt) == []

    def test_dedupes_repeated_filenames(self) -> None:
        prompt = (
            "Write to `report.md`. Then save the report to `report.md` again."
        )
        assert extract_deliverables(prompt) == ["report.md"]

    def test_multiple_distinct_deliverables(self) -> None:
        prompt = "Save findings to `out.md` and write raw data to `data.json`."
        result = extract_deliverables(prompt)
        assert "out.md" in result and "data.json" in result


class TestExtractCandidateDirs:
    def test_windows_path(self) -> None:
        prompt = (
            "Your task workspace is `C:\\Users\\rudi\\AppData\\Local\\Temp\\pinchbench_ws_abc`. "
            "Write your report to `out.md`."
        )
        dirs = extract_candidate_dirs(prompt)
        assert any("pinchbench_ws_abc" in str(d) for d in dirs)

    def test_posix_path(self) -> None:
        prompt = "The workspace is `/tmp/pinchbench_ws_xyz`. Write to `out.md`."
        dirs = extract_candidate_dirs(prompt)
        assert Path("/tmp/pinchbench_ws_xyz") in dirs

    def test_no_dirs(self) -> None:
        assert extract_candidate_dirs("just a sentence") == []


class TestFindMissing:
    def test_all_missing(self, tmp_path: Path) -> None:
        missing = find_missing(["report.md", "data.json"], [tmp_path])
        assert missing == ["report.md", "data.json"]

    def test_some_present(self, tmp_path: Path) -> None:
        (tmp_path / "report.md").write_text("hi")
        missing = find_missing(["report.md", "data.json"], [tmp_path])
        assert missing == ["data.json"]

    def test_basename_fallback(self, tmp_path: Path) -> None:
        """Agent flattened a subpath: prompt says `out/report.md`, file is at root."""
        (tmp_path / "report.md").write_text("hi")
        missing = find_missing(["out/report.md"], [tmp_path])
        assert missing == []

    def test_multiple_roots_first_hit_wins(self, tmp_path: Path) -> None:
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        (root_b / "report.md").write_text("hi")
        missing = find_missing(["report.md"], [root_a, root_b])
        assert missing == []

    def test_empty_search_roots_treats_all_as_missing(self) -> None:
        # Conservative: no roots → can't verify → treat as missing (will nudge).
        assert find_missing(["x.md"], []) == ["x.md"]

    def test_empty_deliverables(self, tmp_path: Path) -> None:
        assert find_missing([], [tmp_path]) == []


class TestBuildNudge:
    def test_mentions_each_missing_file(self) -> None:
        nudge = build_nudge(["a.md", "b.json"])
        assert "`a.md`" in nudge and "`b.json`" in nudge

    def test_instructs_to_use_file_write(self) -> None:
        nudge = build_nudge(["x.md"])
        assert "file_write" in nudge or "edit" in nudge

    def test_instructs_not_to_finalize(self) -> None:
        nudge = build_nudge(["x.md"])
        assert "complete" in nudge.lower()


@pytest.mark.parametrize(
    "verb",
    ["save", "Save", "write", "create", "produce", "store", "output", "generate"],
)
def test_each_output_verb_triggers_detection(verb: str) -> None:
    prompt = f"{verb} the result to `result.md`."
    assert "result.md" in extract_deliverables(prompt)


class TestExtractChecklistBullets:
    def test_numbered_bolded_bullets(self) -> None:
        """Real PinchBench syslog_boot prompt structure."""
        prompt = (
            "Write your findings as a markdown document.\n\n"
            "1. **System identification**: kernel version, CPU model, RAM\n"
            "2. **Storage**: hard drive model, capacity, filesystem\n"
            "3. **Boot timeline**: timestamp, duration\n"
            "4. **Services**: count and list\n"
            "5. **Errors and warnings**: identify failures\n"
            "6. **Network**: NIC, IP addresses\n"
        )
        bullets = extract_checklist_bullets(prompt)
        assert bullets == [
            "System identification",
            "Storage",
            "Boot timeline",
            "Services",
            "Errors and warnings",
            "Network",
        ]

    def test_dashed_bolded_bullets(self) -> None:
        """Real PinchBench csv_iris_summary prompt structure."""
        prompt = (
            "Your report should include:\n\n"
            "- **Dataset overview**: total rows, columns\n"
            "- **Overall statistics**: mean, median\n"
            "- **Per-species statistics**: grouped by species\n"
            "- **Correlation insight**: strongest pair\n"
            "- **Key findings**: notable patterns\n"
        )
        bullets = extract_checklist_bullets(prompt)
        assert "Dataset overview" in bullets
        assert "Key findings" in bullets
        assert len(bullets) == 5

    def test_single_bullet_does_not_trigger(self) -> None:
        """One bolded bullet is not a checklist."""
        prompt = "Just one thing:\n- **Single Item**: do it."
        assert extract_checklist_bullets(prompt) == []

    def test_unbolded_bullets_are_ignored(self) -> None:
        prompt = "1. do x\n2. do y\n3. do z"
        assert extract_checklist_bullets(prompt) == []

    def test_strips_trailing_colon(self) -> None:
        prompt = (
            "- **Item One**: description\n"
            "- **Item Two**: description\n"
        )
        assert extract_checklist_bullets(prompt) == ["Item One", "Item Two"]

    def test_dedupes(self) -> None:
        prompt = "- **A**\n- **B**\n- **A**\n"
        assert extract_checklist_bullets(prompt) == ["A", "B"]

    def test_empty_or_none(self) -> None:
        assert extract_checklist_bullets("") == []
        assert extract_checklist_bullets(None) == []

    def test_caps_at_20_items(self) -> None:
        prompt = "\n".join(f"- **Item {i}**: x" for i in range(50))
        assert len(extract_checklist_bullets(prompt)) == 20


class TestBuildChecklistSection:
    def test_renders_checkboxes(self) -> None:
        section = build_checklist_section(["A", "B", "C"])
        assert "## Required Deliverables" in section
        assert "- [ ] A" in section
        assert "- [ ] B" in section
        assert "- [ ] C" in section

    def test_empty_bullets_yields_empty_string(self) -> None:
        assert build_checklist_section([]) == ""

    def test_instructs_to_treat_as_checklist(self) -> None:
        section = build_checklist_section(["X", "Y"])
        assert "checklist" in section.lower()
