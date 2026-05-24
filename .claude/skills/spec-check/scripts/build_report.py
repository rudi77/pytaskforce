#!/usr/bin/env python3
"""Aggregate mech + LLM results into a Markdown report with severity grading."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

REPO = Path("/home/user/pytaskforce")
MECH = json.loads(Path("/tmp/mech_results.json").read_text())
LLM_DIR = Path("/tmp/spec_llm_results")

# Spec frontmatter helper (re-parse for status/last_verified/known_gaps)
SPEC_DATA: dict[str, dict] = {}
for sf in sorted(Path("/tmp").glob("spec_*.json")):
    name = sf.stem.replace("spec_", "")
    SPEC_DATA[name] = json.loads(sf.read_text())

CRITICAL_KEYWORDS = re.compile(
    r"\b(security|auth|token|leak|secret|cascade|delete|race|deadlock|crash|inject|csrf|"
    r"unauthori[sz]ed|signature|exfiltrat|escal|root|sudo|sensitive)\b", re.I
)


def severity_for_invariant_fail(claim: str) -> str:
    return "P0" if CRITICAL_KEYWORDS.search(claim) else "P1"


def severity_for_capability_fail(claim: str) -> str:
    return "P0"  # capability FAIL = feature broken


def known_gap_matches(claim: str, known_gaps: list[str]) -> bool:
    """Demote a FAIL to 'info' when the claim is acknowledged in known_gaps."""
    if not known_gaps:
        return False
    claim_kw = set(re.findall(r"\b\w{4,}\b", claim.lower()))
    if not claim_kw:
        return False
    for gap in known_gaps:
        gap_kw = set(re.findall(r"\b\w{4,}\b", gap.lower()))
        overlap = claim_kw & gap_kw
        if len(overlap) >= 4:  # 4+ shared 4+-char tokens → likely the same topic
            return True
    return False


def main():
    findings: list[dict] = []
    per_feature: dict[str, dict] = {}

    for feature in sorted(set(list(MECH.keys()) + [p.stem for p in LLM_DIR.glob("*.json")])):
        mech = MECH.get(feature, {})
        llm_path = LLM_DIR / f"{feature}.json"
        llm = json.loads(llm_path.read_text()) if llm_path.exists() else None
        spec = SPEC_DATA.get(feature, {})
        fm = spec.get("frontmatter", {})
        known_gaps = spec.get("known_gaps", [])

        feat = {
            "feature": feature,
            "status": fm.get("status", "?"),
            "since": fm.get("since", ""),
            "last_verified": fm.get("last_verified", ""),
            "mech_counts": mech.get("counts", {}),
            "mech_pass": 0, "mech_fail": 0, "mech_warn": 0, "mech_total": 0,
            "cap_pass": 0, "cap_fail": 0, "cap_uncertain": 0, "cap_skipped": 0, "cap_total": 0,
            "inv_pass": 0, "inv_fail": 0, "inv_uncertain": 0, "inv_skipped": 0, "inv_total": 0,
            "llm_loaded": llm is not None,
            "llm_findings": [],
            "mech_findings": [],
        }

        # Mechanical counts + findings
        for cat, items in mech.get("mech", {}).items():
            for x in items:
                feat["mech_total"] += 1
                v = x.get("verdict")
                if v == "PASS":
                    feat["mech_pass"] += 1
                elif v == "WARN":
                    feat["mech_warn"] += 1
                elif v == "FAIL":
                    feat["mech_fail"] += 1
                    label = x.get("method", "") + " " + x.get("path", "") if cat == "routes" else (x.get("key") or x.get("name") or x.get("symbol") or "?")
                    title = f"{cat}: {label}"
                    # Compute severity
                    sev = {
                        "routes": "P0",
                        "configs": "P1",
                        "events": "P1",
                        "extension_points": "P1",
                    }[cat]
                    # If known-gap matches the failing label, demote to info
                    if known_gap_matches(label, known_gaps):
                        sev = "info"
                    f = {
                        "feature": feature,
                        "kind": "mechanical",
                        "section": cat,
                        "title": title,
                        "verdict": "FAIL",
                        "evidence": x.get("evidence", ""),
                        "severity": sev,
                    }
                    feat["mech_findings"].append(f)
                    findings.append(f)

        # LLM counts + findings
        if llm:
            for cap in llm.get("capabilities", []):
                v = cap.get("verdict")
                feat["cap_total"] += 1
                if v == "PASS":
                    feat["cap_pass"] += 1
                elif v == "FAIL":
                    feat["cap_fail"] += 1
                    claim = cap.get("claim", "")
                    sev = "info" if known_gap_matches(claim, known_gaps) else "P0"
                    f = {
                        "feature": feature, "kind": "capability", "title": claim[:140],
                        "verdict": "FAIL", "evidence": cap.get("evidence", ""),
                        "severity": sev, "known_gap_match": sev == "info",
                    }
                    feat["llm_findings"].append(f)
                    findings.append(f)
                elif v == "UNCERTAIN":
                    feat["cap_uncertain"] += 1
                    claim = cap.get("claim", "")
                    f = {
                        "feature": feature, "kind": "capability", "title": claim[:140],
                        "verdict": "UNCERTAIN", "evidence": cap.get("evidence", ""),
                        "severity": "P2",
                    }
                    feat["llm_findings"].append(f)
                    findings.append(f)
                elif v == "SKIPPED":
                    feat["cap_skipped"] += 1
            for inv in llm.get("invariants", []):
                v = inv.get("verdict")
                feat["inv_total"] += 1
                if v == "PASS":
                    feat["inv_pass"] += 1
                elif v == "FAIL":
                    feat["inv_fail"] += 1
                    claim = inv.get("claim", "")
                    if known_gap_matches(claim, known_gaps):
                        sev = "info"
                    else:
                        sev = severity_for_invariant_fail(claim)
                    f = {
                        "feature": feature, "kind": "invariant", "title": claim[:160],
                        "verdict": "FAIL", "evidence": inv.get("evidence", ""),
                        "severity": sev, "known_gap_match": sev == "info",
                    }
                    feat["llm_findings"].append(f)
                    findings.append(f)
                elif v == "UNCERTAIN":
                    feat["inv_uncertain"] += 1
                    claim = inv.get("claim", "")
                    f = {
                        "feature": feature, "kind": "invariant", "title": claim[:160],
                        "verdict": "UNCERTAIN", "evidence": inv.get("evidence", ""),
                        "severity": "P2",
                    }
                    feat["llm_findings"].append(f)
                    findings.append(f)
                elif v == "SKIPPED":
                    feat["inv_skipped"] += 1

        per_feature[feature] = feat

    # Aging warnings
    today = datetime.date(2026, 5, 24)
    aging: list[tuple[str, str]] = []
    for f, feat in per_feature.items():
        lv = feat.get("last_verified", "")
        if not lv:
            continue
        try:
            d = datetime.date.fromisoformat(lv)
            if (today - d).days > 30:
                aging.append((f, lv))
        except ValueError:
            pass

    # Severity bucketing
    by_sev = {"P0": [], "P1": [], "P2": [], "info": []}
    for f in findings:
        by_sev.setdefault(f["severity"], []).append(f)

    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = Path(f"tmp/spec_check_{ts}.md")
    out.parent.mkdir(exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Spec-Check Report — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"**Specs checked:** {len(per_feature)} / {len(SPEC_DATA)}")
    total_claims = sum(f["mech_total"] + f["cap_total"] + f["inv_total"] for f in per_feature.values())
    lines.append(f"**Total claims verified:** {total_claims}")
    lines.append(f"**Findings:** {len(by_sev['P0'])} P0, {len(by_sev['P1'])} P1, {len(by_sev['P2'])} P2, {len(by_sev['info'])} info")
    if aging:
        lines.append(f"**Aging specs (>30 days unverified):** {len(aging)}")
    lines.append("")

    # Summary table
    lines.append("## Summary table")
    lines.append("")
    lines.append("| Feature | Status | Mech (P/W/F) | Caps (P/F/U) | Inv (P/F/U) | Verdict |")
    lines.append("|---------|--------|--------------|--------------|-------------|---------|")
    for f, feat in sorted(per_feature.items()):
        mech_str = f"{feat['mech_pass']}/{feat['mech_warn']}/{feat['mech_fail']}"
        cap_str = f"{feat['cap_pass']}/{feat['cap_fail']}/{feat['cap_uncertain']}"
        inv_str = f"{feat['inv_pass']}/{feat['inv_fail']}/{feat['inv_uncertain']}"
        # verdict
        n_real_fail = sum(1 for fnd in feat["llm_findings"] + feat["mech_findings"]
                          if fnd["verdict"] == "FAIL" and fnd["severity"] != "info")
        n_uncertain = feat["cap_uncertain"] + feat["inv_uncertain"]
        if not feat["llm_loaded"]:
            verdict = "MECH-ONLY"
        elif n_real_fail == 0 and n_uncertain == 0:
            verdict = "OK"
        elif n_real_fail == 0:
            verdict = "DRIFT"
        else:
            verdict = f"REGRESSION ({n_real_fail})"
        lines.append(f"| {f} | {feat['status']} | {mech_str} | {cap_str} | {inv_str} | {verdict} |")
    lines.append("")

    # Findings, P0 → P1 → P2 → info
    lines.append("## Findings")
    lines.append("")
    for sev in ("P0", "P1", "P2", "info"):
        if not by_sev[sev]:
            continue
        sev_label = {"P0": "Critical (P0)", "P1": "Drift (P1)", "P2": "Ambiguous (P2)", "info": "Acknowledged (info)"}[sev]
        lines.append(f"### {sev_label} — {len(by_sev[sev])} findings")
        lines.append("")
        for f in by_sev[sev]:
            tag = f["kind"]
            lines.append(f"- **{f['feature']}** — _{tag}_: {f['title']}")
            ev = f.get("evidence", "")
            if ev:
                lines.append(f"  - Evidence: `{ev}`")
            if f.get("known_gap_match"):
                lines.append(f"  - _Note: matched a Known-gap entry — demoted to info_")
        lines.append("")

    # Aging
    if aging:
        lines.append("## Aging specs (last_verified > 30 days ago)")
        lines.append("")
        for f, lv in sorted(aging):
            lines.append(f"- {f}: last_verified={lv}")
        lines.append("")

    out.write_text("\n".join(lines))
    print(f"Wrote {out}")
    print(f"\nSeverity summary: {len(by_sev['P0'])} P0, {len(by_sev['P1'])} P1, {len(by_sev['P2'])} P2, {len(by_sev['info'])} info")


if __name__ == "__main__":
    main()
