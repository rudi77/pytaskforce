#!/usr/bin/env python3
"""Fill fillable form fields in a PDF.

Usage:
    python fill_fillable_fields.py input.pdf field_values.json output.pdf
"""
import json
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

# Add scripts directory to path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))
from extract_form_field_info import get_field_info


def validation_error_for_field_value(field_info: dict[str, Any], field_value: str) -> str | None:
    """Validate that a field value is valid for the field type.

    Args:
        field_info: Field information dictionary.
        field_value: Value to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    field_type = field_info["type"]
    field_id = field_info["field_id"]

    if field_type == "checkbox":
        checked_val = field_info["checked_value"]
        unchecked_val = field_info["unchecked_value"]
        if field_value != checked_val and field_value != unchecked_val:
            return (
                f'ERROR: Invalid value "{field_value}" for checkbox field '
                f'"{field_id}". The checked value is "{checked_val}" and '
                f'the unchecked value is "{unchecked_val}"'
            )
    elif field_type == "radio_group":
        option_values = [opt["value"] for opt in field_info["radio_options"]]
        if field_value not in option_values:
            return (
                f'ERROR: Invalid value "{field_value}" for radio group field '
                f'"{field_id}". Valid values are: {option_values}'
            )
    elif field_type == "choice":
        choice_values = [opt["value"] for opt in field_info["choice_options"]]
        if field_value not in choice_values:
            return (
                f'ERROR: Invalid value "{field_value}" for choice field '
                f'"{field_id}". Valid values are: {choice_values}'
            )
    return None


def monkeypatch_pypdf_method() -> None:
    """Apply workaround for pypdf bug with selection lists.

    pypdf (at least version 5.7.0) has a bug when setting the value for a
    selection list field. The problem is that for selection lists,
    `get_inherited` returns a list of two-element lists like
    [["value1", "Text 1"], ["value2", "Text 2"], ...]
    This causes `join` to throw a TypeError because it expects strings.

    The workaround patches `get_inherited` to return a list of value strings.
    """
    from pypdf.constants import FieldDictionaryAttributes
    from pypdf.generic import DictionaryObject

    original_get_inherited = DictionaryObject.get_inherited

    def patched_get_inherited(self: Any, key: str, default: Any = None) -> Any:
        result = original_get_inherited(self, key, default)
        if key == FieldDictionaryAttributes.Opt:
            if isinstance(result, list) and all(
                isinstance(v, list) and len(v) == 2 for v in result
            ):
                result = [r[0] for r in result]
        return result

    DictionaryObject.get_inherited = patched_get_inherited


def fill_pdf_fields(input_pdf_path: str, fields_json_path: str, output_pdf_path: str) -> None:
    """Fill PDF form fields from a JSON specification.

    Args:
        input_pdf_path: Path to input PDF.
        fields_json_path: Path to JSON file with field values.
        output_pdf_path: Path to output PDF.
    """
    with open(fields_json_path) as f:
        fields = json.load(f)

    # Group by page number
    fields_by_page: dict[int, dict[str, str]] = {}
    for field in fields:
        if "value" in field:
            field_id = field["field_id"]
            page = field["page"]
            if page not in fields_by_page:
                fields_by_page[page] = {}
            fields_by_page[page][field_id] = field["value"]

    reader = PdfReader(input_pdf_path)

    # Validate fields
    has_error = False
    field_info = get_field_info(reader)
    fields_by_ids = {f["field_id"]: f for f in field_info}

    for field in fields:
        existing_field = fields_by_ids.get(field["field_id"])
        if not existing_field:
            has_error = True
            print(f"ERROR: `{field['field_id']}` is not a valid field ID")
        elif field["page"] != existing_field["page"]:
            has_error = True
            print(
                f"ERROR: Incorrect page number for `{field['field_id']}` "
                f"(got {field['page']}, expected {existing_field['page']})"
            )
        else:
            if "value" in field:
                err = validation_error_for_field_value(existing_field, field["value"])
                if err:
                    print(err)
                    has_error = True

    if has_error:
        sys.exit(1)

    # Fill fields
    writer = PdfWriter(clone_from=reader)
    for page, field_values in fields_by_page.items():
        writer.update_page_form_field_values(
            writer.pages[page - 1], field_values, auto_regenerate=False
        )

    # This seems to be necessary for many PDF viewers to format the form
    # values correctly. It may cause the viewer to show a "save changes"
    # dialog even if the user doesn't make any changes.
    writer.set_need_appearances_writer(True)

    with open(output_pdf_path, "wb") as output_file:
        writer.write(output_file)

    print(f"Successfully filled PDF and saved to {output_pdf_path}")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 4:
        print("Usage: fill_fillable_fields.py [input pdf] [field_values.json] [output pdf]")
        sys.exit(1)

    monkeypatch_pypdf_method()

    try:
        fill_pdf_fields(sys.argv[1], sys.argv[2], sys.argv[3])
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error filling PDF: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
