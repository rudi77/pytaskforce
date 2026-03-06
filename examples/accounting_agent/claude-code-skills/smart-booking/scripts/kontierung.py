#!/usr/bin/env python3
"""
Kontierung (account assignment) with rule matching and confidence evaluation.

Standalone script adapted from:
- accounting_agent.tools.semantic_rule_engine_tool (rule matching)
- accounting_agent.domain.confidence (confidence calculation)

Uses fuzzy string matching (difflib) instead of embeddings for standalone use.

Usage:
    python kontierung.py --input invoice.json --rules kontierung_rules.yaml [--workspace .bookkeeping]
    echo '{"supplier_name": "...", "line_items": [...]}' | python kontierung.py --rules rules.yaml

Output: JSON with booking proposals, confidence, and recommendation.
"""

import argparse
import json
import re
import sys
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import yaml


# --- Configuration ---

AUTO_BOOK_THRESHOLD = 0.95

SIGNAL_WEIGHTS = {
    "rule_type": 0.25,
    "similarity": 0.25,
    "uniqueness": 0.20,
    "historical": 0.15,
    "extraction": 0.15,
}

DEFAULT_HARD_GATES = {
    "no_rule_match": True,
    "new_vendor": True,
    "high_amount_threshold": 5000.00,
    "critical_accounts": ["1800", "2100"],
}


# --- Helper Functions ---

def extract_supplier_name(invoice_data: dict[str, Any]) -> str:
    """Extract supplier name from various field names."""
    for key in ("supplier_name", "vendor_name", "lieferant", "supplier", "vendor"):
        val = invoice_data.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return ""


