#!/usr/bin/env python3
"""
Booking persistence, rule learning, and GoBD-compliant audit logging.

Standalone script adapted from:
- accounting_agent.tools.rule_learning_tool
- accounting_agent.tools.audit_log_tool
- accounting_agent.infrastructure.persistence.booking_history

Usage:
    # Save booking + audit log
    python booking.py save --input booking.json [--workspace .bookkeeping]

    # Learn rule from confirmed/corrected booking
    python booking.py learn --input rule_data.json [--workspace .bookkeeping]

    # Write audit log entry
    python booking.py audit --input audit_data.json [--workspace .bookkeeping]

    # List recent bookings
    python booking.py list [--workspace .bookkeeping] [--limit 20]

Output: JSON result to stdout.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import yaml


# --- Constants ---

AUTO_RULE_PRIORITY = 75
HITL_RULE_PRIORITY = 90
MAX_ITEM_PATTERNS = 10
MAX_PATTERN_LENGTH = 100
MIN_PATTERN_LENGTH = 2


# --- Workspace Management ---

def ensure_workspace(workspace: str) -> dict[str, Path]:
    """Create workspace directories and return paths."""
    base = Path(workspace)
    paths = {
        "base": base,
        "rules": base / "rules",
        "bookings": base / "bookings",
        "audit": base / "audit",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


# --- Booking Persistence ---

def save_booking(
    booking_data: dict[str, Any],
    workspace: str = ".bookkeeping",
) -> dict[str, Any]:
    """
    Save booking to JSONL (append-only, GoBD-compliant).

    Expected booking_data fields:
    - supplier_name, invoice_number, invoice_date
    - booking_proposals: list of {debit_account, credit_account, net_amount, ...}
    - decision: "auto_book" | "user_confirmed" | "user_corrected"
    - confidence: float
    """
    paths = ensure_workspace(workspace)
    bookings_file = paths["bookings"] / "bookings.jsonl"

    booking_id = f"BK-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "booking_id": booking_id,
        "timestamp": timestamp,
        "supplier_name": booking_data.get("supplier_name", ""),
        "invoice_number": booking_data.get("invoice_number", ""),
        "invoice_date": booking_data.get("invoice_date", ""),
        "total_gross": booking_data.get("total_gross", 0),
        "total_net": booking_data.get("total_net", 0),
        "total_vat": booking_data.get("total_vat", 0),
        "booking_proposals": booking_data.get("booking_proposals", []),
        "decision": booking_data.get("decision", ""),
        "confidence": booking_data.get("confidence", 0.0),
        "user_corrections": booking_data.get("user_corrections"),
    }

    # Append to JSONL
    with open(bookings_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "success": True,
        "booking_id": booking_id,
        "timestamp": timestamp,
        "bookings_file": str(bookings_file),
    }


def list_bookings(
    workspace: str = ".bookkeeping",
    limit: int = 20,
    supplier_filter: str | None = None,
) -> dict[str, Any]:
    """List recent bookings from JSONL."""
    bookings_file = Path(workspace) / "bookings" / "bookings.jsonl"
    if not bookings_file.exists():
        return {"success": True, "bookings": [], "count": 0}

    bookings = []
    with open(bookings_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                booking = json.loads(line)
                if supplier_filter:
                    supplier = (booking.get("supplier_name") or "").lower()
                    if supplier_filter.lower() not in supplier:
                        continue
                bookings.append(booking)
            except json.JSONDecodeError:
                continue

    # Most recent first, limited
    bookings = bookings[-limit:][::-1]

    return {
        "success": True,
        "bookings": bookings,
        "count": len(bookings),
    }


# --- Rule Learning ---

def learn_rule(
    rule_data: dict[str, Any],
    workspace: str = ".bookkeeping",
) -> dict[str, Any]:
    """
    Create or update a learned accounting rule.

    Expected rule_data fields:
    - action: "create_from_booking" | "create_from_hitl_confirmation" | "create_from_hitl"
    - supplier_name: str
    - position_bookings: list of {item_description, debit_account, debit_account_name}
      OR booking_proposal: {debit_account, debit_account_name} (legacy single-account)
      OR correction: {debit_account, debit_account_name} (for HITL corrections)
    - confidence: float (only needed for create_from_booking)
    """
    paths = ensure_workspace(workspace)
    learned_file = paths["rules"] / "learned_rules.yaml"

    action = rule_data.get("action", "create_from_booking")
    supplier_name = rule_data.get("supplier_name", "")
    if not supplier_name:
        return {"success": False, "error": "supplier_name ist erforderlich"}

    # Check confidence for auto-rules
    if action == "create_from_booking":
        confidence = rule_data.get("confidence", 0.0)
        if confidence < 0.95:
            return {
                "success": False,
                "error": f"Confidence {confidence:.1%} unter Schwelle 95%",
                "rule_created": False,
            }

    # Load existing learned rules
    existing_rules = []
    if learned_file.exists():
        try:
            with open(learned_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            existing_rules = data.get("rules", [])
        except (yaml.YAMLError, OSError):
            pass

    # Determine source and priority
    if action == "create_from_hitl":
        source = "hitl_correction"
        priority = HITL_RULE_PRIORITY
    else:
        source = "auto_high_confidence"
        priority = AUTO_RULE_PRIORITY

    timestamp = datetime.now(timezone.utc)
    rules_created = []
    rules_updated = []

    # Get items to create rules for
    position_bookings = rule_data.get("position_bookings", [])
    if not position_bookings:
        # Legacy single booking_proposal or correction
        bp = rule_data.get("booking_proposal") or rule_data.get("correction") or {}
        debit_account = bp.get("debit_account", "")
        if debit_account:
            # Get item descriptions from line_items if available
            line_items = rule_data.get("line_items", [])
            if line_items:
                for item in line_items:
                    desc = item.get("description", "")
                    if desc:
                        position_bookings.append({
                            "item_description": desc,
                            "debit_account": debit_account,
                            "debit_account_name": bp.get("debit_account_name", ""),
                        })
            else:
                # Vendor-only rule
                position_bookings.append({
                    "item_description": "",
                    "debit_account": debit_account,
                    "debit_account_name": bp.get("debit_account_name", ""),
                })

    if not position_bookings:
        return {"success": False, "error": "Keine Buchungspositionen angegeben"}

    vendor_pattern = supplier_name.strip()

    for i, pos in enumerate(position_bookings):
        item_desc = pos.get("item_description", "")
        debit_account = pos.get("debit_account", "")
        debit_account_name = pos.get("debit_account_name", "")

        if not debit_account:
            continue

        item_patterns = [item_desc[:MAX_PATTERN_LENGTH]] if item_desc else []
        rule_type = "vendor_item" if item_patterns else "vendor_only"

        # Check for existing rule (same vendor + same item pattern)
        existing_idx = None
        for idx, rule in enumerate(existing_rules):
            if rule.get("vendor_pattern", "").lower() == vendor_pattern.lower():
                existing_patterns = [p.lower() for p in rule.get("item_patterns", [])]
                new_patterns = [p.lower() for p in item_patterns]
                if existing_patterns == new_patterns or (not existing_patterns and not new_patterns):
                    existing_idx = idx
                    break

        if existing_idx is not None:
            # Update existing rule
            existing_rules[existing_idx]["target_account"] = debit_account
            existing_rules[existing_idx]["target_account_name"] = debit_account_name
            existing_rules[existing_idx]["source"] = source
            existing_rules[existing_idx]["priority"] = priority
            existing_rules[existing_idx]["updated_at"] = timestamp.isoformat()
            rules_updated.append({
                "rule_id": existing_rules[existing_idx]["rule_id"],
                "item": item_desc,
                "account": debit_account,
            })
        else:
            # Create new rule
            prefix = "HITL" if source == "hitl_correction" else "AUTO"
            rule_id = f"{prefix}-{timestamp.strftime('%Y%m%d%H%M%S')}-{i+1}"

            new_rule = {
                "rule_id": rule_id,
                "rule_type": rule_type,
                "vendor_pattern": vendor_pattern,
                "item_patterns": item_patterns,
                "target_account": debit_account,
                "target_account_name": debit_account_name,
                "priority": priority,
                "similarity_threshold": 0.8,
                "source": source,
                "created_at": timestamp.isoformat(),
                "is_active": True,
            }
            existing_rules.append(new_rule)
            rules_created.append({
                "rule_id": rule_id,
                "item": item_desc,
                "account": debit_account,
            })

    # Save updated rules
    output = {
        "version": "1.0",
        "updated_at": timestamp.isoformat(),
        "rules": existing_rules,
    }
    with open(learned_file, "w", encoding="utf-8") as f:
        yaml.dump(output, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return {
        "success": True,
        "rules_created": len(rules_created),
        "rules_updated": len(rules_updated),
        "created_rules": rules_created,
        "updated_rules": rules_updated,
        "vendor_pattern": vendor_pattern,
        "learned_rules_file": str(learned_file),
    }


# --- Audit Logging ---

SENSITIVE_KEYS = {"password", "api_key", "secret", "token", "credential"}


def sanitize(details: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive data from audit details."""
    result = {}
    for key, value in details.items():
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = sanitize(value)
        elif isinstance(value, list):
            result[key] = [sanitize(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    return result


def write_audit_log(
    audit_data: dict[str, Any],
    workspace: str = ".bookkeeping",
) -> dict[str, Any]:
    """
    Create GoBD-compliant audit log entry.

    Expected audit_data fields:
    - operation: str (e.g., "booking_created", "invoice_processed")
    - document_id: str (invoice number or reference)
    - details: dict (operation-specific details)
    - decision: str (outcome)
    - legal_basis: str (e.g., "§14 UStG")
    """
    paths = ensure_workspace(workspace)
    audit_file = paths["audit"] / "audit_trail.jsonl"

    log_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # Get previous hash for chain integrity
    previous_hash = "GENESIS"
    if audit_file.exists():
        try:
            with open(audit_file, "rb") as f:
                # Read last line
                f.seek(0, 2)
                size = f.tell()
                if size > 0:
                    # Find last newline
                    pos = size - 1
                    while pos > 0:
                        f.seek(pos)
                        if f.read(1) == b"\n" and pos < size - 1:
                            break
                        pos -= 1
                    last_line = f.read().decode("utf-8").strip()
                    if last_line:
                        last_entry = json.loads(last_line)
                        previous_hash = last_entry.get("integrity_hash", "GENESIS")
        except (OSError, json.JSONDecodeError):
            pass

    log_entry = {
        "log_id": log_id,
        "timestamp": timestamp,
        "operation": audit_data.get("operation", "unknown"),
        "document_id": audit_data.get("document_id", ""),
        "details": sanitize(audit_data.get("details", {})),
        "decision": audit_data.get("decision", ""),
        "legal_basis": audit_data.get("legal_basis", ""),
        "previous_hash": previous_hash,
        "metadata": {
            "version": "1.0",
            "gobd_compliant": True,
            "created_by": "smart-booking-skill",
        },
    }

    # Calculate integrity hash
    content_for_hash = json.dumps(log_entry, sort_keys=True, ensure_ascii=False)
    integrity_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()
    log_entry["integrity_hash"] = integrity_hash

    # Append to JSONL
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    return {
        "success": True,
        "log_id": log_id,
        "timestamp": timestamp,
        "integrity_hash": integrity_hash,
        "audit_file": str(audit_file),
    }


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="Booking, Rule Learning & Audit")
    parser.add_argument("command", choices=["save", "learn", "audit", "list"],
                        help="Command to execute")
    parser.add_argument("--input", "-i", help="Path to JSON input file (or use stdin)")
    parser.add_argument("--workspace", "-w", default=".bookkeeping", help="Workspace directory")
    parser.add_argument("--limit", type=int, default=20, help="Limit for list command")
    parser.add_argument("--supplier", help="Supplier filter for list command")
    args = parser.parse_args()

    # Read input for non-list commands
    input_data = {}
    if args.command != "list":
        if args.input:
            with open(args.input, encoding="utf-8") as f:
                input_data = json.load(f)
        elif not sys.stdin.isatty():
            input_data = json.load(sys.stdin)

    if args.command == "save":
        result = save_booking(input_data, args.workspace)
    elif args.command == "learn":
        result = learn_rule(input_data, args.workspace)
    elif args.command == "audit":
        result = write_audit_log(input_data, args.workspace)
    elif args.command == "list":
        result = list_bookings(args.workspace, args.limit, args.supplier)
    else:
        result = {"success": False, "error": f"Unknown command: {args.command}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
