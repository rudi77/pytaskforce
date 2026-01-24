#!/usr/bin/env python3
"""Validate bounding boxes in a fields.json file.

This script checks that bounding boxes do not overlap and that entry box
heights are sufficient for the specified font sizes.

Usage:
    python check_bounding_boxes.py fields.json
"""
import json
import sys
from dataclasses import dataclass
from typing import IO, Any


@dataclass
class RectAndField:
    """A bounding box rectangle with its associated field."""

    rect: list[float]
    rect_type: str
    field: dict[str, Any]


def rects_intersect(r1: list[float], r2: list[float]) -> bool:
    """Check if two rectangles intersect.

    Args:
        r1: First rectangle [x_min, y_min, x_max, y_max].
        r2: Second rectangle [x_min, y_min, x_max, y_max].

    Returns:
        True if rectangles intersect, False otherwise.
    """
    disjoint_horizontal = r1[0] >= r2[2] or r1[2] <= r2[0]
    disjoint_vertical = r1[1] >= r2[3] or r1[3] <= r2[1]
    return not (disjoint_horizontal or disjoint_vertical)


def get_bounding_box_messages(fields_json_stream: IO[str]) -> list[str]:
    """Validate bounding boxes and return validation messages.

    Args:
        fields_json_stream: File stream containing fields JSON.

    Returns:
        List of validation messages (errors or success).
    """
    messages: list[str] = []
    fields = json.load(fields_json_stream)
    messages.append(f"Read {len(fields['form_fields'])} fields")

    rects_and_fields: list[RectAndField] = []
    for f in fields["form_fields"]:
        rects_and_fields.append(RectAndField(f["label_bounding_box"], "label", f))
        rects_and_fields.append(RectAndField(f["entry_bounding_box"], "entry", f))

    has_error = False

    for i, ri in enumerate(rects_and_fields):
        # This is O(N^2); we can optimize if it becomes a problem
        for j in range(i + 1, len(rects_and_fields)):
            rj = rects_and_fields[j]
            if ri.field["page_number"] == rj.field["page_number"] and rects_intersect(
                ri.rect, rj.rect
            ):
                has_error = True
                if ri.field is rj.field:
                    messages.append(
                        f"FAILURE: intersection between label and entry bounding "
                        f"boxes for `{ri.field['description']}` ({ri.rect}, {rj.rect})"
                    )
                else:
                    messages.append(
                        f"FAILURE: intersection between {ri.rect_type} bounding box "
                        f"for `{ri.field['description']}` ({ri.rect}) and "
                        f"{rj.rect_type} bounding box for "
                        f"`{rj.field['description']}` ({rj.rect})"
                    )
                if len(messages) >= 20:
                    messages.append(
                        "Aborting further checks; fix bounding boxes and try again"
                    )
                    return messages

        # Check entry box height vs font size
        if ri.rect_type == "entry":
            if "entry_text" in ri.field:
                font_size = ri.field["entry_text"].get("font_size", 14)
                entry_height = ri.rect[3] - ri.rect[1]
                if entry_height < font_size:
                    has_error = True
                    messages.append(
                        f"FAILURE: entry bounding box height ({entry_height}) for "
                        f"`{ri.field['description']}` is too short for the text "
                        f"content (font size: {font_size}). Increase the box height "
                        f"or decrease the font size."
                    )
                    if len(messages) >= 20:
                        messages.append(
                            "Aborting further checks; fix bounding boxes and try again"
                        )
                        return messages

    if not has_error:
        messages.append("SUCCESS: All bounding boxes are valid")

    return messages


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: check_bounding_boxes.py [fields.json]")
        sys.exit(1)

    try:
        with open(sys.argv[1]) as f:
            messages = get_bounding_box_messages(f)
        for msg in messages:
            print(msg)
    except FileNotFoundError:
        print(f"Error: File not found: {sys.argv[1]}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Missing required field in JSON: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