def extract_line_items(invoice_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract line items from invoice data."""
    items = invoice_data.get("line_items", [])
    if isinstance(items, list):
        return items
    return []


def fuzzy_match(text_a: str, text_b: str) -> float:
    """Calculate fuzzy similarity between two strings (0.0-1.0)."""
    a = text_a.lower().strip()
    b = text_b.lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    # Direct substring match gets high score
    if a in b or b in a:
        return 0.90

    # Use SequenceMatcher for general fuzzy matching
    return SequenceMatcher(None, a, b).ratio()


def vendor_matches(vendor_name: str, pattern: str) -> bool:
    """Check if vendor name matches a vendor pattern."""
    name_lower = vendor_name.lower().strip()
    pattern_lower = pattern.lower().strip()

    # Direct substring match
    if pattern_lower in name_lower or name_lower in pattern_lower:
        return True

    # Regex match (for patterns like "Microsoft (Ireland|Azure)")
    try:
        if re.search(pattern, vendor_name, re.IGNORECASE):
            return True
    except re.error:
        pass

    # Fuzzy match fallback
    return fuzzy_match(vendor_name, pattern) >= 0.85


# --- Rule Loading ---

def load_rules(rules_path: str) -> dict[str, Any]:
    """Load kontierung rules from YAML."""
    path = Path(rules_path)
    if not path.exists():
        return {"vendor_rules": [], "semantic_rules": [], "vat_rules": {}, "credit_accounts": {}}

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_learned_rules(workspace: str) -> list[dict[str, Any]]:
    """Load learned rules from workspace."""
    path = Path(workspace) / "learned_rules.yaml"
    if not path.exists():
        return []

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("rules", [])
    except (yaml.YAMLError, OSError):
        return []


def check_vendor_is_known(vendor_name: str, workspace: str) -> bool:
    """Check if vendor has been seen before in booking history."""
    bookings_path = Path(workspace) / "bookings.jsonl"
    if not bookings_path.exists():
        return False

    vendor_lower = vendor_name.lower().strip()
    try:
        with open(bookings_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    booking = json.loads(line)
                    booked_vendor = (booking.get("supplier_name") or "").lower().strip()
                    if booked_vendor and (
                        booked_vendor in vendor_lower or vendor_lower in booked_vendor
                    ):
                        return True
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return False


# --- Rule Matching ---

def match_vendor_rules(
    vendor_name: str,
    vendor_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match vendor-only rules (highest priority)."""
    matches = []
    for rule in vendor_rules:
        pattern = rule.get("vendor_pattern", "")
        if vendor_matches(vendor_name, pattern):
            matches.append({
                "rule_id": rule.get("rule_id", ""),
                "rule_type": "vendor_only",
                "match_type": "exact",
                "target_account": rule.get("target_account", ""),
                "target_account_name": rule.get("target_account_name", ""),
                "similarity_score": 1.0,
                "priority": rule.get("priority", 100),
                "legal_basis": rule.get("legal_basis", ""),
                "is_ambiguous": False,
            })
    return matches


def match_semantic_rules(
    vendor_name: str,
    line_items: list[dict[str, Any]],
    semantic_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match vendor + item semantic rules using fuzzy matching."""
    matches = []

    for rule in semantic_rules:
        vendor_pattern = rule.get("vendor_pattern", ".*")
        # Check vendor pattern (wildcard means any vendor)
        if vendor_pattern != ".*" and not vendor_matches(vendor_name, vendor_pattern):
            continue

        item_patterns = rule.get("item_patterns", [])
        threshold = rule.get("similarity_threshold", 0.8)

        # Check each line item against rule patterns
        for item in line_items:
            item_desc = item.get("description", "")
            if not item_desc:
                continue

            best_similarity = 0.0
            best_pattern = ""

            for pattern in item_patterns:
                sim = fuzzy_match(item_desc, pattern)
                if sim > best_similarity:
                    best_similarity = sim
                    best_pattern = pattern

            if best_similarity >= threshold:
                matches.append({
                    "rule_id": rule.get("rule_id", ""),
                    "rule_type": "vendor_item",
                    "match_type": "semantic",
                    "target_account": rule.get("target_account", ""),
                    "target_account_name": rule.get("target_account_name", ""),
                    "similarity_score": round(best_similarity, 3),
                    "matched_item": item_desc,
                    "matched_pattern": best_pattern,
                    "priority": rule.get("priority", 50),
                    "legal_basis": rule.get("legal_basis", ""),
                    "note": rule.get("note", ""),
                    "is_ambiguous": False,
                })

    return matches


def match_learned_rules(
    vendor_name: str,
    line_items: list[dict[str, Any]],
    learned_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match learned rules (from previous bookings/corrections)."""
    matches = []

    for rule in learned_rules:
        if not rule.get("is_active", True):
            continue

        vendor_pattern = rule.get("vendor_pattern", "")
        if not vendor_matches(vendor_name, vendor_pattern):
            continue

        rule_type = rule.get("rule_type", "vendor_item")
        item_patterns = rule.get("item_patterns", [])
        source = rule.get("source", "auto_high_confidence")
        priority = rule.get("priority", 75)

        if rule_type == "vendor_only" or not item_patterns:
            # Vendor-only learned rule
            matches.append({
                "rule_id": rule.get("rule_id", ""),
                "rule_type": "vendor_only",
                "match_type": "exact",
                "rule_source": source,
                "target_account": rule.get("target_account", ""),
                "target_account_name": rule.get("target_account_name", ""),
                "similarity_score": 1.0,
                "priority": priority,
                "is_ambiguous": False,
            })
        else:
            # Vendor + item learned rule
            for item in line_items:
                item_desc = item.get("description", "")
                if not item_desc:
                    continue

                best_sim = 0.0
                for pattern in item_patterns:
                    sim = fuzzy_match(item_desc, pattern)
                    if sim > best_sim:
                        best_sim = sim

                if best_sim >= 0.75:
                    matches.append({
                        "rule_id": rule.get("rule_id", ""),
                        "rule_type": "vendor_item",
                        "match_type": "semantic" if best_sim < 0.95 else "exact",
                        "rule_source": source,
                        "target_account": rule.get("target_account", ""),
                        "target_account_name": rule.get("target_account_name", ""),
                        "similarity_score": round(best_sim, 3),
                        "matched_item": item_desc,
                        "priority": priority,
                        "is_ambiguous": False,
                    })

    return matches


# --- Booking Proposal Generation ---

def resolve_vat_account(
    vat_rate: float,
    vat_rules: dict[str, Any],
    is_reverse_charge: bool = False,
) -> dict[str, Any]:
    """Determine the correct VAT account based on rate."""
    if is_reverse_charge:
        rc = vat_rules.get("reverse_charge", {})
        return {
            "vat_account": rc.get("input_tax_account", "1577"),
            "vat_account_name": "Vorsteuer Reverse Charge",
            "legal_basis": rc.get("legal_basis", "§13b UStG"),
        }

    if abs(vat_rate - 0.07) < 0.01:
        reduced = vat_rules.get("reduced_rate", {})
        return {
            "vat_account": reduced.get("input_tax_account", "1571"),
            "vat_account_name": reduced.get("input_tax_name", "Abziehbare Vorsteuer 7%"),
            "legal_basis": reduced.get("legal_basis", "§15 Abs. 1 UStG"),
        }

    standard = vat_rules.get("standard_rate", {})
    return {
        "vat_account": standard.get("input_tax_account", "1576"),
        "vat_account_name": standard.get("input_tax_name", "Abziehbare Vorsteuer 19%"),
        "legal_basis": standard.get("legal_basis", "§15 Abs. 1 UStG"),
    }


def generate_booking_proposals(
    invoice_data: dict[str, Any],
    rule_matches: list[dict[str, Any]],
    rules_config: dict[str, Any],
    is_reverse_charge: bool = False,
) -> list[dict[str, Any]]:
    """Generate double-entry booking proposals from rule matches."""
    proposals = []
    vat_rules = rules_config.get("vat_rules", {})
    credit_config = rules_config.get("credit_accounts", {})
    credit_account = credit_config.get("liabilities", {}).get("account", "1600")
    credit_name = credit_config.get("liabilities", {}).get("name", "Verbindlichkeiten")

    line_items = extract_line_items(invoice_data)

    # Group matches by line item
    item_to_match: dict[str, dict[str, Any]] = {}
    general_matches = []

    for match in rule_matches:
        matched_item = match.get("matched_item", "")
        if matched_item:
            # Keep best match per item (highest priority, then similarity)
            key = matched_item.lower().strip()
            existing = item_to_match.get(key)
            if not existing or (
                match["priority"] > existing["priority"]
                or (match["priority"] == existing["priority"]
                    and match["similarity_score"] > existing["similarity_score"])
            ):
                item_to_match[key] = match
        else:
            general_matches.append(match)

    # Create proposals for matched items
    for item in line_items:
        desc = item.get("description", "")
        key = desc.lower().strip()
        match = item_to_match.get(key)

        if not match and general_matches:
            match = general_matches[0]

        if not match:
            continue

        net_amount = float(item.get("net_amount", item.get("unit_price", 0)) or 0)
        vat_rate = float(item.get("vat_rate", 0.19) or 0.19)
        vat_amount = round(net_amount * vat_rate, 2)

        vat_info = resolve_vat_account(vat_rate, vat_rules, is_reverse_charge)

        proposals.append({
            "line_item": desc,
            "debit_account": match["target_account"],
            "debit_account_name": match.get("target_account_name", ""),
            "credit_account": credit_account,
            "credit_account_name": credit_name,
            "net_amount": net_amount,
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "vat_account": vat_info["vat_account"],
            "vat_account_name": vat_info["vat_account_name"],
            "rule_id": match.get("rule_id", ""),
            "rule_type": match.get("rule_type", ""),
            "similarity_score": match.get("similarity_score", 0.0),
            "legal_basis": match.get("legal_basis", "§4 Abs. 4 EStG"),
        })

    # If no per-item match but we have a general vendor match, apply to all items
    if not proposals and general_matches:
        match = general_matches[0]
        total_net = float(invoice_data.get("total_net", invoice_data.get("net_amount", 0)) or 0)
        vat_rate_val = 0.19
        # Try to get rate from data
        vb = invoice_data.get("vat_breakdown", [])
        if isinstance(vb, list) and vb:
            vat_rate_val = float(vb[0].get("rate", 0.19) or 0.19)

        vat_info = resolve_vat_account(vat_rate_val, vat_rules, is_reverse_charge)

        proposals.append({
            "line_item": "Gesamtrechnung",
            "debit_account": match["target_account"],
            "debit_account_name": match.get("target_account_name", ""),
            "credit_account": credit_account,
            "credit_account_name": credit_name,
            "net_amount": total_net,
            "vat_rate": vat_rate_val,
            "vat_amount": round(total_net * vat_rate_val, 2),
            "vat_account": vat_info["vat_account"],
            "vat_account_name": vat_info["vat_account_name"],
            "rule_id": match.get("rule_id", ""),
            "rule_type": match.get("rule_type", ""),
            "similarity_score": match.get("similarity_score", 0.0),
            "legal_basis": match.get("legal_basis", "§4 Abs. 4 EStG"),
        })

    return proposals


# --- Confidence Evaluation ---

def calculate_confidence(
    rule_matches: list[dict[str, Any]],
    extraction_confidence: float,
    is_new_vendor: bool,
    invoice_amount: float,
    proposals: list[dict[str, Any]],
    hard_gate_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Calculate booking confidence with weighted signals and hard gates."""
    config = hard_gate_config or DEFAULT_HARD_GATES
    has_matches = len(rule_matches) > 0

    if not has_matches:
        # No matches at all
        signals = {
            "rule_type_score": 0.0,
            "similarity_score": 0.0,
            "uniqueness_score": 0.0,
            "historical_score": 0.0,
            "extraction_score": extraction_confidence,
        }
        overall = extraction_confidence * SIGNAL_WEIGHTS["extraction"]
    else:
        # Use best match for scoring
        best_match = max(rule_matches, key=lambda m: (m["priority"], m["similarity_score"]))

        # Rule type score
        rule_type = best_match.get("rule_type", "")
        rule_source = best_match.get("rule_source", "")
        match_type = best_match.get("match_type", "")
        similarity = best_match.get("similarity_score", 0.0)

        is_confirmed = rule_source in ("auto_high_confidence", "hitl_correction")
        is_exact = match_type == "exact" and similarity >= 0.95

        if rule_type == "vendor_only":
            rule_type_score = 1.0
        elif rule_type == "vendor_item":
            if is_confirmed and is_exact:
                rule_type_score = 0.98
            else:
                rule_type_score = 0.8
        else:
            rule_type_score = 0.6

        # Check ambiguity
        unique_accounts = set(m["target_account"] for m in rule_matches)
        is_ambiguous = len(unique_accounts) > 1
        uniqueness_score = 0.5 if is_ambiguous else 1.0

        signals = {
            "rule_type_score": rule_type_score,
            "similarity_score": similarity,
            "uniqueness_score": uniqueness_score,
            "historical_score": 0.85,  # Default for learned rules
            "extraction_score": extraction_confidence,
        }

        overall = sum(
            SIGNAL_WEIGHTS[k.replace("_score", "")] * v
            for k, v in signals.items()
        )

    # Hard gates
    triggered_gates = []

    if config.get("no_rule_match", True) and not has_matches:
        triggered_gates.append({
            "gate_type": "no_rule_match",
            "reason": "Keine passende Buchungsregel gefunden",
        })

    if config.get("new_vendor", True) and is_new_vendor:
        triggered_gates.append({
            "gate_type": "new_vendor",
            "reason": "Erster Beleg von diesem Lieferanten",
        })

    threshold = config.get("high_amount_threshold", 5000.0)
    if invoice_amount > threshold:
        triggered_gates.append({
            "gate_type": "high_amount",
            "reason": f"Betrag {invoice_amount:.2f} EUR > {threshold:.2f} EUR",
        })

    critical_accounts = config.get("critical_accounts", [])
    for proposal in proposals:
        if proposal.get("debit_account") in critical_accounts:
            triggered_gates.append({
                "gate_type": "critical_account",
                "reason": f"Kritisches Konto: {proposal['debit_account']}",
            })
            break

    # Recommendation
    if triggered_gates:
        recommendation = "hitl_review"
        explanation = "HITL erforderlich: " + "; ".join(g["reason"] for g in triggered_gates)
    elif overall >= AUTO_BOOK_THRESHOLD:
        recommendation = "auto_book"
        explanation = f"Confidence {overall:.1%} >= Schwelle {AUTO_BOOK_THRESHOLD:.1%}"
    else:
        recommendation = "hitl_review"
        explanation = f"Confidence {overall:.1%} < Schwelle {AUTO_BOOK_THRESHOLD:.1%}"

    return {
        "overall_confidence": round(overall, 4),
        "signals": signals,
        "recommendation": recommendation,
        "triggered_hard_gates": triggered_gates,
        "explanation": explanation,
        "auto_book_threshold": AUTO_BOOK_THRESHOLD,
    }


# --- Main Orchestration ---

def run_kontierung(
    invoice_data: dict[str, Any],
    rules_path: str,
    workspace: str = ".bookkeeping",
    is_reverse_charge: bool = False,
    extraction_confidence: float = 0.9,
) -> dict[str, Any]:
    """
    Run full kontierung pipeline: match rules, generate proposals, evaluate confidence.
    """
    supplier_name = extract_supplier_name(invoice_data)
    line_items = extract_line_items(invoice_data)

    if not supplier_name:
        return {
            "success": False,
            "error": "Lieferantenname fehlt in den Rechnungsdaten",
            "rule_matches": [],
            "booking_proposals": [],
        }

    # Load rules
    rules_config = load_rules(rules_path)
    learned_rules = load_learned_rules(workspace)

    # Phase 1: Match rules (priority order)
    all_matches = []

    # 1a. Learned rules (highest priority if confirmed)
    learned_matches = match_learned_rules(supplier_name, line_items, learned_rules)
    all_matches.extend(learned_matches)

    # 1b. Vendor-only rules
    vendor_matches_list = match_vendor_rules(
        supplier_name,
        rules_config.get("vendor_rules", []),
    )
    all_matches.extend(vendor_matches_list)

    # 1c. Semantic rules (fuzzy item matching)
    semantic_matches = match_semantic_rules(
        supplier_name,
        line_items,
        rules_config.get("semantic_rules", []),
    )
    all_matches.extend(semantic_matches)

    # Sort by priority (desc), then similarity (desc)
    all_matches.sort(key=lambda m: (m["priority"], m["similarity_score"]), reverse=True)

    # Phase 2: Generate booking proposals
    proposals = generate_booking_proposals(
        invoice_data, all_matches, rules_config, is_reverse_charge
    )

    # Phase 3: Check vendor history
    is_new_vendor = not check_vendor_is_known(supplier_name, workspace)

    # Phase 4: Calculate confidence
    gross_amount = float(
        invoice_data.get("total_gross", invoice_data.get("gross_amount", 0)) or 0
    )
    confidence = calculate_confidence(
        all_matches,
        extraction_confidence,
        is_new_vendor,
        gross_amount,
        proposals,
    )

    # Collect unmatched items
    matched_items = {m.get("matched_item", "").lower().strip() for m in all_matches if m.get("matched_item")}
    unmatched_items = [
        item.get("description", "")
        for item in line_items
        if item.get("description", "").lower().strip() not in matched_items
    ]

    return {
        "success": True,
        "supplier_name": supplier_name,
        "is_new_vendor": is_new_vendor,
        "rule_matches": all_matches,
        "rules_applied": len(set(m["rule_id"] for m in all_matches)),
        "booking_proposals": proposals,
        "unmatched_items": unmatched_items,
        "confidence": confidence,
    }


def main():
    parser = argparse.ArgumentParser(description="Kontierung (account assignment)")
    parser.add_argument("--input", "-i", help="Path to invoice JSON file (or use stdin)")
    parser.add_argument("--rules", "-r", required=True, help="Path to kontierung_rules.yaml")
    parser.add_argument("--workspace", "-w", default=".bookkeeping", help="Workspace directory")
    parser.add_argument("--reverse-charge", action="store_true", help="Flag as reverse charge")
    parser.add_argument("--extraction-confidence", type=float, default=0.9,
                        help="Extraction confidence score (0.0-1.0)")
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            invoice_data = json.load(f)
    else:
        invoice_data = json.load(sys.stdin)

    result = run_kontierung(
        invoice_data,
        args.rules,
        args.workspace,
        args.reverse_charge,
        args.extraction_confidence,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
