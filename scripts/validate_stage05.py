#!/usr/bin/env python3
"""Validate Stage 05 JSON exports using deterministic project rules."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks: list[dict[str, Any]], check_id: str, description: str, passed: bool, details: Any) -> None:
    checks.append({
        "check_id": check_id,
        "description": description,
        "status": "passed" if passed else "failed",
        "details": details,
    })


def validate(data_dir: Path) -> dict[str, Any]:
    timeline = load(data_dir / "equity_timeline.json")
    time_nodes = load(data_dir / "time_nodes.json")
    calculations = load(data_dir / "calculations.json")
    exclusions = load(data_dir / "exclusions.json")
    auxiliaries = load(data_dir / "auxiliaries.json")
    review_items = load(data_dir / "review_items.json")
    acceptance = load(data_dir / "acceptance_checks.json")

    checks: list[dict[str, Any]] = []

    timeline_ids = [r["timeline_id"] for r in timeline]
    event_ids = [r["event_id"] for r in timeline]
    add_check(checks, "S05-001", "主时间线事件数为17", len(timeline) == 17, len(timeline))
    add_check(checks, "S05-002", "timeline_id唯一", len(timeline_ids) == len(set(timeline_ids)), timeline_ids)
    add_check(checks, "S05-003", "event_id唯一", len(event_ids) == len(set(event_ids)), event_ids)
    add_check(
        checks, "S05-004", "展示顺序连续为1至17",
        [r["display_sequence"] for r in timeline] == list(range(1, 18)),
        [r["display_sequence"] for r in timeline],
    )

    parent_containers = {"CE-002", "CE-010", "CE-013"}
    bad_parents = sorted(parent_containers.intersection(event_ids))
    add_check(checks, "S05-005", "父级复合事件未重复进入主时间线", not bad_parents, bad_parents)

    evidence_missing = [
        r["timeline_id"] for r in timeline
        if not r.get("evidence_ids") or not r.get("pdf_pages") or not r.get("printed_pages")
    ]
    add_check(checks, "S05-006", "每个时间线事件均保留证据及双页码", not evidence_missing, evidence_missing)

    non_approved = [
        r["timeline_id"] for r in timeline if r.get("review_status") != "已验收通过"
    ]
    add_check(checks, "S05-007", "所有时间线事件均已验收通过", not non_approved, non_approved)

    manual_review = [
        r["timeline_id"] for r in timeline if r.get("needs_manual_review") is True
    ]
    add_check(checks, "S05-008", "阶段五无未关闭人工复核行", not manual_review, manual_review)

    node_ids = [r["time_node_id"] for r in time_nodes]
    add_check(checks, "S05-009", "时间节点数为43", len(time_nodes) == 43, len(time_nodes))
    add_check(checks, "S05-010", "time_node_id唯一", len(node_ids) == len(set(node_ids)), node_ids)

    referenced_nodes = {
        node_id for r in timeline for node_id in r.get("time_node_ids", [])
    }
    missing_nodes = sorted(referenced_nodes.difference(node_ids))
    add_check(checks, "S05-011", "主时间线引用的时间节点均存在", not missing_nodes, missing_nodes)

    calculation_ids = [r["calculation_id"] for r in calculations]
    add_check(checks, "S05-012", "计算登记数为16", len(calculations) == 16, len(calculations))
    add_check(checks, "S05-013", "calculation_id唯一", len(calculation_ids) == len(set(calculation_ids)), calculation_ids)

    referenced_calcs = {
        calc_id for r in timeline for calc_id in r.get("calculation_ids", [])
    }
    missing_calcs = sorted(referenced_calcs.difference(calculation_ids))
    add_check(checks, "S05-014", "主时间线引用的计算登记均存在", not missing_calcs, missing_calcs)

    add_check(checks, "S05-015", "排除项数为9", len(exclusions) == 9, len(exclusions))
    add_check(checks, "S05-016", "辅助非事件数为2", len(auxiliaries) == 2, len(auxiliaries))
    add_check(checks, "S05-017", "后续复核事项数为3", len(review_items) == 3, len(review_items))

    rv001 = next((r for r in review_items if r.get("review_item_id") == "RV-001"), None)
    add_check(checks, "S05-018", "CE-005差异事项RV-001已保留", rv001 is not None, rv001)

    cal005 = next((r for r in calculations if r.get("calculation_id") == "CAL-005"), None)
    variance_ok = cal005 is not None and abs(float(cal005["variance"]) - 0.00574) < 1e-12
    add_check(checks, "S05-019", "CAL-005差异为0.00574万元", variance_ok, cal005)

    add_check(checks, "S05-020", "验收清单事件数为17", len(acceptance) == 17, len(acceptance))
    bad_acceptance = [
        r["timeline_id"] for r in acceptance if r.get("overall_check_status") != "已验收通过"
    ]
    add_check(checks, "S05-021", "验收清单全部通过", not bad_acceptance, bad_acceptance)

    failed = [c for c in checks if c["status"] == "failed"]
    return {
        "stage": 5,
        "stage_name": "股本变化时间线",
        "validation_status": "passed" if not failed else "failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "checks_total": len(checks),
            "checks_passed": len(checks) - len(failed),
            "checks_failed": len(failed),
        },
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    report = validate(args.data_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    raise SystemExit(0 if report["validation_status"] == "passed" else 1)


if __name__ == "__main__":
    main()
