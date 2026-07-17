from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from .common import comparison_name, parse_decimal, write_json

GOLD_SNAPSHOT_MAP = {
    "AUTO-SNP-001": "SNP-001",
    "AUTO-SNP-002": "SNP-009",
    "AUTO-SNP-003": "SNP-010",
    "AUTO-SNP-004": "SNP-011",
    "AUTO-SNP-005": "SNP-012",
    "AUTO-SNP-006": "SNP-013",
    "AUTO-SNP-007": "SNP-014",
    "AUTO-SNP-008": "SNP-015",
}


def _main_gold_events(bundle: dict) -> list[dict]:
    rows = bundle["candidate_event_register"]["candidate_events"]
    return [r for r in rows if r["event_id"].startswith("CE-") and r["event_id"].count("-") == 1]


def _type_set(value: str | list[str]) -> set[str]:
    if isinstance(value, list):
        return set(value)
    return set(str(value).split("|"))


def _event_match(auto: dict, gold: dict) -> bool:
    if auto["review_status"] != "AUTO_EXTRACTED":
        return False
    a_types = _type_set(auto["event_types"])
    g_types = _type_set(gold["event_types"])
    if gold["event_id"] == "CE-014":
        return bool({"special_rights_agreement", "termination"} & a_types)
    if auto.get("event_date_normalized"):
        auto_y_m = auto["event_date_normalized"].split("/")[0]
        gold_date = gold.get("event_date", "")
        if gold_date and not gold_date.startswith(auto_y_m):
            return False
    return bool(a_types & g_types)


def compare_events(auto_events: list[dict], bundle: dict) -> tuple[list[dict], dict]:
    gold_events = _main_gold_events(bundle)
    matches: list[dict] = []
    used: set[str] = set()
    for gold in gold_events:
        candidate = next((a for a in auto_events if a["auto_event_id"] not in used and _event_match(a, gold)), None)
        if candidate:
            used.add(candidate["auto_event_id"])
            status = "AUTO_MATCH"
            auto_id = candidate["auto_event_id"]
        elif gold["event_id"] in {"CE-002", "CE-003", "CE-004", "CE-005", "CE-006", "CE-007"} and any(a["review_status"] == "REVIEW_REQUIRED" for a in auto_events):
            status = "ROUTED_TO_VISUAL_REVIEW"
            auto_id = next(a["auto_event_id"] for a in auto_events if a["review_status"] == "REVIEW_REQUIRED")
        else:
            status = "MISSED"
            auto_id = None
        matches.append(
            {
                "gold_event_id": gold["event_id"],
                "gold_event_date": gold["event_date"],
                "gold_event_name": gold["event_name"],
                "auto_event_id": auto_id,
                "match_status": status,
            }
        )
    strict = sum(1 for x in matches if x["match_status"] == "AUTO_MATCH")
    routed = sum(1 for x in matches if x["match_status"] == "ROUTED_TO_VISUAL_REVIEW")
    missed = sum(1 for x in matches if x["match_status"] == "MISSED")
    text_candidates = [a for a in auto_events if a["review_status"] == "AUTO_EXTRACTED"]
    metrics = {
        "gold_main_event_count": len(gold_events),
        "auto_matched_event_count": strict,
        "visual_review_routed_event_count": routed,
        "missed_event_count": missed,
        "strict_event_recall": round(strict / len(gold_events), 6) if gold_events else None,
        "coverage_including_review_routing": round((strict + routed) / len(gold_events), 6) if gold_events else None,
        "auto_text_candidate_count": len(text_candidates),
        "auto_text_candidate_precision": round(strict / len(text_candidates), 6) if text_candidates else None,
    }
    return matches, metrics


def _entity_alias_map(bundle: dict) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for entity in bundle.get("canonical_entities", []):
        canonical = entity.get("canonical_name") or ""
        values = {canonical}
        for mapping in entity.get("name_mappings", []):
            values.update({mapping.get("raw_name") or "", mapping.get("normalized_name") or "", mapping.get("canonical_name") or ""})
        stage06 = entity.get("stage06_party_attributes") or {}
        values.update(stage06.get("name_variants") or [])
        values.update({stage06.get("original_name") or "", stage06.get("standardized_name") or ""})
        for value in values:
            if value:
                aliases[comparison_name(value)] = canonical
    return aliases


def _canonical_compare_name(value: str, aliases: dict[str, str]) -> str:
    key = comparison_name(value)
    return comparison_name(aliases.get(key, value))


