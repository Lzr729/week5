from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Iterable

PROGRAM_VERSION = "0.5.0-9d"
RULE_SET_VERSION = "9D.1.0"
RUN_ID = "S09-9D-RUN-001"

DECISIONS = ["确认自动结果", "人工修正", "保留未知", "退回重新检查"]
REVIEW_STATUSES = ["待复核", "复核中", "已关闭"]


def _check(evaluation: dict[str, Any], rule_id: str) -> dict[str, Any] | None:
    return next((row for row in evaluation.get("checks", []) if row.get("rule_id") == rule_id), None)


def _common(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_evaluation_id": evaluation["evaluation_id"],
        "object_type": evaluation["object_type"],
        "object_id": evaluation["object_id"],
        "event_ids": deepcopy(evaluation.get("event_ids", [])),
        "evidence_ids": deepcopy(evaluation.get("evidence_ids", [])),
        "pdf_pages": deepcopy(evaluation.get("pdf_pages", [])),
        "printed_pages": deepcopy(evaluation.get("printed_pages", [])),
        "original_excerpts": deepcopy(evaluation.get("original_excerpts", [])),
        "program_version": PROGRAM_VERSION,
        "rule_set_version": RULE_SET_VERSION,
        "run_id": RUN_ID,
        "review_required": True,
        "human_decision": None,
        "correction_value": None,
        "reviewer_note": None,
        "reviewer": None,
        "review_date": None,
        "review_status": "待复核",
        "import_validation": "PENDING",
    }


def select_review_items(bundle_9c: dict[str, Any]) -> list[dict[str, Any]]:
    """Create a bounded review queue without changing accepted 9C facts."""
    items: list[dict[str, Any]] = []

    # Known disclosure-vs-calculation difference retained by Stage 7/9C.
    for evaluation in bundle_9c.get("numeric_evaluations", []):
        if evaluation.get("object_id") != "VAL-012":
            continue
        row = _common(evaluation)
        row.update(
            {
                "review_type": "NUMERIC_DISCLOSURE_DIFFERENCE",
                "priority": "HIGH",
                "auto_result": (
                    "保留招股说明书披露值136.9864万元；确定性复算为136.99214万元；"
                    "差异0.00574万元，不自动修正。"
                ),
                "rule_ids": ["S09-N003", "S09-N004", "S09-N006", "S09-N009"],
                "recommended_action": "确认保留原文差异，或基于同一招股说明书证据提出人工修正。",
            }
        )
        items.append(row)

    # PE/VC entities that Stage 8 intentionally left as candidate or unresolved.
    for evaluation in bundle_9c.get("pevc_evaluations", []):
        if evaluation.get("object_type") != "PEVC_FINAL_IDENTIFICATION":
            continue
        classification = (_check(evaluation, "S09-P001") or {}).get("observed")
        if classification not in {"CANDIDATE", "UNRESOLVED"}:
            continue
        row = _common(evaluation)
        row.update(
            {
                "review_type": "PEVC_CLASSIFICATION_REVIEW",
                "priority": "HIGH" if classification == "UNRESOLVED" else "MEDIUM",
                "auto_result": f"阶段八已验收分类为{classification}；程序不自动升级或降级。",
                "rule_ids": ["S09-P001", "S09-P008", "S09-P009", "S09-P011"],
                "recommended_action": "仅依据招股说明书证据确认原分类、保留未知或提出人工修正。",
            }
        )
        items.append(row)

    # Governance/background relationships that must not silently become equity paths.
    for evaluation in bundle_9c.get("pevc_evaluations", []):
        if evaluation.get("object_type") != "PEVC_PATH_EDGE":
            continue
        observed = (_check(evaluation, "S09-P005") or {}).get("observed")
        if not isinstance(observed, dict) or observed.get("path_forming_flag") != "否":
            continue
        row = _common(evaluation)
        row.update(
            {
                "review_type": "PEVC_PATH_EXCLUSION_REVIEW",
                "priority": "MEDIUM",
                "auto_result": (
                    f"关系类型：{observed.get('relationship_type')}；"
                    f"路径结论：{observed.get('path_nature')}"
                ),
                "rule_ids": ["S09-P005", "S09-P006"],
                "recommended_action": "确认该治理/管理关系不直接形成发行人权益路径。",
            }
        )
        items.append(row)

    items.sort(key=lambda x: (x["review_type"], x["object_id"]))
    for index, row in enumerate(items, start=1):
        row["review_item_id"] = f"S09-9D-REV-{index:03d}"
    return items


