from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from . import RULE_SET_VERSION, __version__
from .numeric_rules import numeric_evaluations
from .pevc_rules import pevc_evaluations
from .trace import stable_hash
from .transaction_rules import transaction_evaluations


def run_business_rules(model_9b: dict[str, Any], *, run_id: str = "S09-9C-RUN-001") -> dict[str, Any]:
    _validate_baseline(model_9b)
    numeric = numeric_evaluations(model_9b, run_id)
    transactions = transaction_evaluations(model_9b, run_id)
    pevc = pevc_evaluations(model_9b, run_id)
    evaluations = numeric + transactions + pevc
    rule_results = aggregate_rule_results(evaluations)
    governance = _governance_results(model_9b, evaluations)
    rule_results.extend(governance)
    exceptions = build_exceptions(evaluations)
    failed = [row for row in rule_results if row["result"] == "FAIL"]
    blocking = [row for row in exceptions if row["status"] == "OPEN" and row["blocking_for_9c"]]
    business_view = {
        "numeric_evaluations": numeric,
        "transaction_evaluations": transactions,
        "pevc_evaluations": pevc,
        "rule_results": rule_results,
        "exceptions": exceptions,
    }
    bundle = {
        "metadata": {
            "project": "301563云汉芯城招股说明书工程化学习",
            "stage": 9,
            "substage": "9C",
            "status": "PENDING_USER_ACCEPTANCE",
            "scope": "数值、增资/转让/快照及PE/VC投资路径确定性业务规则自动运行",
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "run_id": run_id,
            "primary_fact_source": model_9b["metadata"].get("primary_fact_source"),
            "input_baseline_substage": model_9b["metadata"].get("substage"),
            "input_baseline_status": model_9b["metadata"].get("status"),
            "result": "READY_FOR_USER_ACCEPTANCE" if not failed and not blocking else "BLOCKED",
            "automation_boundary": "只复算和复现已验收确定性业务规则；不新增事实、不模糊合并主体、不升级候选分类、不推算未披露信息",
        },
        "input_baseline": {
            "substage": "9B",
            "program_version": model_9b["metadata"].get("program_version"),
            "rule_set_version": model_9b["metadata"].get("rule_set_version"),
            "model_sha256": stable_hash(model_9b),
            "business_output_hash": model_9b.get("run_manifest", {}).get("business_output_hash"),
        },
        "numeric_evaluations": numeric,
        "transaction_evaluations": transactions,
        "pevc_evaluations": pevc,
        "rule_results": rule_results,
        "exceptions": exceptions,
        "review_actions": [],
        "acceptance_checks": acceptance_checks(model_9b, evaluations, rule_results, exceptions),
        "run_manifest": {
            "run_id": run_id,
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "evaluation_counts": {
                "numeric": len(numeric),
                "transaction_and_snapshot": len(transactions),
                "pevc": len(pevc),
                "total": len(evaluations),
            },
            "business_output_hash": stable_hash(business_view),
        },
    }
    return bundle