def _gold_holding_rows(bundle: dict, snapshot_id: str) -> list[dict]:
    rows = []
    for r in bundle["normalized_snapshots"]:
        if r.get("snapshot_id") == snapshot_id and r.get("record_type") == "HOLDING":
            a = r["attributes"]
            value = a["holding_shares_original"]
            if value is None:
                value = a["holding_amount_original"]
            if value is None:
                value = a.get("holding_after_calculated")
            percentage = a.get("holding_percentage_original")
            if percentage is None:
                percentage = a.get("holding_percentage_calculated")
            rows.append(
                {
                    "name": a["original_party_name"],
                    "holding_value": value,
                    "holding_percentage": percentage,
                }
            )
    return rows


def compare_snapshots(auto_holdings: list[dict], bundle: dict) -> tuple[list[dict], dict]:
    comparison: list[dict] = []
    metrics_by_snapshot: dict[str, dict] = {}
    aliases = _entity_alias_map(bundle)
    for auto_sid, gold_sid in GOLD_SNAPSHOT_MAP.items():
        auto_rows = [r for r in auto_holdings if r["auto_snapshot_id"] == auto_sid]
        gold_rows = _gold_holding_rows(bundle, gold_sid)
        gold_by_name = {_canonical_compare_name(r["name"], aliases): r for r in gold_rows}
        matched = 0
        exact_value = 0
        exact_pct = 0
        for auto in auto_rows:
            key = _canonical_compare_name(auto["shareholder_original_name"], aliases)
            gold = gold_by_name.get(key)
            if gold is None:
                for gkey, grow in gold_by_name.items():
                    if key in gkey or gkey in key:
                        gold = grow
                        break
            if gold:
                matched += 1
                av, gv = parse_decimal(auto["holding_value"]), parse_decimal(gold["holding_value"])
                ap, gp = parse_decimal(auto["holding_percentage"]), parse_decimal(gold["holding_percentage"])
                value_ok = av == gv
                # PDF tables disclose percentages to two decimals; calculated gold can contain more precision.
                pct_ok = ap is not None and gp is not None and ap.quantize(Decimal("0.01")) == gp.quantize(Decimal("0.01"))
                exact_value += int(value_ok)
                exact_pct += int(pct_ok)
                status = "MATCH" if value_ok and pct_ok else "VALUE_DIFFERENCE"
            else:
                value_ok = pct_ok = False
                status = "NAME_UNMATCHED"
            comparison.append(
                {
                    "auto_snapshot_id": auto_sid,
                    "gold_snapshot_id": gold_sid,
                    "shareholder_original_name": auto["shareholder_original_name"],
                    "auto_holding_value": auto["holding_value"],
                    "auto_holding_percentage": auto["holding_percentage"],
                    "gold_holding_value": str(gold["holding_value"]) if gold else None,
                    "gold_holding_percentage": str(gold["holding_percentage"]) if gold else None,
                    "comparison_status": status,
                }
            )
        metrics_by_snapshot[auto_sid] = {
            "gold_snapshot_id": gold_sid,
            "auto_row_count": len(auto_rows),
            "gold_row_count": len(gold_rows),
            "name_match_count": matched,
            "exact_value_count": exact_value,
            "exact_percentage_count": exact_pct,
            "full_exact_row_count": sum(1 for x in comparison if x["auto_snapshot_id"] == auto_sid and x["comparison_status"] == "MATCH"),
        }
    total_auto = sum(x["auto_row_count"] for x in metrics_by_snapshot.values())
    total_gold = sum(x["gold_row_count"] for x in metrics_by_snapshot.values())
    total_exact = sum(x["full_exact_row_count"] for x in metrics_by_snapshot.values())
    metrics = {
        "snapshot_count": len(metrics_by_snapshot),
        "auto_holding_row_count": total_auto,
        "gold_holding_row_count": total_gold,
        "full_exact_holding_row_count": total_exact,
        "holding_row_exact_rate": round(total_exact / total_gold, 6) if total_gold else None,
        "by_snapshot": metrics_by_snapshot,
    }
    return comparison, metrics


