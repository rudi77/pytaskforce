"""Unit tests for tool output filters."""

import json

from taskforce.infrastructure.tools.filters import simplify_wiki_list_output


class TestSimplifyWikiListOutput:
    """Tests for simplify_wiki_list_output filter."""

    def _make_result(self, output, success=True):
        """Helper to build a tool result dict."""
        return {"success": success, "output": output}

    # ------------------------------------------------------------------ #
    # Happy path
    # ------------------------------------------------------------------ #

    def test_filters_list_to_name_and_id(self):
        """Should keep only name and id from each wiki entry."""
        wikis = [
            {"name": "Wiki A", "id": "1", "remoteUrl": "http://...", "extra": "data"},
            {"name": "Wiki B", "id": "2", "remoteUrl": "http://...", "other": 42},
        ]
        result = self._make_result(json.dumps(wikis))
        filtered = simplify_wiki_list_output(result)

        parsed = json.loads(filtered["output"])
        assert len(parsed) == 2
        assert parsed[0] == {"name": "Wiki A", "id": "1"}
        assert parsed[1] == {"name": "Wiki B", "id": "2"}
        assert filtered["success"] is True

    def test_empty_list(self):
        result = self._make_result(json.dumps([]))
        filtered = simplify_wiki_list_output(result)
        assert json.loads(filtered["output"]) == []

    def test_handles_already_parsed_list(self):
        """When output is already a list (not a JSON string)."""
        wikis = [{"name": "Wiki C", "id": "3", "extra": "stuff"}]
        result = self._make_result(wikis)  # list, not string
        filtered = simplify_wiki_list_output(result)

        parsed = json.loads(filtered["output"])
        assert parsed == [{"name": "Wiki C", "id": "3"}]

    def test_missing_name_or_id_produces_none(self):
        """Entries missing name or id should get None for those fields."""
        wikis = [{"id": "1"}, {"name": "Only Name"}]
        result = self._make_result(json.dumps(wikis))
        filtered = simplify_wiki_list_output(result)

        parsed = json.loads(filtered["output"])
        assert parsed[0] == {"name": None, "id": "1"}
        assert parsed[1] == {"name": "Only Name", "id": None}

    # ------------------------------------------------------------------ #
    # Pass-through cases
    # ------------------------------------------------------------------ #

    def test_unsuccessful_result_passes_through(self):
        result = {"success": False, "output": "some error text"}
        filtered = simplify_wiki_list_output(result)
        assert filtered == result

    def test_empty_output_passes_through(self):
        result = self._make_result("")
        filtered = simplify_wiki_list_output(result)
        assert filtered["output"] == ""

    def test_no_output_key_passes_through(self):
        result = {"success": True}
        filtered = simplify_wiki_list_output(result)
        assert "output" not in filtered or filtered.get("output") is None

    def test_non_json_string_passes_through(self):
        """Non-JSON output should be returned unchanged."""
        result = self._make_result("this is not json")
        filtered = simplify_wiki_list_output(result)
        assert filtered["output"] == "this is not json"

    def test_json_dict_not_list_passes_through(self):
        """A JSON object (not a list) should be left alone."""
        result = self._make_result(json.dumps({"key": "value"}))
        filtered = simplify_wiki_list_output(result)
        # Output unchanged because data is a dict, not a list
        assert filtered["output"] == json.dumps({"key": "value"})

    # ------------------------------------------------------------------ #
    # Edge cases
    # ------------------------------------------------------------------ #

    def test_non_dict_items_in_list_skipped(self):
        """Non-dict items in the list should be filtered out."""
        data = [{"name": "A", "id": "1"}, "not a dict", 42]
        result = self._make_result(json.dumps(data))
        filtered = simplify_wiki_list_output(result)

        parsed = json.loads(filtered["output"])
        assert len(parsed) == 1
        assert parsed[0] == {"name": "A", "id": "1"}

    def test_result_mutated_in_place(self):
        """The function mutates and returns the same dict object."""
        result = self._make_result(json.dumps([{"name": "X", "id": "9"}]))
        returned = simplify_wiki_list_output(result)
        assert returned is result
