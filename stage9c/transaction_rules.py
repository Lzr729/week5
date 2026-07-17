from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from . import RULE_SET_VERSION, __version__
from .numeric_rules import D
from .trace import as_tokens, dedupe, trace_from_evidence


def transaction_evaluations(model: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    transactions = model["normalized_transactions"]
    increase_events = {row["source_record_id"]: row for row in transactions if row["source_dataset"] == "increase_events"}
    transfer_events = {row["source_record_id"]: row for row in transactions if row["source_dataset"] == "transfer_events"}
    subscriptions = [row for row in transactions if row["source_dataset"] == "subscriptions"]
    lots = [row for row in transactions if row["source_dataset"] == "transfer_lots"]
    lots_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lot in lots:
        lots_by_parent[str(lot["attributes"].get("transfer_event_id"))].append(lot)
    subs_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sub in subscriptions:
        subs_by_parent[str(sub["attributes"].get("increase_id"))].append(sub)

    output: list[dict[str, Any]] = []
    for row in transactions:
        checks: list[dict[str, Any]] = []
        expected_level = {"increase_events": "EVENT", "subscriptions": "PARTICIPANT_LEG", "transfer_events": "EVENT", "transfer_lots": "TRANSFER_LOT"}[row["source_dataset"]]
        _check(checks, "S09-T001", row["transaction_level"] == expected_level, row["transaction_level"], expected_level, "事件层与原子交易层分离")

        parent_ok = True
        parent_observed: Any = "not_applicable"
        if row["source_dataset"] == "subscriptions":
            parent_observed = row["attributes"].get("increase_id")
            parent_ok = str(parent_observed) in increase_events
        elif row["source_dataset"] == "transfer_lots":
            parent_observed = row["attributes"].get("transfer_event_id")
            parent_ok = str(parent_observed) in transfer_events
        _check(checks, "S09-T002", parent_ok, parent_observed, "existing parent event", "原子交易引用父事件")

        aggregate_ok, aggregate_observed = _aggregate_check(row, lots_by_parent)
        _check(checks, "S09-T003", aggregate_ok, aggregate_observed, "event aggregate equals lots", "转让事件与逐笔明细勾稽")
        price_ok, price_observed = _unit_price_check(row)
        _check(checks, "S09-T004", price_ok, price_observed, "consideration*10000/shares", "逐笔转让单位价格复算")
        transfer_capital_ok = row["transaction_type"] != "SHARE_TRANSFER" or row["attributes"].get("registered_capital_unchanged", True) is True
        _check(checks, "S09-T005", transfer_capital_ok, row["attributes"].get("registered_capital_unchanged"), True, "股权/股份转让不改变注册资本")

        increase_ok, increase_observed = _increase_arithmetic(row)
        _check(checks, "S09-T006", increase_ok, increase_observed, "before + change = after, except retained CE-005 disclosure difference", "增资资本算术勾稽")
        no_average_ok, no_average_observed = _no_average_inference(row, subs_by_parent)
        _check(checks, "S09-T007", no_average_ok, no_average_observed, "undisclosed participant values remain null", "禁止对共同增资额平均分配")
        conversion_ok, conversion_observed = _subscription_conversion(row)
        _check(checks, "S09-T008", conversion_ok, conversion_observed, "capital*10000=shares", "已披露认缴资本与股份换算")
        _check(checks, "S09-T009", True, "evaluated_on_snapshot_records", "evaluated_on_snapshot_records", "完整快照持股合计规则在快照记录执行")
        _check(checks, "S09-T010", True, "evaluated_on_snapshot_records", "evaluated_on_snapshot_records", "完整快照比例合计规则在快照记录执行")

        evidence_ids = dedupe(row.get("evidence_ids", []))
        trace = trace_from_evidence(model, evidence_ids)
        trace["original_excerpts"] = dedupe(trace["original_excerpts"] + [str(x) for x in row.get("original_excerpts", []) if x])
        overall = "PASS" if all(x["result"] == "PASS" for x in checks) else "FAIL"
        output.append({
            "evaluation_id": f"S09-9C-TXN-{row['source_record_id']}",
            "object_type": "TRANSACTION",
            "object_id": row["canonical_transaction_id"],
            "event_ids": row.get("event_ids", []),
            **trace,
            "transaction_type": row["transaction_type"],
            "transaction_level": row["transaction_level"],
            "checks": checks,
            "overall_result": overall,
            "derivation_type": "RULE_CLASSIFICATION_AND_DETERMINISTIC_CALCULATION",
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "run_id": run_id,
            "review_required": overall == "FAIL",
            "review_status": "AUTO_PASS_PENDING_9C_ACCEPTANCE" if overall == "PASS" else "PENDING_9D_REVIEW",
        })

    output.extend(snapshot_evaluations(model, run_id))
    return output


def snapshot_evaluations(model: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    rows = model["normalized_snapshots"]
    holdings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["record_type"] == "HOLDING":
            holdings[str(row["snapshot_id"])].append(row)
    output: list[dict[str, Any]] = []
    for row in rows:
        if row["record_type"] != "SNAPSHOT":
            continue
        attrs = row["attributes"]
        checks = []
        complete = attrs.get("completeness_status") == "complete"
        total_ok, total_observed = _snapshot_total(attrs, holdings.get(str(row["snapshot_id"]), [])) if complete else (True, "not_applicable_incomplete_snapshot")
        _check(checks, "S09-T009", total_ok, total_observed, attrs.get("capital_total_original") or attrs.get("capital_total_calculated"), "完整快照逐主体持股合计等于总资本/总股本")
        pct_ok, pct_observed = _snapshot_percentages(holdings.get(str(row["snapshot_id"]), [])) if complete else (True, "not_applicable_incomplete_snapshot")
        _check(checks, "S09-T010", pct_ok, pct_observed, "approximately 100%", "完整快照持股比例合计为100%（允许披露舍入）")
        for rule_id in ("S09-T001", "S09-T002", "S09-T003", "S09-T004", "S09-T005", "S09-T006", "S09-T007", "S09-T008"):
            _check(checks, rule_id, True, "not_applicable_snapshot", "not_applicable_snapshot", "非快照规则")
        trace = trace_from_evidence(model, row.get("evidence_ids", []))
        overall = "PASS" if all(x["result"] == "PASS" for x in checks) else "FAIL"
        output.append({
            "evaluation_id": f"S09-9C-SNP-{row['snapshot_id']}",
            "object_type": "EQUITY_SNAPSHOT",
            "object_id": row["snapshot_id"],
            "event_ids": row.get("event_ids", []) or as_tokens(attrs.get("trigger_event_id")) or ["GLOBAL"],
            **trace,
            "completeness_status": attrs.get("completeness_status"),
            "checks": checks,
            "overall_result": overall,
            "derivation_type": "DETERMINISTIC_AGGREGATION_AND_RULE_CLASSIFICATION",
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "run_id": run_id,
            "review_required": overall == "FAIL",
            "review_status": "AUTO_PASS_PENDING_9C_ACCEPTANCE" if overall == "PASS" else "PENDING_9D_REVIEW",
        })
    return output


def _aggregate_check(row: dict[str, Any], lots_by_parent: dict[str, list[dict[str, Any]]]) -> tuple[bool, Any]:
    if row["source_dataset"] != "transfer_events":
        return True, "not_applicable"
    lots = lots_by_parent.get(row["source_record_id"], [])
    if not lots:
        return False, {"lot_count": 0}
    attrs = row["attributes"]
    measures = [
        ("shares", "transferred_shares_original", "total_transferred_original", "total_transferred_calculated", "股"),
        ("percentage", "transferred_percentage_original", "total_transferred_original", "total_transferred_calculated", "%"),
        ("consideration", "consideration_original", "total_consideration_original", "total_consideration_calculated", "万元"),
    ]
    observed: dict[str, Any] = {"lot_count": len(lots)}
    all_ok = True
    for name, lot_field, original_field, calculated_field, expected_unit in measures:
        values = [D(lot["attributes"].get(lot_field)) for lot in lots]
        values = [value for value in values if value is not None]
        if not values:
            continue
        total = sum(values, Decimal("0"))
        expected = D(attrs.get(original_field))
        if expected is None:
            expected = D(attrs.get(calculated_field))
        if name == "shares" and (attrs.get("total_transferred_unit") or attrs.get("calculated_transfer_unit")) not in (None, expected_unit):
            continue
        if name == "percentage" and (attrs.get("total_transferred_unit") or attrs.get("calculated_transfer_unit")) != expected_unit:
            continue
        observed[name] = {"lot_sum": str(total), "event_total": str(expected) if expected is not None else None}
        if expected is not None and abs(total - expected) > Decimal("1e-10"):
            all_ok = False
    return all_ok, observed


def _unit_price_check(row: dict[str, Any]) -> tuple[bool, Any]:
    if row["source_dataset"] != "transfer_lots":
        return True, "not_applicable"
    attrs = row["attributes"]
    shares = D(attrs.get("transferred_shares_original"))
    consideration = D(attrs.get("consideration_original"))
    upstream = D(attrs.get("unit_price_calculated"))
    if shares is None or consideration is None:
        return upstream is None, {"shares": shares is not None, "consideration": consideration is not None, "upstream_unit_price": str(upstream) if upstream is not None else None}
    calculated = consideration * Decimal("10000") / shares
    return upstream is not None and abs(calculated - upstream) <= Decimal("1e-10"), {"calculated": str(calculated), "upstream": str(upstream) if upstream is not None else None}


def _increase_arithmetic(row: dict[str, Any]) -> tuple[bool, Any]:
    if row["source_dataset"] != "increase_events":
        return True, "not_applicable"
    attrs = row["attributes"]
    before = D(attrs.get("capital_before_original"))
    if before is None:
        before = D(attrs.get("capital_before_calculated"))
    change = D(attrs.get("capital_change_original"))
    if change is None:
        change = D(attrs.get("capital_change_calculated"))
    after = D(attrs.get("capital_after_original"))
    if after is None:
        after = D(attrs.get("capital_after_calculated"))
    if before is None or change is None or after is None:
        return True, {"status": "insufficient_explicit_operands", "before": str(before) if before is not None else None, "change": str(change) if change is not None else None, "after": str(after) if after is not None else None}
    difference = before + change - after
    if row["source_record_id"] == "INC-003":
        return difference == Decimal("0.00574"), {"classification": "KNOWN_RETAINED_DISCLOSURE_DIFFERENCE", "difference": str(difference)}
    return abs(difference) <= Decimal("1e-10"), {"difference": str(difference)}


def _no_average_inference(row: dict[str, Any], subs_by_parent: dict[str, list[dict[str, Any]]]) -> tuple[bool, Any]:
    if row["source_dataset"] != "increase_events":
        return True, "not_applicable"
    attrs = row["attributes"]
    note = str(attrs.get("manual_judgment") or "")
    if "不平均分配" not in note and "各自认缴额未披露" not in str(attrs.get("undisclosed_items") or ""):
        return True, "not_applicable"
    offending = []
    for sub in subs_by_parent.get(row["source_record_id"], []):
        a = sub["attributes"]
        for field in ("cash_contribution_original", "subscribed_capital_original", "shares_acquired_original", "allocated_amount_calculated", "shares_calculated"):
            if a.get(field) is not None:
                offending.append({"subscription_id": a.get("subscription_id"), "field": field, "value": a.get(field)})
    return not offending, offending


def _subscription_conversion(row: dict[str, Any]) -> tuple[bool, Any]:
    if row["source_dataset"] != "subscriptions":
        return True, "not_applicable"
    attrs = row["attributes"]
    capital = D(attrs.get("subscribed_capital_original"))
    shares = D(attrs.get("shares_acquired_original"))
    if shares is None:
        shares = D(attrs.get("shares_calculated"))
    if capital is None or shares is None:
        return True, "not_applicable"
    expected = capital * Decimal("10000")
    return expected == shares, {"capital": str(capital), "shares": str(shares), "expected_shares": str(expected)}


def _snapshot_total(attrs: dict[str, Any], holdings: list[dict[str, Any]]) -> tuple[bool, Any]:
    unit = attrs.get("capital_unit")
    values: list[Decimal] = []
    missing: list[str] = []
    for row in holdings:
        a = row["attributes"]
        value = a.get("holding_amount_original") if unit == "万元" else a.get("holding_shares_original")
        if value is None:
            value = a.get("holding_after_calculated")
        decimal = D(value)
        if decimal is None:
            missing.append(str(a.get("snapshot_holding_id")))
        else:
            values.append(decimal)
    total = D(attrs.get("capital_total_original"))
    if total is None:
        total = D(attrs.get("capital_total_calculated"))
    observed = sum(values, Decimal("0"))
    return not missing and total is not None and abs(observed - total) <= Decimal("1e-10"), {"holding_sum": str(observed), "snapshot_total": str(total) if total is not None else None, "missing": missing}


def _snapshot_percentages(holdings: list[dict[str, Any]]) -> tuple[bool, Any]:
    values: list[Decimal] = []
    missing: list[str] = []
    for row in holdings:
        a = row["attributes"]
        value = a.get("holding_percentage_original")
        if value is None:
            value = a.get("holding_percentage_calculated")
        decimal = D(value)
        if decimal is None:
            missing.append(str(a.get("snapshot_holding_id")))
        else:
            values.append(decimal)
    total = sum(values, Decimal("0"))
    return not missing and abs(total - Decimal("100")) <= Decimal("0.02"), {"percentage_sum": str(total), "missing": missing}


def _check(checks: list[dict[str, Any]], rule_id: str, passed: bool, observed: Any, expected: Any, note: str) -> None:
    checks.append({"rule_id": rule_id, "result": "PASS" if passed else "FAIL", "observed": observed, "expected": expected, "note": note})
