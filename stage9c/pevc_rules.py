from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import RULE_SET_VERSION, __version__
from .trace import as_tokens, dedupe, evidence_ids_from_record, trace_from_evidence

ALLOWED_STATUSES = {"CONFIRMED", "CANDIDATE", "RELATED", "EXCLUDED", "UNRESOLVED"}


def pevc_evaluations(model: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    results = model["pevc_results"]
    entities = {row["entity_id"]: row for row in model["canonical_entities"]}
    source_entities = {row["entity_id"]: row for row in results["final_identification"]}
    edges = results["path_edges"]
    edge_attrs = [row["attributes"] for row in edges]
    investments = results["investment_records"]
    output: list[dict[str, Any]] = []

    for record in investments:
        a = record["attributes"]
        checks: list[dict[str, Any]] = []
        status_row = source_entities.get(a["investor_entity_id"])
        status = (status_row or {}).get("attributes", {}).get("pevc_status")
        _check(checks, "S09-P001", status in ALLOWED_STATUSES and a.get("review_status") == "确认通过", {"status": status, "review": a.get("review_status")}, {"status": sorted(ALLOWED_STATUSES), "review": "确认通过"}, "投资主体分类来自已验收阶段八")
        level_method_ok = a.get("investment_level") in {"DIRECT", "INDIRECT"} and a.get("entry_method") in {"CAPITAL_INCREASE", "SHARE_TRANSFER"}
        _check(checks, "S09-P002", level_method_ok, {"investment_level": a.get("investment_level"), "entry_method": a.get("entry_method")}, "independent controlled dimensions", "直接/间接与增资/受让是两个独立维度")
        edge_ok, edge_observed = _investment_edge_match(a, edge_attrs)
        _check(checks, "S09-P003", edge_ok, edge_observed, "matching path edge", "投资事件与路径边类型一致")
        direct_path_ok = a.get("investment_level") != "DIRECT" or edge_ok
        _check(checks, "S09-P004", direct_path_ok, edge_observed, "direct investment has transaction/legal path", "直接投资必须有发行人权益或交易进入边")
        _check(checks, "S09-P005", True, "evaluated_on_path_edges", "evaluated_on_path_edges", "GP/管理人边规则在路径边执行")
        _check(checks, "S09-P006", True, "evaluated_on_path_edges", "evaluated_on_path_edges", "间接经济路径规则在路径边执行")
        if a.get("value_type") == "NOT_DISCLOSED":
            fields = ["shares_or_capital_value", "cash_or_consideration_value"]
            values_null = all(a.get(field) is None for field in fields) and a.get("actual_investment_amount_disclosed") == "否"
            observed = {field: a.get(field) for field in fields} | {"disclosed": a.get("actual_investment_amount_disclosed")}
        else:
            values_null, observed = True, "not_applicable_disclosed"
        _check(checks, "S09-P007", values_null, observed, "undisclosed values remain null", "未披露投资金额不得填零、均分或倒推")
        _check(checks, "S09-P008", True, "evaluated_on_final_identification", "evaluated_on_final_identification", "最终分类一致性在主体最终记录执行")
        _check(checks, "S09-P009", True, "evaluated_on_final_identification", "evaluated_on_final_identification", "CONFIRMED证据门槛在主体最终记录执行")
        _check(checks, "S09-P010", True, "evaluated_on_path_edges", "evaluated_on_path_edges", "路径序号规则在路径边执行")
        event_covered = a.get("event_id") in as_tokens((status_row or {}).get("attributes", {}).get("investment_event_ids")) if status_row else False
        _check(checks, "S09-P011", event_covered, a.get("event_id"), as_tokens((status_row or {}).get("attributes", {}).get("investment_event_ids")), "投资事件进入主体最终汇总")
        output.append(_evaluation(model, record, "PEVC_INVESTMENT", a["investment_record_id"], checks, run_id))

    paths: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in edges:
        paths[str(record["attributes"].get("path_id"))].append(record["attributes"])
    for record in edges:
        a = record["attributes"]
        checks: list[dict[str, Any]] = []
        _check(checks, "S09-P001", a.get("review_status") == "确认通过", a.get("review_status"), "确认通过", "路径边已人工验收")
        _check(checks, "S09-P002", a.get("direct_or_indirect") in {"DIRECT", "INDIRECT"}, a.get("direct_or_indirect"), ["DIRECT", "INDIRECT"], "路径直接性字段受控")
        _check(checks, "S09-P003", True, "evaluated_on_investment_records", "evaluated_on_investment_records", "投资记录匹配规则")
        _check(checks, "S09-P004", True, "evaluated_on_investment_records", "evaluated_on_investment_records", "直接投资路径规则")
        gp = a.get("relationship_type") in {"GENERAL_PARTNER", "GENERAL_PARTNER_EXECUTIVE"}
        gp_ok = not gp or (a.get("path_forming_flag") == "否" and "不直接形成发行人权益路径" in str(a.get("path_nature")))
        _check(checks, "S09-P005", gp_ok, {"relationship_type": a.get("relationship_type"), "path_forming_flag": a.get("path_forming_flag"), "path_nature": a.get("path_nature")}, {"path_forming_flag": "否"}, "GP、管理人及执行事务合伙人关系默认不形成发行人权益路径")
        indirect = a.get("direct_or_indirect") == "INDIRECT" and a.get("path_forming_flag") == "是"
        indirect_ok = not indirect or a.get("relationship_type") == "FUND_SOURCE_REPRESENTED_INVESTMENT"
        _check(checks, "S09-P006", indirect_ok, {"relationship_type": a.get("relationship_type"), "direct_or_indirect": a.get("direct_or_indirect"), "forming": a.get("path_forming_flag")}, "only explicit represented fund-source edge may form indirect economic path", "间接经济路径仅在原文明示资金来源时形成")
        _check(checks, "S09-P007", True, "not_applicable_path_edge", "not_applicable_path_edge", "投资数值披露规则")
        _check(checks, "S09-P008", True, "not_applicable_path_edge", "not_applicable_path_edge", "主体最终分类规则")
        _check(checks, "S09-P009", True, "not_applicable_path_edge", "not_applicable_path_edge", "CONFIRMED证据规则")
        sequence = sorted(int(x.get("edge_sequence")) for x in paths[str(a.get("path_id"))])
        sequence_ok = sequence == list(range(1, len(sequence) + 1)) and len(sequence) == len(set(sequence))
        _check(checks, "S09-P010", sequence_ok, sequence, list(range(1, len(sequence) + 1)), "同一路径边序号唯一且连续")
        _check(checks, "S09-P011", True, "not_applicable_path_edge", "not_applicable_path_edge", "投资事件汇总规则")
        output.append(_evaluation(model, record, "PEVC_PATH_EDGE", a["edge_id"], checks, run_id))

    entity_source = _stage8_entity_source(model)
    for record in results["final_identification"]:
        a = record["attributes"]
        checks: list[dict[str, Any]] = []
        source = entity_source.get(record["entity_id"], {})
        _check(checks, "S09-P001", a.get("pevc_status") in ALLOWED_STATUSES, a.get("pevc_status"), sorted(ALLOWED_STATUSES), "最终PE/VC状态受控")
        _check(checks, "S09-P002", True, "not_applicable_final", "not_applicable_final", "投资维度规则")
        _check(checks, "S09-P003", True, "not_applicable_final", "not_applicable_final", "路径匹配规则")
        _check(checks, "S09-P004", True, "not_applicable_final", "not_applicable_final", "直接路径规则")
        _check(checks, "S09-P005", True, "not_applicable_final", "not_applicable_final", "GP路径规则")
        _check(checks, "S09-P006", True, "not_applicable_final", "not_applicable_final", "间接经济路径规则")
        _check(checks, "S09-P007", True, "not_applicable_final", "not_applicable_final", "未披露值规则")
        consistency = source.get("pevc_status") == a.get("pevc_status") and source.get("canonical_name") == a.get("canonical_name")
        _check(checks, "S09-P008", consistency, {"entity": source.get("pevc_status"), "final": a.get("pevc_status"), "names": [source.get("canonical_name"), a.get("canonical_name")]}, "same stage08 approved classification and canonical name", "最终识别与已验收主体主表一致")
        if a.get("pevc_status") == "CONFIRMED":
            confirmed_ok = bool(evidence_ids_from_record(record)) and a.get("confidence") == "HIGH" and "确认通过" in str(a.get("final_review_conclusion"))
            observed = {"evidence_ids": evidence_ids_from_record(record), "confidence": a.get("confidence"), "conclusion": a.get("final_review_conclusion")}
        else:
            confirmed_ok, observed = True, "not_applicable_nonconfirmed"
        _check(checks, "S09-P009", confirmed_ok, observed, {"evidence": "required", "confidence": "HIGH", "human_confirmation": "required"}, "CONFIRMED主体必须有招股书证据及人工确认")
        _check(checks, "S09-P010", True, "not_applicable_final", "not_applicable_final", "路径序号规则")
        investment_events = as_tokens(a.get("investment_event_ids"))
        actual_events = dedupe(x["attributes"].get("event_id") for x in investments if x["attributes"].get("investor_entity_id") == record["entity_id"])
        coverage = set(investment_events) == set(actual_events)
        _check(checks, "S09-P011", coverage, investment_events, actual_events, "主体最终投资事件清单与投资记录一致")
        output.append(_evaluation(model, record, "PEVC_FINAL_IDENTIFICATION", record["final_record_id"], checks, run_id))
    return output


def _investment_edge_match(a: dict[str, Any], edges: list[dict[str, Any]]) -> tuple[bool, Any]:
    event_id = a.get("event_id")
    investor = a.get("investor_entity_id")
    counterparty = a.get("counterparty_entity_id")
    method = a.get("entry_method")
    role = a.get("investor_role")
    matches = []
    for edge in edges:
        if edge.get("event_id") != event_id:
            continue
        if method == "CAPITAL_INCREASE" and edge.get("relationship_type") == "CAPITAL_SUBSCRIPTION" and edge.get("upstream_entity_id") == investor and edge.get("downstream_entity_id") == "ENT-ISSUER":
            matches.append(edge.get("edge_id"))
        if method == "SHARE_TRANSFER" and edge.get("relationship_type") == "SHARE_TRANSFER":
            if role == "全部转让退出" and edge.get("upstream_entity_id") == investor and (counterparty is None or edge.get("downstream_entity_id") == counterparty):
                matches.append(edge.get("edge_id"))
            elif role != "全部转让退出" and edge.get("downstream_entity_id") == investor and (counterparty is None or edge.get("upstream_entity_id") == counterparty):
                matches.append(edge.get("edge_id"))
        # Early events may only have the already-accepted direct holding edge rather than a separate transfer edge.
        if method == "SHARE_TRANSFER" and role != "全部转让退出" and counterparty is None and edge.get("relationship_type") == "DIRECT_SHAREHOLDING" and edge.get("upstream_entity_id") == investor and edge.get("downstream_entity_id") == "ENT-ISSUER":
            matches.append(edge.get("edge_id"))
    return bool(matches), {"matched_edge_ids": matches, "event_id": event_id, "method": method, "investor": investor, "counterparty": counterparty}


def _stage8_entity_source(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output = {}
    for row in model.get("source_records", []):
        if row.get("source_stage") == 8 and row.get("source_dataset") == "entities":
            attrs = row.get("attributes") or {}
            if attrs.get("entity_id"):
                output[str(attrs["entity_id"])] = attrs
    return output


def _evaluation(model: dict[str, Any], record: dict[str, Any], object_type: str, object_id: str, checks: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    evidence_ids = evidence_ids_from_record(record)
    trace = trace_from_evidence(model, evidence_ids)
    attrs = record.get("attributes") or {}
    trace["pdf_pages"] = dedupe(trace["pdf_pages"] + as_tokens(attrs.get("pdf_pages")))
    trace["printed_pages"] = dedupe(trace["printed_pages"] + as_tokens(attrs.get("printed_pages")))
    if attrs.get("original_excerpt"):
        trace["original_excerpts"] = dedupe(trace["original_excerpts"] + [str(attrs["original_excerpt"])])
    if attrs.get("path_or_relation_summary"):
        trace["original_excerpts"] = dedupe(trace["original_excerpts"] + [str(attrs["path_or_relation_summary"])])
    overall = "PASS" if all(check["result"] == "PASS" for check in checks) else "FAIL"
    event_ids = dedupe(as_tokens(attrs.get("event_id")) + as_tokens(attrs.get("investment_event_ids")) + as_tokens(attrs.get("first_entry_event_id")) + as_tokens(attrs.get("last_exit_event_id")))
    if not event_ids:
        event_ids = ["GLOBAL"]
    return {
        "evaluation_id": f"S09-9C-{object_type}-{object_id}",
        "object_type": object_type,
        "object_id": object_id,
        "event_ids": event_ids,
        **trace,
        "checks": checks,
        "overall_result": overall,
        "derivation_type": "RULE_CLASSIFICATION",
        "program_version": __version__,
        "rule_set_version": RULE_SET_VERSION,
        "run_id": run_id,
        "review_required": overall == "FAIL",
        "review_status": "AUTO_PASS_PENDING_9C_ACCEPTANCE" if overall == "PASS" else "PENDING_9D_REVIEW",
    }


def _check(checks: list[dict[str, Any]], rule_id: str, passed: bool, observed: Any, expected: Any, note: str) -> None:
    checks.append({"rule_id": rule_id, "result": "PASS" if passed else "FAIL", "observed": observed, "expected": expected, "note": note})
