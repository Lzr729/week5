from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import RULE_SET_VERSION, __version__

RUN_ID = "S09-9E-RUN-001"


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(check_id: str, item: str, passed: bool, observed: Any, note: str | None = None) -> dict[str, Any]:
    row = {"check_id": check_id, "check_item": item, "result": "PASS" if passed else "FAIL", "observed": observed}
    if note:
        row["note"] = note
    return row


def build_final_bundle(
    model_9b: dict[str, Any],
    bundle_9c: dict[str, Any],
    bundle_9d: dict[str, Any],
    *,
    final_workbook_sha256: str,
    tests_passed: int,
    tests_failed: int = 0,
) -> dict[str, Any]:
    """Combine approved 9B/9C/9D results without rewriting their facts."""
    if model_9b.get("metadata", {}).get("status") != "FINAL_APPROVED":
        raise ValueError("9E requires FINAL_APPROVED 9B")
    if bundle_9c.get("metadata", {}).get("status") != "FINAL_APPROVED":
        raise ValueError("9E requires FINAL_APPROVED 9C")
    if bundle_9d.get("metadata", {}).get("status") != "FINAL_APPROVED":
        raise ValueError("9E requires FINAL_APPROVED 9D")

    evaluations = (
        deepcopy(bundle_9c["numeric_evaluations"])
        + deepcopy(bundle_9c["transaction_evaluations"])
        + deepcopy(bundle_9c["pevc_evaluations"])
    )
    investment_records = model_9b["pevc_results"]["investment_records"]
    path_edges = model_9b["pevc_results"]["path_edges"]
    not_disclosed = [row for row in investment_records if row["attributes"].get("value_type") == "NOT_DISCLOSED"]
    gp_edges = [
        row for row in path_edges
        if row["attributes"].get("relationship_type") in {"GENERAL_PARTNER", "GENERAL_PARTNER_EXECUTIVE"}
    ]
    trace_complete = [
        row for row in evaluations
        if all(row.get(field) for field in ("event_ids", "evidence_ids", "pdf_pages", "printed_pages", "original_excerpts"))
    ]
    open_exceptions = [
        row for row in model_9b.get("exceptions", []) + bundle_9c.get("exceptions", []) + bundle_9d.get("exceptions", [])
        if row.get("status") == "OPEN"
    ]
    valid_actions = [row for row in bundle_9d["review_actions"] if row.get("validation_result") == "VALID"]
    by_validation = {row["validation_id"]: row for row in model_9b["numeric_validations"]}

    checks = [
        _check("S09-9E-ACC-001", "9B、9C、9D均为正式验收基线", True, {"9B": "FINAL_APPROVED", "9C": "FINAL_APPROVED", "9D": "FINAL_APPROVED"}),
        _check("S09-9E-ACC-002", "阶段一至八来源记录完整接入", len(model_9b["source_records"]) == 1648, len(model_9b["source_records"])),
        _check("S09-9E-ACC-003", "统一模型核心对象数量回归", all((len(model_9b["canonical_events"]) == 26, len(model_9b["canonical_entities"]) == 45, len(model_9b["canonical_evidence"]) == 126)), {"events": len(model_9b["canonical_events"]), "entities": len(model_9b["canonical_entities"]), "evidence": len(model_9b["canonical_evidence"])}),
        _check("S09-9E-ACC-004", "276条业务自动评价完整", len(evaluations) == 276, len(evaluations)),
        _check("S09-9E-ACC-005", "35条业务规则全部通过", len(bundle_9c["rule_results"]) == 35 and all(row["result"] == "PASS" for row in bundle_9c["rule_results"]), len(bundle_9c["rule_results"])),
        _check("S09-9E-ACC-006", "无开放异常", not open_exceptions, len(open_exceptions)),
        _check("S09-9E-ACC-007", "17条人工复核决定全部有效关闭", len(valid_actions) == 17 and bundle_9d["summary"]["pending"] == 0 and bundle_9d["summary"]["invalid"] == 0, {"valid": len(valid_actions), "pending": bundle_9d["summary"]["pending"], "invalid": bundle_9d["summary"]["invalid"]}),
        _check("S09-9E-ACC-008", "CE-005披露差异保留", by_validation["VAL-012"]["result"].get("absolute_difference_excel") == 0.00574, by_validation["VAL-012"]["result"].get("absolute_difference_excel")),
        _check("S09-9E-ACC-009", "CE-013转让股数合计回归", by_validation["VAL-044"]["result"].get("calculated_value_excel") == 1659535, by_validation["VAL-044"]["result"].get("calculated_value_excel")),
        _check("S09-9E-ACC-010", "CE-013转让价款合计回归", by_validation["VAL-045"]["result"].get("calculated_value_excel") == 8563.19, by_validation["VAL-045"]["result"].get("calculated_value_excel")),
        _check("S09-9E-ACC-011", "未披露投资值保持空值", len(not_disclosed) == 13 and all(row["attributes"].get("shares_or_capital_value") is None and row["attributes"].get("cash_or_consideration_value") is None for row in not_disclosed), len(not_disclosed)),
        _check("S09-9E-ACC-012", "GP及执行事务合伙人关系不形成权益路径", len(gp_edges) == 8 and all(row["attributes"].get("path_forming_flag") == "否" for row in gp_edges), len(gp_edges)),
        _check("S09-9E-ACC-013", "全部自动评价保留完整证据链", len(trace_complete) == len(evaluations), f"{len(trace_complete)}/{len(evaluations)}"),
        _check("S09-9E-ACC-014", "名称标准化仅使用已验收映射", all(row.get("mapping_method") == "UPSTREAM_APPROVED_ID_AND_NAME_MAPPING_ONLY" for row in model_9b["canonical_entities"]), len(model_9b["canonical_entities"])),
        _check("S09-9E-ACC-015", "最终工作簿哈希已冻结", len(final_workbook_sha256) == 64, final_workbook_sha256),
        _check("S09-9E-ACC-016", "自动测试全部通过", tests_failed == 0 and tests_passed > 0, {"passed": tests_passed, "failed": tests_failed}),
    ]

    final = {
        "metadata": {
            "project": "301563云汉芯城招股说明书工程化学习",
            "stage": 9,
            "substage": "9E",
            "status": "FINAL_APPROVED" if all(row["result"] == "PASS" for row in checks) else "BLOCKED",
            "scope": "稳定人工研究步骤自动化的最终回归、验收和发布",
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "run_id": RUN_ID,
            "primary_fact_source": "301563_云汉芯城_IPO招股说明书.pdf",
            "automation_boundary": "不补充未披露事实；不模糊合并主体；不把治理关系自动认定为权益路径；自动结果与人工决定分层保存。",
            "upstream_status": {"9A": "FINAL_APPROVED", "9B": "FINAL_APPROVED", "9C": "FINAL_APPROVED", "9D": "FINAL_APPROVED"},
        },
        "input_artifacts": deepcopy(model_9b["input_artifacts"]),
        "source_records": deepcopy(model_9b["source_records"]),
        "source_crosswalks": deepcopy(model_9b["source_crosswalks"]),
        "document_context": deepcopy(model_9b["document_context"]),
        "candidate_event_register": deepcopy(model_9b["candidate_event_register"]),
        "event_annotations": deepcopy(model_9b["event_annotations"]),
        "equity_timeline": deepcopy(model_9b["equity_timeline"]),
        "canonical_events": deepcopy(model_9b["canonical_events"]),
        "canonical_entities": deepcopy(model_9b["canonical_entities"]),
        "canonical_evidence": deepcopy(model_9b["canonical_evidence"]),
        "normalized_transactions": deepcopy(model_9b["normalized_transactions"]),
        "normalized_snapshots": deepcopy(model_9b["normalized_snapshots"]),
        "numeric_source_values": deepcopy(model_9b["numeric_source_values"]),
        "numeric_validations": deepcopy(model_9b["numeric_validations"]),
        "pevc_results": deepcopy(model_9b["pevc_results"]),
        "automation_results": {
            "numeric_evaluations": deepcopy(bundle_9c["numeric_evaluations"]),
            "transaction_evaluations": deepcopy(bundle_9c["transaction_evaluations"]),
            "pevc_evaluations": deepcopy(bundle_9c["pevc_evaluations"]),
            "rule_results": deepcopy(bundle_9c["rule_results"]),
            "business_output_hash": bundle_9c["run_manifest"]["business_output_hash"],
        },
        "review_items": deepcopy(bundle_9d["review_items"]),
        "review_actions": deepcopy(bundle_9d["review_actions"]),
        "exceptions": deepcopy(model_9b.get("exceptions", [])) + deepcopy(bundle_9c.get("exceptions", [])) + deepcopy(bundle_9d.get("exceptions", [])),
        "acceptance_checks": checks,
        "run_manifest": {
            "run_id": RUN_ID,
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "upstream_hashes": {
                "9b_model": stable_hash(model_9b),
                "9c_bundle": stable_hash(bundle_9c),
                "9d_bundle": stable_hash(bundle_9d),
            },
            "final_workbook_sha256": final_workbook_sha256,
            "counts": {
                "source_records": len(model_9b["source_records"]),
                "events": len(model_9b["canonical_events"]),
                "entities": len(model_9b["canonical_entities"]),
                "evidence": len(model_9b["canonical_evidence"]),
                "automatic_evaluations": len(evaluations),
                "review_actions": len(bundle_9d["review_actions"]),
            },
        },
    }
    final["run_manifest"]["final_business_hash"] = stable_hash({
        "automation_results": final["automation_results"],
        "review_actions": final["review_actions"],
        "acceptance_checks": final["acceptance_checks"],
    })
    return final