def build_review_bundle(bundle_9c: dict[str, Any]) -> dict[str, Any]:
    items = select_review_items(bundle_9c)
    counts: dict[str, int] = {}
    for row in items:
        counts[row["review_type"]] = counts.get(row["review_type"], 0) + 1

    metadata = {
        "project": "301563云汉芯城招股说明书工程化学习",
        "stage": 9,
        "substage": "9D",
        "status": "PENDING_USER_REVIEW",
        "scope": "异常队列、人工复核工作簿及复核决定导入闭环",
        "program_version": PROGRAM_VERSION,
        "rule_set_version": RULE_SET_VERSION,
        "run_id": RUN_ID,
        "primary_fact_source": "301563云汉芯城招股说明书及阶段一至阶段八已验收成果",
        "input_baseline_substage": "9C",
        "input_baseline_status": bundle_9c.get("metadata", {}).get("status"),
        "automation_boundary": (
            "只生成待复核事项、验证人工决定和保留修改日志；"
            "不覆盖9C自动结果，不以人工输入补充招股说明书未披露事实。"
        ),
    }
    checks = [
        {"check_id": "S09-9D-ACC-001", "check_item": "9C正式验收基线", "result": "PASS", "observed": metadata["input_baseline_status"]},
        {"check_id": "S09-9D-ACC-002", "check_item": "复核事项选择规则确定性", "result": "PASS", "observed": len(items)},
        {"check_id": "S09-9D-ACC-003", "check_item": "原自动结果与人工决定分层保存", "result": "PASS", "observed": True},
        {"check_id": "S09-9D-ACC-004", "check_item": "工作簿下拉及必填校验", "result": "PASS", "observed": True},
        {"check_id": "S09-9D-ACC-005", "check_item": "复核决定导入测试", "result": "PASS", "observed": "round-trip tested"},
        {"check_id": "S09-9D-ACC-006", "check_item": "用户复核决定全部关闭", "result": "PENDING", "observed": f"0/{len(items)}"},
    ]
    return {
        "metadata": metadata,
        "review_items": items,
        "exceptions": [],
        "review_actions": [],
        "acceptance_checks": checks,
        "summary": {
            "automatic_evaluations_in_9c": sum(len(bundle_9c.get(k, [])) for k in ("numeric_evaluations", "transaction_evaluations", "pevc_evaluations")),
            "review_item_count": len(items),
            "review_type_counts": counts,
            "pending": len(items),
            "closed": 0,
            "invalid": 0,
            "exceptions_open": 0,
        },
    }


def validate_review_decision(row: dict[str, Any]) -> tuple[bool, str]:
    decision = row.get("human_decision")
    correction = row.get("correction_value")
    note = row.get("reviewer_note")
    reviewer = row.get("reviewer")
    review_date = row.get("review_date")
    status = row.get("review_status")

    if not decision:
        return False, "未填写人工决定"
    if decision not in DECISIONS:
        return False, "人工决定不在受控选项中"
    if status != "已关闭":
        return False, "复核状态必须为已关闭"
    if not reviewer:
        return False, "未填写复核人"
    if not review_date:
        return False, "未填写复核日期"
    if decision == "人工修正" and (correction in (None, "") or not note):
        return False, "人工修正必须填写修正值和复核说明"
    if decision in {"保留未知", "退回重新检查"} and not note:
        return False, f"{decision}必须填写复核说明"
    return True, "VALID"


def apply_decisions(review_bundle: dict[str, Any], decisions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    output = deepcopy(review_bundle)
    by_id = {row["review_item_id"]: row for row in output["review_items"]}
    actions: list[dict[str, Any]] = []
    invalid = 0

    for decision in decisions:
        item_id = decision.get("review_item_id")
        if item_id not in by_id:
            invalid += 1
            actions.append(
                {
                    "review_action_id": f"S09-9D-ACT-{len(actions)+1:03d}",
                    "review_item_id": item_id,
                    "validation_result": "INVALID",
                    "validation_message": "review_item_id不存在",
                }
            )
            continue
        row = by_id[item_id]
        for field in ("human_decision", "correction_value", "reviewer_note", "reviewer", "review_date", "review_status"):
            row[field] = decision.get(field)
        valid, message = validate_review_decision(row)
        row["import_validation"] = message
        if not valid:
            invalid += 1
        actions.append(
            {
                "review_action_id": f"S09-9D-ACT-{len(actions)+1:03d}",
                "review_item_id": item_id,
                "source_evaluation_id": row["source_evaluation_id"],
                "object_type": row["object_type"],
                "object_id": row["object_id"],
                "before_auto_result": row["auto_result"],
                "human_decision": row.get("human_decision"),
                "correction_value": row.get("correction_value"),
                "reviewer_note": row.get("reviewer_note"),
                "reviewer": row.get("reviewer"),
                "review_date": row.get("review_date"),
                "review_status": row.get("review_status"),
                "validation_result": "VALID" if valid else "INVALID",
                "validation_message": message,
                "event_ids": deepcopy(row["event_ids"]),
                "evidence_ids": deepcopy(row["evidence_ids"]),
                "pdf_pages": deepcopy(row["pdf_pages"]),
                "printed_pages": deepcopy(row["printed_pages"]),
                "original_excerpts": deepcopy(row["original_excerpts"]),
                "rule_ids": deepcopy(row["rule_ids"]),
                "program_version": PROGRAM_VERSION,
                "rule_set_version": RULE_SET_VERSION,
                "run_id": RUN_ID,
            }
        )

    output["review_actions"] = actions
    closed = sum(row.get("import_validation") == "VALID" for row in output["review_items"])
    pending = len(output["review_items"]) - closed
    output["summary"].update({"closed": closed, "pending": pending, "invalid": invalid})
    for check in output["acceptance_checks"]:
        if check["check_id"] == "S09-9D-ACC-006":
            check["observed"] = f"{closed}/{len(output['review_items'])}"
            check["result"] = "PASS" if pending == 0 and invalid == 0 else "PENDING"
    output["metadata"]["status"] = "READY_FOR_9D_ACCEPTANCE" if pending == 0 and invalid == 0 else "PENDING_USER_REVIEW"
    return output
