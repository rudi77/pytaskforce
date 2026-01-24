#!/usr/bin/env python3
"""Extract fillable form field information from a PDF.

Usage:
    python extract_form_field_info.py input.pdf output.json
"""
import json
import sys
from typing import Any

from pypdf import PdfReader


def get_full_annotation_field_id(annotation: dict) -> str | None:
    """Get the full hierarchical field ID from an annotation.

    Args:
        annotation: PDF annotation dictionary.

    Returns:
        Full field ID as dot-separated string, or None if not found.
    """
    components = []
    while annotation:
        field_name = annotation.get("/T")
        if field_name:
            components.append(field_name)
        annotation = annotation.get("/Parent")
    return ".".join(reversed(components)) if components else None


def make_field_dict(field: dict, field_id: str) -> dict[str, Any]:
    """Create a field dictionary from PDF field data.

    Args:
        field: PDF field dictionary.
        field_id: Field identifier.

    Returns:
        Normalized field dictionary with type and options.
    """
    field_dict: dict[str, Any] = {"field_id": field_id}
    ft = field.get("/FT")

    if ft == "/Tx":
        field_dict["type"] = "text"
    elif ft == "/Btn":
        field_dict["type"] = "checkbox"
        states = field.get("/_States_", [])
        if len(states) == 2:
            if "/Off" in states:
                field_dict["checked_value"] = (
                    states[0] if states[0] != "/Off" else states[1]
                )
                field_dict["unchecked_value"] = "/Off"
            else:
                print(f"Unexpected state values for checkbox `{field_id}`...")
                field_dict["checked_value"] = states[0]
                field_dict["unchecked_value"] = states[1]
    elif ft == "/Ch":
        field_dict["type"] = "choice"
        states = field.get("/_States_", [])
        field_dict["choice_options"] = [
            {
                "value": state[0],
                "text": state[1],
            }
            for state in states
        ]
    else:
        field_dict["type"] = f"unknown ({ft})"

    return field_dict


def get_field_info(reader: PdfReader) -> list[dict[str, Any]]:
    """Extract field information from a PDF reader.

    Args:
        reader: PdfReader instance.

    Returns:
        List of field dictionaries with location information.
    """
    fields = reader.get_fields()
    if not fields:
        return []

    field_info_by_id: dict[str, dict] = {}
    possible_radio_names: set[str] = set()

    for field_id, field in fields.items():
        if field.get("/Kids"):
            if field.get("/FT") == "/Btn":
                possible_radio_names.add(field_id)
            continue
        field_info_by_id[field_id] = make_field_dict(field, field_id)

    radio_fields_by_id: dict[str, dict] = {}

    for page_index, page in enumerate(reader.pages):
        annotations = page.get("/Annots", [])
        for ann in annotations:
            field_id = get_full_annotation_field_id(ann)
            if field_id in field_info_by_id:
                field_info_by_id[field_id]["page"] = page_index + 1
                field_info_by_id[field_id]["rect"] = ann.get("/Rect")
            elif field_id in possible_radio_names:
                try:
                    on_values = [v for v in ann["/AP"]["/N"] if v != "/Off"]
                except KeyError:
                    continue
                if len(on_values) == 1:
                    rect = ann.get("/Rect")
                    if field_id not in radio_fields_by_id:
                        radio_fields_by_id[field_id] = {
                            "field_id": field_id,
                            "type": "radio_group",
                            "page": page_index + 1,
                            "radio_options": [],
                        }
                    radio_fields_by_id[field_id]["radio_options"].append(
                        {
                            "value": on_values[0],
                            "rect": rect,
                        }
                    )

    fields_with_location = []
    for field_info in field_info_by_id.values():
        if "page" in field_info:
            fields_with_location.append(field_info)
        else:
            print(
                f"Unable to determine location for field id: "
                f"{field_info.get('field_id')}, ignoring"
            )

    def sort_key(f: dict) -> list:
        if "radio_options" in f:
            rect = f["radio_options"][0]["rect"] or [0, 0, 0, 0]
        else:
            rect = f.get("rect") or [0, 0, 0, 0]
        adjusted_position = [-rect[1], rect[0]]
        return [f.get("page"), adjusted_position]

    sorted_fields = fields_with_location + list(radio_fields_by_id.values())
    sorted_fields.sort(key=sort_key)

    return sorted_fields


def write_field_info(pdf_path: str, json_output_path: str) -> None:
    """Extract and write field info to JSON file.

    Args:
        pdf_path: Path to input PDF.
        json_output_path: Path to output JSON file.
    """
    reader = PdfReader(pdf_path)
    field_info = get_field_info(reader)

    with open(json_output_path, "w") as f:
        json.dump(field_info, f, indent=2)

    print(f"Wrote {len(field_info)} fields to {json_output_path}")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: extract_form_field_info.py [input pdf] [output json]")
        sys.exit(1)

    try:
        write_field_info(sys.argv[1], sys.argv[2])
    except FileNotFoundError:
        print(f"Error: File not found: {sys.argv[1]}")
        sys.exit(1)
    except Exception as e:
        print(f"Error extracting field info: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