def validate_final_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic validation failures; an empty list means PASS."""
    failures: list[dict[str, Any]] = []
    required = [
        "metadata", "input_artifacts", "source_records", "source_crosswalks", "canonical_events",
        "canonical_entities", "canonical_evidence", "normalized_transactions", "normalized_snapshots",
        "numeric_validations", "pevc_results", "automation_results", "review_items", "review_actions",
        "exceptions", "acceptance_checks", "run_manifest",
    ]
    for key in required:
        if key not in bundle:
            failures.append({"rule_id": "S09-A001", "message": f"缺少顶层字段: {key}"})
    if failures:
        return failures
    if bundle["metadata"].get("status") != "FINAL_APPROVED":
        failures.append({"rule_id": "S09-A002", "message": "最终状态不是FINAL_APPROVED"})
    if any(row.get("result") != "PASS" for row in bundle["acceptance_checks"]):
        failures.append({"rule_id": "S09-A003", "message": "存在未通过的验收检查"})
    if any(row.get("status") == "OPEN" for row in bundle["exceptions"]):
        failures.append({"rule_id": "S09-A004", "message": "存在开放异常"})
    if len(bundle["review_actions"]) != 17 or any(row.get("validation_result") != "VALID" for row in bundle["review_actions"]):
        failures.append({"rule_id": "S09-A005", "message": "人工复核动作未全部有效关闭"})

    source_ids = [row.get("source_pointer") for row in bundle["source_records"]]
    if len(source_ids) != len(set(source_ids)):
        failures.append({"rule_id": "S09-S001", "message": "source_pointer存在重复"})

    investment_records = bundle["pevc_results"].get("investment_records", [])
    for row in investment_records:
        attrs = row.get("attributes", {})
        if attrs.get("value_type") == "NOT_DISCLOSED" and (
            attrs.get("shares_or_capital_value") is not None or attrs.get("cash_or_consideration_value") is not None
        ):
            failures.append({"rule_id": "S09-G001", "message": f"未披露投资值被填充: {attrs.get('investment_record_id')}"})
            break

    for row in bundle["pevc_results"].get("path_edges", []):
        attrs = row.get("attributes", {})
        if attrs.get("relationship_type") in {"GENERAL_PARTNER", "GENERAL_PARTNER_EXECUTIVE"} and attrs.get("path_forming_flag") != "否":
            failures.append({"rule_id": "S09-G002", "message": f"治理关系被错误标记为权益路径: {attrs.get('edge_id')}"})
            break

    evaluations = []
    automation = bundle.get("automation_results", {})
    for key in ("numeric_evaluations", "transaction_evaluations", "pevc_evaluations"):
        evaluations.extend(automation.get(key, []))
    for row in evaluations:
        if not all(row.get(field) for field in ("event_ids", "evidence_ids", "pdf_pages", "printed_pages", "original_excerpts")):
            failures.append({"rule_id": "S09-E001", "message": f"证据链不完整: {row.get('evaluation_id')}"})
            break
    return failures