def _gold_text_transaction_legs(bundle: dict) -> list[dict]:
    target_events = {"CE-009", "CE-010-01", "CE-010-02", "CE-010-03", "CE-011", "CE-012", "CE-013-01", "CE-013-02"}
    rows: list[dict] = []
    for tx in bundle["normalized_transactions"]:
        if tx["transaction_level"] not in {"PARTICIPANT_LEG", "TRANSFER_LOT"}:
            continue
        if not target_events.intersection(tx.get("event_ids", [])):
            continue
        a = tx["attributes"]
        if tx["transaction_level"] == "PARTICIPANT_LEG":
            shares = a.get("shares_acquired_original")
            unit = a.get("shares_unit")
            if shares is None:
                shares = a.get("subscribed_capital_original")
                unit = "万股" if shares is not None else unit
            rows.append(
                {
                    "transaction_type": "CAPITAL_INCREASE",
                    "transferor": None,
                    "party": a.get("original_party_name"),
                    "cash_amount_wan": a.get("cash_contribution_original"),
                    "shares": shares,
                    "shares_unit": unit,
                }
            )
        else:
            rows.append(
                {
                    "transaction_type": "EQUITY_TRANSFER",
                    "transferor": a.get("transferor_original_name"),
                    "party": a.get("transferee_original_name"),
                    "cash_amount_wan": a.get("consideration_original"),
                    "shares": a.get("transferred_shares_original"),
                    "shares_unit": "股",
                }
            )
    return rows

def _leg_key(row: dict) -> tuple:
    def n(v: Any) -> str | None:
        d = parse_decimal(v)
        return format(d.normalize(), "f") if d is not None else None
    shares = parse_decimal(row.get("shares"))
    unit = row.get("shares_unit")
    if shares is not None and unit == "万股":
        shares = shares * Decimal("10000")
    return (
        row["transaction_type"],
        comparison_name(row.get("transferor") or ""),
        comparison_name(row.get("party") or row.get("investor_or_transferee") or ""),
        n(row.get("cash_amount_wan")),
        n(shares),
        "股" if shares is not None else unit,
    )


def compare_transaction_legs(auto_legs: list[dict], bundle: dict) -> tuple[list[dict], dict]:
    gold = _gold_text_transaction_legs(bundle)
    gold_buckets: dict[tuple, list[int]] = defaultdict(list)
    for i, row in enumerate(gold):
        gold_buckets[_leg_key(row)].append(i)
    comparison: list[dict] = []
    matched_gold: set[int] = set()
    for auto in auto_legs:
        key = _leg_key(auto)
        candidates = gold_buckets.get(key, [])
        idx = next((x for x in candidates if x not in matched_gold), None)
        if idx is not None:
            matched_gold.add(idx)
            status = "MATCH"
        else:
            status = "UNMATCHED_AUTO"
        comparison.append(
            {
                "auto_leg_id": auto["auto_leg_id"],
                "transaction_type": auto["transaction_type"],
                "transferor": auto.get("transferor"),
                "party": auto.get("investor_or_transferee"),
                "cash_amount_wan": auto.get("cash_amount_wan"),
                "shares": auto.get("shares"),
                "shares_unit": auto.get("shares_unit"),
                "comparison_status": status,
            }
        )
    metrics = {
        "gold_text_transaction_leg_count": len(gold),
        "auto_transaction_leg_count": len(auto_legs),
        "matched_transaction_leg_count": len(matched_gold),
        "transaction_leg_recall": round(len(matched_gold) / len(gold), 6) if gold else None,
        "transaction_leg_precision": round(len(matched_gold) / len(auto_legs), 6) if auto_legs else None,
    }
    return comparison, metrics


def write_csv(path: str | Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def evaluate(auto_events: list[dict], auto_legs: list[dict], auto_holdings: list[dict], gold_path: str | Path, output_dir: str | Path) -> dict:
    with open(gold_path, "r", encoding="utf-8") as f:
        bundle = json.load(f)
    event_rows, event_metrics = compare_events(auto_events, bundle)
    snapshot_rows, snapshot_metrics = compare_snapshots(auto_holdings, bundle)
    leg_rows, leg_metrics = compare_transaction_legs(auto_legs, bundle)
    out = Path(output_dir)
    write_csv(out / "event_comparison.csv", event_rows)
    write_csv(out / "snapshot_holding_comparison.csv", snapshot_rows)
    write_csv(out / "transaction_leg_comparison.csv", leg_rows)
    metrics = {"events": event_metrics, "snapshots": snapshot_metrics, "transaction_legs": leg_metrics}
    write_json(out / "metrics.json", metrics)
    return metrics
