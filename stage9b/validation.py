from __future__ import annotations

from typing import Any

from . import RULE_SET_VERSION, __version__
from .adapters import CE_EVENT_RE, AdaptedStage, normalize_reference_tokens, source_record_id
from .model import stable_hash


def validate_model(model: dict[str, Any], stages: dict[int, AdaptedStage]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    events = model["canonical_events"]
    entities = model["canonical_entities"]
    evidence = model["canonical_evidence"]
    transactions = model["normalized_transactions"]
    snapshots = model["normalized_snapshots"]
    numeric_sources = model["numeric_source_values"]
    validations = model["numeric_validations"]
    pevc = model["pevc_results"]
    crosswalks = model["source_crosswalks"]
    source_records = model["source_records"]

    event_ids = {row["event_id"] for row in events}
    _append(results, "S09-B001", "canonical_events", _unique_nonempty(events, "event_id"), len(events), "统一事件ID非空且唯一")
    missing_event_refs = sorted(_referenced_ce_events(model) - event_ids)
    _append(results, "S09-B002", "event_references", not missing_event_refs, missing_event_refs, "所有CE事件引用均存在于统一事件主表")

    entity_ids = {row["entity_id"] for row in entities}
    _append(results, "S09-B003", "canonical_entities", _unique_nonempty(entities, "entity_id"), len(entities), "统一主体ID非空且唯一")
    stage6_parties = {str(row["party_id"]) for row in stages[6].datasets["parties"]}
    mapped_parties = {str(row["upstream_party_id"]) for row in entities if row.get("upstream_party_id")}
    missing_parties = sorted(stage6_parties - mapped_parties)
    _append(results, "S09-B004", "stage06_party_mapping", not missing_parties, missing_parties, "阶段六主体均通过阶段八明确ID映射")
    fuzzy_used = [row["entity_id"] for row in entities if row.get("mapping_method") != "UPSTREAM_APPROVED_ID_AND_NAME_MAPPING_ONLY"]
    _append(results, "S09-B005", "entity_mapping_method", not fuzzy_used, fuzzy_used, "未使用模糊名称合并")

    evidence_ids = {row["evidence_id"] for row in evidence}
    _append(results, "S09-B006", "canonical_evidence", _unique_nonempty(evidence, "evidence_id"), len(evidence), "统一证据ID非空且唯一")
    supporting_count, unresolved_support = _supporting_reference_status(model)
    business_evidence_unresolved = _business_evidence_unresolved(model, evidence_ids)
    unresolved_all = sorted(set(unresolved_support + business_evidence_unresolved))
    _append(results, "S09-B007", "supporting_references", not unresolved_all, {"resolved_count": supporting_count, "unresolved": unresolved_all}, "支持性引用按类型确定性解析")

    transaction_missing_entities = []
    for row in transactions:
        if len(row.get("party_ids", [])) != len(row.get("entity_ids", [])):
            transaction_missing_entities.append(row["canonical_transaction_id"])
    _append(results, "S09-B008", "transaction_entities", not transaction_missing_entities, transaction_missing_entities, "交易参与方均映射到统一主体")
    _append(results, "S09-B009", "transactions", _unique_nonempty(transactions, "canonical_transaction_id"), len(transactions), "交易记录ID非空且唯一")

    snapshot_missing_entities = [row["canonical_snapshot_record_id"] for row in snapshots if row.get("party_id") and not row.get("entity_id")]
    _append(results, "S09-B010", "snapshot_entities", not snapshot_missing_entities, snapshot_missing_entities, "快照持股主体均映射到统一主体")

    _append(results, "S09-B011", "numeric_source_values", _unique_nonempty(numeric_sources, "canonical_source_value_id"), len(numeric_sources), "数值来源记录ID非空且唯一")
    unresolved_inputs = []
    for validation in validations:
        for item in validation["inputs"]:
            if item["source_reference_resolution"]["status"] == "UNRESOLVED":
                unresolved_inputs.append({"input_id": item["input_id"], "value": item.get("source_value_id")})
    _append(results, "S09-B012", "numeric_input_references", not unresolved_inputs, unresolved_inputs, "数值输入引用均解析或按明确派生类型分类")
    _append(results, "S09-B013", "numeric_validations", _unique_nonempty(validations, "canonical_validation_id"), len(validations), "校验事项按validation_id确定性合并")

    pevc_entity_missing = []
    for row in pevc["investment_records"]:
        attrs = row["attributes"]
        for field in ("investor_entity_id", "counterparty_entity_id"):
            value = attrs.get(field)
            if value and value not in entity_ids:
                pevc_entity_missing.append({"record": attrs["investment_record_id"], "field": field, "value": value})
    for row in pevc["path_edges"]:
        attrs = row["attributes"]
        for field in ("upstream_entity_id", "downstream_entity_id"):
            value = attrs.get(field)
            if value and value not in entity_ids:
                pevc_entity_missing.append({"record": attrs["edge_id"], "field": field, "value": value})
    _append(results, "S09-B014", "pevc_entity_references", not pevc_entity_missing, pevc_entity_missing, "PE/VC投资与路径主体引用完整")

    _append(results, "S09-B015", "source_crosswalk_count", len(crosswalks) == len(source_records), {"crosswalks": len(crosswalks), "source_records": len(source_records)}, "每条来源记录均有交叉映射")
    source_payloads_preserved = _source_payloads_preserved(model, stages)
    _append(results, "S09-B016", "source_payload_preservation", source_payloads_preserved, source_payloads_preserved, "阶段一至八来源字段、空值和数值无损保留")

    missing_artifacts = [item for item in model["input_artifacts"] if item["availability"] != "AVAILABLE"]
    _append(results, "S09-B017", "full_input_availability", not missing_artifacts, [item["artifact_id"] for item in missing_artifacts], "PDF及阶段一至八输入全部可用")

    incomplete_evidence = [row["evidence_id"] for row in evidence if row.get("evidence_completeness") != "FULL_ORIGINAL_EXCERPT"]
    _append(results, "S09-B018", "evidence_excerpt_completeness", not incomplete_evidence, incomplete_evidence, "统一证据记录保留原文摘录或原文描述")

    package_audit_failures = []
    for stage, adapted in stages.items():
        audit = adapted.metadata.get("package_audit")
        if audit and audit.get("result") != "PASS":
            package_audit_failures.append({"stage": stage, "result": audit.get("result"), "issues": audit.get("issues")})
    _append(results, "S09-B019", "upstream_package_integrity", not package_audit_failures, package_audit_failures, "阶段一至八成果包内部哈希或工作簿哈希校验通过")

    pdf_metadata = stages[1].datasets["pdf_metadata"][0]
    pdf_artifact = next((item for item in model["input_artifacts"] if item["artifact_role"] == "PRIMARY_FACT_SOURCE"), None)
    observed_pages = ((pdf_artifact or {}).get("verification") or {}).get("page_count")
    expected_pages = pdf_metadata.get("pdf_page_count")
    pdf_ok = observed_pages == expected_pages == 443
    _append(results, "S09-B020", "pdf_identity_and_pages", pdf_ok, {"expected_pages": expected_pages, "observed_pages": observed_pages, "sha256": (pdf_artifact or {}).get("sha256")}, "PDF二进制已冻结且总页数与阶段一记录一致")

    stage4_events = stages[4].datasets["event_master"]
    stage4_reviews = stages[4].datasets["review_checks"]
    unaccepted_events = [row["event_id"] for row in stage4_events if row.get("review_status") != "已验收通过"]
    unaccepted_checks = [row["event_id"] for row in stage4_reviews if row.get("overall_check_status") != "通过"]
    stale_participant_status = [row["participant_id"] for row in stages[4].datasets["participants"] if row.get("review_status") == "待人工复核"]
    stage4_authority_ok = not unaccepted_events and not unaccepted_checks
    _append(results, "S09-B021", "stage04_authoritative_acceptance", stage4_authority_ok, {"unaccepted_events": unaccepted_events, "unaccepted_checks": unaccepted_checks, "stale_participant_rows": stale_participant_status}, "阶段四事件主表和复核清单为最终验收权威；历史行级状态不覆盖最终决定")

    stage_acceptance = _stage_acceptance_status(stages)
    unapproved = {stage: status for stage, status in stage_acceptance.items() if status not in {"accepted", "final_approved", "FINAL_APPROVED"}}
    _append(results, "S09-B022", "upstream_acceptance_status", not unapproved, stage_acceptance, "阶段一至八均为已验收状态")

    page_mapping_errors = _page_mapping_errors(stages)
    _append(results, "S09-B023", "double_page_mapping", not page_mapping_errors, page_mapping_errors, "目标章节双页码符合PDF页码=正文页码+1的已验收规则")

    if stale_participant_status:
        exceptions.append(_exception(
            "S09-9B-EXC-001",
            "UPSTREAM_STALE_ROW_REVIEW_STATUS",
            "LOW",
            "stage04.participants.review_status",
            "RESOLVED_CONFIRMED",
            ["S09-B021"],
            "保留4条参与方历史状态原值；以阶段四事件主表及复核清单的最终验收决定为权威，不回写上游工作簿。",
            blocking_for_full_9b=False,
            details={"participant_ids": stale_participant_status},
        ))

    semantic_ids = pevc.get("semantic_variance_record_ids", [])
    if semantic_ids:
        exceptions.append(_exception(
            f"S09-9B-EXC-{len(exceptions)+1:03d}",
            "UPSTREAM_FIELD_SEMANTIC_VARIANCE",
            "LOW",
            "stage08.investment_records.stage07_validation_id",
            "RESOLVED_CONFIRMED",
            ["S09-B012", "S09-B014"],
            "字段名为stage07_validation_id，但17条记录实际引用阶段六calculation_id；程序按ID类型解析并保留原字段。",
            blocking_for_full_9b=False,
            details={"record_ids": semantic_ids},
        ))

    failed = [row for row in results if row["result"] == "FAIL"]
    acceptance = [
        {"check_id": "S09-9B-ACC-001", "check_item": "23条基础规则无失败", "result": "PASS" if not failed else "FAIL"},
        {"check_id": "S09-9B-ACC-002", "check_item": "阶段一至八来源记录全部进入source_records和crosswalk", "result": "PASS" if len(crosswalks) == len(source_records) else "FAIL"},
        {"check_id": "S09-9B-ACC-003", "check_item": "未使用模糊主体合并", "result": "PASS" if not fuzzy_used else "FAIL"},
        {"check_id": "S09-9B-ACC-004", "check_item": "PDF及阶段一至八完整输入已挂载", "result": "PASS" if not missing_artifacts else "FAIL"},
        {"check_id": "S09-9B-ACC-005", "check_item": "CE-008-E04已由阶段四证据主表补齐原文", "result": "PASS" if "CE-008-E04" not in incomplete_evidence else "FAIL"},
        {"check_id": "S09-9B-ACC-006", "check_item": "上游包哈希及阶段状态已核验", "result": "PASS" if not package_audit_failures and not unapproved else "FAIL"},
        {"check_id": "S09-9B-ACC-007", "check_item": "用户验收", "result": "PENDING"},
    ]
    return results, exceptions, acceptance


def _append(results: list[dict[str, Any]], rule_id: str, object_id: str, passed: bool, observed: Any, details: str) -> None:
    results.append({
        "rule_id": rule_id,
        "object_id": object_id,
        "result": "PASS" if passed else "FAIL",
        "observed": observed,
        "details": details,
        "program_version": __version__,
        "rule_set_version": RULE_SET_VERSION,
        "review_status": "NOT_REQUIRED" if passed else "PENDING_REVIEW",
    })


def _unique_nonempty(rows: list[dict[str, Any]], field: str) -> bool:
    values = [row.get(field) for row in rows]
    return all(value not in (None, "") for value in values) and len(values) == len(set(values))


def _referenced_ce_events(model: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for row in model["source_crosswalks"]:
        refs.update(x for x in row["event_ids"] if CE_EVENT_RE.fullmatch(x))
    return refs


def _supporting_reference_status(model: dict[str, Any]) -> tuple[int, list[str]]:
    unresolved: list[str] = []
    count = 0
    containers = [*model["numeric_source_values"], *model["numeric_validations"]]
    containers += model["pevc_results"]["investment_records"]
    containers += model["pevc_results"]["path_edges"]
    containers += model["pevc_results"]["final_identification"]
    for row in containers:
        ref = row.get("supporting_references")
        if ref:
            count += len(ref.get("resolved_references", []))
            unresolved.extend(ref.get("unresolved_tokens", []))
        for input_row in row.get("inputs", []):
            input_ref = input_row.get("supporting_references")
            if input_ref:
                count += len(input_ref.get("resolved_references", []))
                unresolved.extend(input_ref.get("unresolved_tokens", []))
        for review in row.get("manual_review_items", []):
            review_ref = review.get("supporting_references")
            if review_ref:
                count += len(review_ref.get("resolved_references", []))
                unresolved.extend(review_ref.get("unresolved_tokens", []))
    return count, sorted(set(unresolved))


def _business_evidence_unresolved(model: dict[str, Any], evidence_ids: set[str]) -> list[str]:
    unresolved: list[str] = []
    rows = [*model["canonical_events"], *model["canonical_entities"], *model["normalized_transactions"], *model["normalized_snapshots"]]
    for row in rows:
        normalized = normalize_reference_tokens(row.get("evidence_ids"))
        for token in normalized["expanded_tokens"]:
            if token not in evidence_ids:
                unresolved.append(token)
    return unresolved


def _source_payloads_preserved(model: dict[str, Any], stages: dict[int, AdaptedStage]) -> bool:
    expected: dict[str, dict[str, Any]] = {}
    for stage in sorted(stages):
        for dataset, rows in stages[stage].datasets.items():
            for row in rows:
                record_id = source_record_id(stage, dataset, row)
                expected[f"S{stage:02d}:{dataset}:{record_id}"] = row
    observed = {row["source_pointer"]: row for row in model["source_records"]}
    if set(expected) != set(observed):
        return False
    for pointer, source in expected.items():
        if observed[pointer]["attributes"] != source:
            return False
        if observed[pointer]["payload_sha256"] != stable_hash(source):
            return False
    return True


def _stage_acceptance_status(stages: dict[int, AdaptedStage]) -> dict[int, str | None]:
    status12 = stages[1].metadata["stage_status"]["stages"]
    by_stage = {int(row["stage"]): row.get("status") for row in status12}
    result: dict[int, str | None] = {1: by_stage.get(1), 2: by_stage.get(2)}
    result[3] = stages[3].metadata.get("manifest", {}).get("status")
    result[4] = stages[4].metadata.get("stage_status")
    result[5] = stages[5].metadata.get("manifest", {}).get("status")
    result[6] = stages[6].metadata.get("manifest", {}).get("status")
    result[7] = stages[7].metadata.get("manifest", {}).get("status")
    result[8] = stages[8].metadata.get("bundle_metadata", {}).get("stage_status")
    return result


def _page_mapping_errors(stages: dict[int, AdaptedStage]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for row in stages[2].datasets["sections"]:
        for side in ("start", "end"):
            pdf_value = row.get(f"pdf_{side}_page")
            printed_value = row.get(f"printed_{side}_page")
            if pdf_value in (None, "") or printed_value in (None, ""):
                continue
            try:
                if int(pdf_value) != int(printed_value) + 1:
                    errors.append({"section_id": row.get("section_id"), "side": side, "pdf": pdf_value, "printed": printed_value})
            except ValueError:
                errors.append({"section_id": row.get("section_id"), "side": side, "pdf": pdf_value, "printed": printed_value, "error": "NON_INTEGER"})
    return errors


def _exception(exception_id: str, exception_type: str, severity: str, object_id: str, status: str, rule_ids: list[str], recommended_action: str, *, blocking_for_full_9b: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "exception_id": exception_id,
        "exception_type": exception_type,
        "severity": severity,
        "object_id": object_id,
        "status": status,
        "triggered_rule_ids": rule_ids,
        "recommended_action": recommended_action,
        "blocking_for_current_available_scope": False,
        "blocking_for_full_9b": blocking_for_full_9b,
        "details": details or {},
        "program_version": __version__,
        "rule_set_version": RULE_SET_VERSION,
    }