def aggregate_rule_results(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for evaluation in evaluations:
        for check in evaluation["checks"]:
            grouped[check["rule_id"]].append((evaluation, check))
    results = []
    for rule_id in sorted(grouped):
        rows = grouped[rule_id]
        failures = [evaluation["object_id"] for evaluation, check in rows if check["result"] == "FAIL"]
        applicable = [(evaluation, check) for evaluation, check in rows if not str(check.get("observed")).startswith("not_applicable") and check.get("observed") != "evaluated_on_path_edges" and check.get("observed") != "evaluated_on_snapshot_records" and check.get("observed") != "evaluated_on_investment_records" and check.get("observed") != "evaluated_on_final_identification"]
        results.append({
            "rule_id": rule_id,
            "result": "FAIL" if failures else "PASS",
            "evaluated_object_count": len(rows),
            "applicable_object_count": len(applicable),
            "failed_object_ids": failures,
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "review_status": "AUTO_PASS_PENDING_9C_ACCEPTANCE" if not failures else "PENDING_9D_REVIEW",
        })
    return results


def _governance_results(model_9b: dict[str, Any], evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace_failures = [row["evaluation_id"] for row in evaluations if not row.get("event_ids") or not row.get("evidence_ids") or not row.get("pdf_pages") or not row.get("printed_pages") or not row.get("original_excerpts")]
    source_entity_ids = {row["entity_id"] for row in model_9b["canonical_entities"]}
    output_entity_ids = set()
    for row in evaluations:
        if row["object_type"].startswith("PEVC"):
            output_entity_ids.update(_entity_ids_from_eval(row, model_9b))
    extra_entities = sorted(output_entity_ids - source_entity_ids)
    baseline_ok = model_9b["metadata"].get("substage") == "9B" and model_9b["metadata"].get("status") == "FINAL_APPROVED"
    return [
        _global_result("S09-G001", not trace_failures, trace_failures, "所有业务自动化结果保留事件、证据、双页码和原文"),
        _global_result("S09-G002", not extra_entities, extra_entities, "未创建上游不存在的新主体ID"),
        _global_result("S09-G003", baseline_ok, {"substage": model_9b["metadata"].get("substage"), "status": model_9b["metadata"].get("status")}, "仅在正式验收9B基线上运行"),
    ]


def _entity_ids_from_eval(evaluation: dict[str, Any], model_9b: dict[str, Any]) -> set[str]:
    object_id = evaluation["object_id"]
    if evaluation["object_type"] == "PEVC_FINAL_IDENTIFICATION":
        row = next((x for x in model_9b["pevc_results"]["final_identification"] if x["final_record_id"] == object_id), None)
        return {row["entity_id"]} if row else set()
    if evaluation["object_type"] == "PEVC_INVESTMENT":
        row = next((x for x in model_9b["pevc_results"]["investment_records"] if x["attributes"]["investment_record_id"] == object_id), None)
        if not row:
            return set()
        attrs = row["attributes"]
        return {x for x in (attrs.get("investor_entity_id"), attrs.get("counterparty_entity_id")) if x}
    if evaluation["object_type"] == "PEVC_PATH_EDGE":
        row = next((x for x in model_9b["pevc_results"]["path_edges"] if x["attributes"]["edge_id"] == object_id), None)
        if not row:
            return set()
        attrs = row["attributes"]
        return {x for x in (attrs.get("upstream_entity_id"), attrs.get("downstream_entity_id")) if x}
    return set()


def _global_result(rule_id: str, passed: bool, observed: Any, note: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "result": "PASS" if passed else "FAIL",
        "evaluated_object_count": 1,
        "applicable_object_count": 1,
        "failed_object_ids": [] if passed else ["GLOBAL"],
        "observed": observed,
        "note": note,
        "program_version": __version__,
        "rule_set_version": RULE_SET_VERSION,
        "review_status": "AUTO_PASS_PENDING_9C_ACCEPTANCE" if passed else "PENDING_9D_REVIEW",
    }


def build_exceptions(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exceptions = []
    counter = 1
    for evaluation in evaluations:
        failed = [check for check in evaluation["checks"] if check["result"] == "FAIL"]
        if not failed:
            continue
        exceptions.append({
            "exception_id": f"S09-9C-EXC-{counter:03d}",
            "exception_type": "BUSINESS_RULE_FAILURE",
            "severity": "HIGH",
            "blocking_for_9c": True,
            "object_type": evaluation["object_type"],
            "object_id": evaluation["object_id"],
            "event_ids": evaluation["event_ids"],
            "evidence_ids": evaluation["evidence_ids"],
            "pdf_pages": evaluation["pdf_pages"],
            "printed_pages": evaluation["printed_pages"],
            "original_excerpts": evaluation["original_excerpts"],
            "triggered_rule_ids": [check["rule_id"] for check in failed],
            "observed": [{"rule_id": check["rule_id"], "observed": check.get("observed")} for check in failed],
            "expected": [{"rule_id": check["rule_id"], "expected": check.get("expected")} for check in failed],
            "recommended_action": "进入9D人工复核队列；不得自动覆盖上游事实。",
            "status": "OPEN",
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
        })
        counter += 1
    return exceptions


def acceptance_checks(model_9b: dict[str, Any], evaluations: list[dict[str, Any]], rules: list[dict[str, Any]], exceptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["object_type"] for row in evaluations)
    checks = [
        ("S09-9C-ACC-001", "9B正式验收基线", model_9b["metadata"].get("status") == "FINAL_APPROVED", model_9b["metadata"].get("status")),
        ("S09-9C-ACC-002", "55项数值校验全部复算", counts["NUMERIC_VALIDATION"] == 55, counts["NUMERIC_VALIDATION"]),
        ("S09-9C-ACC-003", "63条交易及15个快照均执行规则", counts["TRANSACTION"] == 63 and counts["EQUITY_SNAPSHOT"] == 15, {"transactions": counts["TRANSACTION"], "snapshots": counts["EQUITY_SNAPSHOT"]}),
        ("S09-9C-ACC-004", "PEVC 33+65+45记录全部执行规则", counts["PEVC_INVESTMENT"] == 33 and counts["PEVC_PATH_EDGE"] == 65 and counts["PEVC_FINAL_IDENTIFICATION"] == 45, {"investments": counts["PEVC_INVESTMENT"], "edges": counts["PEVC_PATH_EDGE"], "final": counts["PEVC_FINAL_IDENTIFICATION"]}),
        ("S09-9C-ACC-005", "所有规则通过", not [row for row in rules if row["result"] == "FAIL"], [row["rule_id"] for row in rules if row["result"] == "FAIL"]),
        ("S09-9C-ACC-006", "无开放阻断异常", not [row for row in exceptions if row["status"] == "OPEN" and row["blocking_for_9c"]], len(exceptions)),
        ("S09-9C-ACC-007", "未披露值不推算", next(row for row in rules if row["rule_id"] == "S09-P007")["result"] == "PASS", next(row for row in rules if row["rule_id"] == "S09-P007")["result"]),
        ("S09-9C-ACC-008", "证据链完整", next(row for row in rules if row["rule_id"] == "S09-G001")["result"] == "PASS", next(row for row in rules if row["rule_id"] == "S09-G001")["result"]),
    ]
    return [{"check_id": cid, "check_item": item, "result": "PASS" if passed else "FAIL", "observed": observed} for cid, item, passed, observed in checks]


def _validate_baseline(model: dict[str, Any]) -> None:
    if model.get("metadata", {}).get("substage") != "9B":
        raise ValueError("9C requires a 9B unified model")
    if model.get("metadata", {}).get("status") != "FINAL_APPROVED":
        raise ValueError("9C requires the formally approved 9B baseline")
