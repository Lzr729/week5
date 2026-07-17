from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Iterable

from . import RULE_SET_VERSION, __version__
from .adapters import (
    CE_EVENT_RE,
    EVIDENCE_FIELDS,
    EVENT_FIELDS,
    EXCERPT_FIELDS,
    PDF_PAGE_FIELDS,
    PRINTED_PAGE_FIELDS,
    REVIEW_FIELDS,
    AdaptedStage,
    collect_tokens,
    dedupe,
    first_present,
    normalize_reference_tokens,
    source_record_id,
    split_tokens,
)

STAGE_DATASET_OBJECT_TYPES: dict[tuple[int, str], str] = {
    (1, "pdf_metadata"): "PDF_METADATA",
    (1, "evidence"): "EVIDENCE",
    (2, "sections"): "SECTION",
    (2, "evidence"): "EVIDENCE",
    (3, "candidate_events"): "EVENT",
    (3, "flowchart_nodes"): "FLOWCHART_NODE",
    (3, "auxiliary_findings"): "AUXILIARY_FINDING",
    (3, "evidence"): "EVIDENCE",
    (4, "event_master"): "EVENT",
    (4, "participants"): "EVENT_PARTICIPANT",
    (4, "evidence"): "EVIDENCE",
    (4, "source_values"): "NUMERIC_SOURCE_VALUE",
    (4, "review_checks"): "ACCEPTANCE_CHECK",
    (5, "equity_timeline"): "EQUITY_TIMELINE",
    (5, "time_nodes"): "TIME_NODE",
    (5, "calculations"): "CALCULATION",
    (5, "exclusions"): "EXCLUSION",
    (5, "auxiliaries"): "AUXILIARY_FINDING",
    (5, "review_items"): "REVIEW_ITEM",
    (5, "acceptance_checks"): "ACCEPTANCE_CHECK",
    (6, "parties"): "ENTITY",
    (6, "increase_events"): "TRANSACTION",
    (6, "subscriptions"): "TRANSACTION",
    (6, "transfer_events"): "TRANSACTION",
    (6, "transfer_lots"): "TRANSACTION",
    (6, "snapshots"): "SNAPSHOT",
    (6, "snapshot_holdings"): "SNAPSHOT_HOLDING",
    (6, "calculations"): "CALCULATION",
    (6, "evidence_reviews"): "EVIDENCE_OR_REVIEW",
    (6, "acceptance_checks"): "ACCEPTANCE_CHECK",
    (6, "audit_log"): "AUDIT_LOG",
    (7, "source_values"): "NUMERIC_SOURCE_VALUE",
    (7, "validation_items"): "NUMERIC_VALIDATION",
    (7, "calculation_inputs"): "NUMERIC_INPUT",
    (7, "validation_results"): "NUMERIC_VALIDATION_RESULT",
    (7, "manual_review_items"): "REVIEW_ITEM",
    (7, "acceptance_checks"): "ACCEPTANCE_CHECK",
    (7, "review_log"): "AUDIT_LOG",
    (8, "entities"): "ENTITY",
    (8, "name_mappings"): "ENTITY_NAME_MAPPING",
    (8, "investment_records"): "PEVC_INVESTMENT",
    (8, "path_edges"): "PEVC_PATH_EDGE",
    (8, "evidence"): "EVIDENCE",
    (8, "review_items"): "REVIEW_ITEM",
    (8, "qa_results"): "ACCEPTANCE_CHECK",
    (8, "final_identification"): "PEVC_FINAL_IDENTIFICATION",
}

TRANSACTION_DATASETS = ("increase_events", "subscriptions", "transfer_events", "transfer_lots")
SNAPSHOT_DATASETS = ("snapshots", "snapshot_holdings")


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_unified_model(
    stages: dict[int, AdaptedStage],
    input_artifacts: list[dict[str, Any]],
    *,
    run_id: str = "S09-9B-RUN-002",
) -> dict[str, Any]:
    required = set(range(1, 9))
    missing = required - set(stages)
    if missing:
        raise ValueError(f"Full 9B model requires stages 1-8; missing {sorted(missing)}")

    stage6, stage7, stage8 = stages[6], stages[7], stages[8]
    party_to_entity = _party_to_entity_map(stage8)
    reference_catalog = _reference_catalog(stages)

    source_records = _build_source_records(stages)
    crosswalks = _build_crosswalks(stages, party_to_entity)
    canonical_events = _build_events(stages)
    canonical_entities = _build_entities(stage6, stage8)
    canonical_evidence = _build_evidence(stages)
    transactions = _build_transactions(stage6, party_to_entity)
    snapshots = _build_snapshots(stage6, party_to_entity)
    numeric_source_values, numeric_validations = _build_numeric(stage7, reference_catalog)
    pevc_results = _build_pevc(stage8, reference_catalog)

    model = {
        "metadata": {
            "project": "301563云汉芯城招股说明书工程化学习",
            "stage": 9,
            "substage": "9B",
            "status": "PENDING_USER_ACCEPTANCE_FULL_INPUT",
            "scope": "统一中间数据模型与基础完整性规则；已接入PDF及阶段一至八全部已验收成果",
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "run_id": run_id,
            "primary_fact_source": "301563_云汉芯城_IPO招股说明书.pdf",
            "automation_boundary": "仅来源复制、格式标准化、确定性聚合和明确引用解析；不生成新业务事实，不做模糊名称合并",
        },
        "input_artifacts": input_artifacts,
        "source_records": source_records,
        "source_crosswalks": crosswalks,
        "document_context": _build_document_context(stages),
        "candidate_event_register": _build_candidate_register(stages[3]),
        "event_annotations": _build_event_annotations(stages[4]),
        "equity_timeline": _build_equity_timeline(stages[5]),
        "canonical_events": canonical_events,
        "canonical_entities": canonical_entities,
        "canonical_evidence": canonical_evidence,
        "normalized_transactions": transactions,
        "normalized_snapshots": snapshots,
        "numeric_source_values": numeric_source_values,
        "numeric_validations": numeric_validations,
        "pevc_results": pevc_results,
        "rule_results": [],
        "exceptions": [],
        "review_actions": [],
        "acceptance_checks": [],
        "run_manifest": {
            "run_id": run_id,
            "program_version": __version__,
            "rule_set_version": RULE_SET_VERSION,
            "adapted_stages": sorted(stages),
            "source_record_count": len(source_records),
            "business_output_hash": None,
        },
    }
    business_view = {key: model[key] for key in (
        "source_records",
        "source_crosswalks",
        "document_context",
        "candidate_event_register",
        "event_annotations",
        "equity_timeline",
        "canonical_events",
        "canonical_entities",
        "canonical_evidence",
        "normalized_transactions",
        "normalized_snapshots",
        "numeric_source_values",
        "numeric_validations",
        "pevc_results",
    )}
    model["run_manifest"]["business_output_hash"] = stable_hash(business_view)
    return model


def _party_to_entity_map(stage8: AdaptedStage) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entity in stage8.datasets["entities"]:
        party_id = entity.get("upstream_party_id")
        if party_id:
            mapping[str(party_id)] = str(entity["entity_id"])
    return mapping


def _reference_catalog(stages: dict[int, AdaptedStage]) -> dict[str, list[str]]:
    """Build an ID-to-object-types catalog without collapsing legitimate multi-role IDs.

    Upstream stages intentionally reuse some identifiers across an authoritative row and
    its review/check row (for example an event ID), and some stage-seven numeric source
    IDs resemble evidence IDs.  Retaining all observed types allows the resolver to apply
    field-specific deterministic priorities instead of treating those IDs as broken.
    """
    catalog_sets: dict[str, set[str]] = defaultdict(set)
    for stage, stage_data in stages.items():
        for dataset, rows in stage_data.datasets.items():
            object_type = STAGE_DATASET_OBJECT_TYPES[(stage, dataset)]
            for row in rows:
                record_id = source_record_id(stage, dataset, row)
                if not record_id:
                    continue
                catalog_sets[record_id].add(object_type)
    return {record_id: sorted(types) for record_id, types in catalog_sets.items()}


def _record_trace(stage: int, dataset: str, row: dict[str, Any]) -> dict[str, Any]:
    review_field, review_value = first_present(row, REVIEW_FIELDS)
    event_ids = [x for x in collect_tokens(row, EVENT_FIELDS) if CE_EVENT_RE.fullmatch(x)]
    return {
        "source_stage": stage,
        "source_dataset": dataset,
        "source_record_id": source_record_id(stage, dataset, row),
        "event_ids": event_ids,
        "evidence_ids": collect_tokens(row, EVIDENCE_FIELDS),
        "pdf_pages": collect_tokens(row, PDF_PAGE_FIELDS),
        "printed_pages": collect_tokens(row, PRINTED_PAGE_FIELDS),
        "original_excerpts": dedupe([str(row[field]) for field in EXCERPT_FIELDS if row.get(field) not in (None, "")]),
        "source_review_field": review_field,
        "source_review_status": review_value,
    }


def _build_source_records(stages: dict[int, AdaptedStage]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for stage in sorted(stages):
        for dataset in stages[stage].datasets:
            for row in stages[stage].datasets[dataset]:
                record_id = source_record_id(stage, dataset, row)
                output.append({
                    "source_pointer": f"S{stage:02d}:{dataset}:{record_id}",
                    "source_stage": stage,
                    "source_dataset": dataset,
                    "source_record_id": record_id,
                    "source_object_type": STAGE_DATASET_OBJECT_TYPES[(stage, dataset)],
                    "attributes": copy.deepcopy(row),
                    "payload_sha256": stable_hash(row),
                    "derivation_type": "SOURCE_COPY",
                    "program_version": __version__,
                    "rule_set_version": RULE_SET_VERSION,
                })
    return output


def _canonical_ids_for_source(stage: int, dataset: str, row: dict[str, Any], party_to_entity: dict[str, str]) -> list[str]:
    record_id = source_record_id(stage, dataset, row)
    if not record_id:
        return []
    if STAGE_DATASET_OBJECT_TYPES[(stage, dataset)] == "EVENT":
        return [record_id]
    if STAGE_DATASET_OBJECT_TYPES[(stage, dataset)] == "EVIDENCE":
        return [record_id]
    if stage == 6 and dataset == "parties" and record_id in party_to_entity:
        return [party_to_entity[record_id]]
    if stage == 8 and dataset in ("entities", "name_mappings", "final_identification"):
        entity_id = row.get("entity_id")
        return [str(entity_id)] if entity_id else []
    if stage == 6 and dataset in TRANSACTION_DATASETS:
        return [f"TXN-{record_id}"]
    if stage == 6 and dataset in SNAPSHOT_DATASETS:
        return [f"SNP-{record_id}"]
    if stage == 7 and dataset in ("validation_items", "validation_results"):
        return [f"NUM-{record_id}"]
    if stage == 7 and dataset == "calculation_inputs":
        validation_id = row.get("validation_id")
        return [f"NUM-{validation_id}"] if validation_id else []
    if stage == 7 and dataset == "source_values":
        return [f"NUMSRC-{record_id}"]
    if stage == 8 and dataset == "investment_records":
        return [f"PEVC-{record_id}"]
    if stage == 8 and dataset == "path_edges":
        return [record_id]
    return [record_id]


def _build_crosswalks(stages: dict[int, AdaptedStage], party_to_entity: dict[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for stage in sorted(stages):
        for dataset in stages[stage].datasets:
            for row in stages[stage].datasets[dataset]:
                trace = _record_trace(stage, dataset, row)
                output.append({
                    **trace,
                    "source_pointer": f"S{stage:02d}:{dataset}:{trace['source_record_id']}",
                    "source_object_type": STAGE_DATASET_OBJECT_TYPES[(stage, dataset)],
                    "canonical_ids": _canonical_ids_for_source(stage, dataset, row, party_to_entity),
                    "source_payload_sha256": stable_hash(row),
                    "derivation_type": "FORMAT_NORMALIZATION",
                    "program_version": __version__,
                    "rule_set_version": RULE_SET_VERSION,
                    "review_status": "INHERITED_UPSTREAM",
                })
    return output


def _build_document_context(stages: dict[int, AdaptedStage]) -> dict[str, Any]:
    return {
        "pdf_metadata": copy.deepcopy(stages[1].datasets["pdf_metadata"][0]),
        "sections": copy.deepcopy(stages[2].datasets["sections"]),
        "stage01_evidence": copy.deepcopy(stages[1].datasets["evidence"]),
        "stage02_evidence": copy.deepcopy(stages[2].datasets["evidence"]),
        "derivation_type": "SOURCE_COPY",
        "program_version": __version__,
    }


def _build_candidate_register(stage3: AdaptedStage) -> dict[str, Any]:
    return {
        "candidate_events": copy.deepcopy(stage3.datasets["candidate_events"]),
        "flowchart_nodes": copy.deepcopy(stage3.datasets["flowchart_nodes"]),
        "auxiliary_findings": copy.deepcopy(stage3.datasets["auxiliary_findings"]),
        "evidence": copy.deepcopy(stage3.datasets["evidence"]),
        "derivation_type": "SOURCE_COPY",
        "program_version": __version__,
    }


def _build_event_annotations(stage4: AdaptedStage) -> dict[str, Any]:
    return {
        "event_master": copy.deepcopy(stage4.datasets["event_master"]),
        "participants": copy.deepcopy(stage4.datasets["participants"]),
        "evidence": copy.deepcopy(stage4.datasets["evidence"]),
        "source_values": copy.deepcopy(stage4.datasets["source_values"]),
        "review_checks": copy.deepcopy(stage4.datasets["review_checks"]),
        "derivation_type": "SOURCE_COPY",
        "program_version": __version__,
    }


def _build_equity_timeline(stage5: AdaptedStage) -> dict[str, Any]:
    return {
        **{name: copy.deepcopy(rows) for name, rows in stage5.datasets.items()},
        "derivation_type": "SOURCE_COPY",
        "program_version": __version__,
    }


def _build_events(stages: dict[int, AdaptedStage]) -> list[dict[str, Any]]:
    event_acc: dict[str, dict[str, Any]] = {}
    label_fields = ("standard_event_name", "event_name", "stage3_title", "increase_type", "validation_description", "entry_method", "transaction_leg")
    date_fields = ("primary_display_time", "stage3_date", "event_date", "original_date_text", "event_date_raw", "standardized_date", "title_date")
    for stage in sorted(stages):
        for dataset, rows in stages[stage].datasets.items():
            for row in rows:
                trace = _record_trace(stage, dataset, row)
                for event_id in trace["event_ids"]:
                    item = event_acc.setdefault(event_id, {
                        "event_id": event_id,
                        "source_record_ids": [],
                        "parent_event_ids": [],
                        "event_labels": [],
                        "date_texts": [],
                        "evidence_ids": [],
                        "pdf_pages": [],
                        "printed_pages": [],
                        "original_excerpts": [],
                        "source_review_statuses": [],
                    })
                    source_pointer = f"S{stage:02d}:{dataset}:{trace['source_record_id']}"
                    item["source_record_ids"].append(source_pointer)
                    parent = row.get("parent_event_id")
                    if parent and str(parent) != event_id and CE_EVENT_RE.fullmatch(str(parent)):
                        item["parent_event_ids"].append(str(parent))
                    for field in label_fields:
                        if row.get(field) not in (None, ""):
                            item["event_labels"].append({"value": str(row[field]), "source": source_pointer, "field": field})
                    for field in date_fields:
                        if row.get(field) not in (None, ""):
                            item["date_texts"].append({"value": str(row[field]), "source": source_pointer, "field": field})
                    item["evidence_ids"].extend(trace["evidence_ids"])
                    item["pdf_pages"].extend(trace["pdf_pages"])
                    item["printed_pages"].extend(trace["printed_pages"])
                    item["original_excerpts"].extend(trace["original_excerpts"])
                    if trace["source_review_status"] not in (None, ""):
                        item["source_review_statuses"].append(str(trace["source_review_status"]))
    stage4_by_event = {str(row["event_id"]): row for row in stages[4].datasets["event_master"]}
    stage5_by_event = {str(row["event_id"]): row for row in stages[5].datasets["equity_timeline"]}
    stage3_by_event = {str(row["event_id"]): row for row in stages[3].datasets["candidate_events"]}
    result: list[dict[str, Any]] = []
    for event_id in sorted(event_acc):
        item = event_acc[event_id]
        for field in ("source_record_ids", "parent_event_ids", "evidence_ids", "pdf_pages", "printed_pages", "original_excerpts", "source_review_statuses"):
            item[field] = dedupe(item[field])
        item["event_labels"] = _dedupe_dicts(item["event_labels"])
        item["date_texts"] = _dedupe_dicts(item["date_texts"])
        authoritative = stage4_by_event.get(event_id)
        timeline = stage5_by_event.get(event_id)
        candidate = stage3_by_event.get(event_id)
        item.update({
            "canonical_label": (authoritative or {}).get("standard_event_name") or (timeline or {}).get("standard_event_name") or (candidate or {}).get("event_name"),
            "canonical_date_text": (timeline or {}).get("primary_display_time") or (authoritative or {}).get("stage3_date") or (candidate or {}).get("event_date"),
            "authoritative_stage04_record": copy.deepcopy(authoritative),
            "stage05_timeline_record": copy.deepcopy(timeline),
            "derivation_type": "SOURCE_AGGREGATION_WITH_STAGE04_AUTHORITY",
            "program_version": __version__,
            "rule_ids": ["S09-B001", "S09-B002"],
            "review_status": (authoritative or {}).get("review_status", "INHERITED_UPSTREAM"),
            "completeness_status": "FULL_WITH_STAGE03_STAGE04_STAGE05",
        })
        result.append(item)
    return result


def _build_entities(stage6: AdaptedStage, stage8: AdaptedStage) -> list[dict[str, Any]]:
    parties = {str(row["party_id"]): row for row in stage6.datasets["parties"]}
    mappings_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in stage8.datasets["name_mappings"]:
        mappings_by_entity[str(mapping["entity_id"])].append(copy.deepcopy(mapping))
    output: list[dict[str, Any]] = []
    for row in stage8.datasets["entities"]:
        entity_id = str(row["entity_id"])
        upstream_party_id = row.get("upstream_party_id")
        party = parties.get(str(upstream_party_id)) if upstream_party_id else None
        output.append({
            "entity_id": entity_id,
            "canonical_name": row.get("canonical_name"),
            "entity_type": row.get("entity_type"),
            "pevc_status": row.get("pevc_status"),
            "pevc_role": row.get("pevc_role"),
            "upstream_party_id": upstream_party_id,
            "name_mappings": mappings_by_entity.get(entity_id, []),
            "stage08_attributes": copy.deepcopy(row),
            "stage06_party_attributes": copy.deepcopy(party),
            "event_ids": dedupe([x for x in collect_tokens(row, EVENT_FIELDS) if CE_EVENT_RE.fullmatch(x)]),
            "evidence_ids": split_tokens(row.get("evidence_ids")),
            "pdf_pages": split_tokens(row.get("pdf_pages")),
            "printed_pages": split_tokens(row.get("printed_pages")),
            "source_record_ids": dedupe([
                f"S08:entities:{entity_id}",
                *([f"S06:parties:{upstream_party_id}"] if upstream_party_id else []),
                *[f"S08:name_mappings:{item['name_record_id']}" for item in mappings_by_entity.get(entity_id, [])],
            ]),
            "derivation_type": "SOURCE_COPY_AND_EXPLICIT_MAPPING",
            "mapping_method": "UPSTREAM_APPROVED_ID_AND_NAME_MAPPING_ONLY",
            "program_version": __version__,
            "rule_ids": ["S09-B003", "S09-B004", "S09-B005"],
            "review_status": row.get("review_decision", "INHERITED_UPSTREAM"),
        })
    return output


def _build_evidence(stages: dict[int, AdaptedStage]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}

    def add(stage: int, dataset: str, row: dict[str, Any], evidence_id: str, excerpts: list[str] | None = None) -> None:
        trace = _record_trace(stage, dataset, row)
        item = records.setdefault(evidence_id, {
            "evidence_id": evidence_id,
            "evidence_systems": [],
            "source_record_ids": [],
            "event_ids": [],
            "pdf_pages": [],
            "printed_pages": [],
            "original_excerpts": [],
            "supported_fields": [],
            "source_attributes": [],
            "source_review_statuses": [],
        })
        item["evidence_systems"].append(f"STAGE{stage:02d}_{dataset.upper()}")
        item["source_record_ids"].append(f"S{stage:02d}:{dataset}:{trace['source_record_id']}")
        item["event_ids"].extend(trace["event_ids"])
        item["pdf_pages"].extend(trace["pdf_pages"])
        item["printed_pages"].extend(trace["printed_pages"])
        item["original_excerpts"].extend(excerpts if excerpts is not None else trace["original_excerpts"])
        for field in ("used_for", "supported_fields", "supported_fields_or_review_point", "supported_field"):
            item["supported_fields"].extend(split_tokens(row.get(field)))
        item["source_attributes"].append({"source_stage": stage, "source_dataset": dataset, "attributes": copy.deepcopy(row)})
        if trace["source_review_status"] not in (None, ""):
            item["source_review_statuses"].append(str(trace["source_review_status"]))

    for stage in (1, 2, 3, 4, 8):
        for row in stages[stage].datasets["evidence"]:
            evidence_id = str(row["evidence_id"])
            add(stage, "evidence", row, evidence_id)

    for row in stages[6].datasets["evidence_reviews"]:
        if row.get("record_type") != "PDF原文证据":
            continue
        evidence_ids = split_tokens(row.get("evidence_ids")) or [str(row["record_id"])]
        for evidence_id in evidence_ids:
            excerpts = [str(row["original_evidence_or_issue"])] if row.get("original_evidence_or_issue") else []
            add(6, "evidence_reviews", row, evidence_id, excerpts)

    output: list[dict[str, Any]] = []
    for evidence_id in sorted(records):
        item = records[evidence_id]
        for field in ("evidence_systems", "source_record_ids", "event_ids", "pdf_pages", "printed_pages", "original_excerpts", "supported_fields", "source_review_statuses"):
            item[field] = dedupe(item[field])
        item["source_attributes"] = _dedupe_dicts(item["source_attributes"])
        item["evidence_completeness"] = "FULL_ORIGINAL_EXCERPT" if item["original_excerpts"] else "ID_AND_PAGE_ONLY"
        item.update({
            "derivation_type": "SOURCE_COPY_AND_AGGREGATION",
            "program_version": __version__,
            "rule_ids": ["S09-B006", "S09-B007", "S09-B018"],
            "review_status": "INHERITED_UPSTREAM",
        })
        output.append(item)
    return output


def _build_transactions(stage6: AdaptedStage, party_to_entity: dict[str, str]) -> list[dict[str, Any]]:
    type_map = {
        "increase_events": ("CAPITAL_INCREASE", "EVENT"),
        "subscriptions": ("CAPITAL_INCREASE", "PARTICIPANT_LEG"),
        "transfer_events": ("SHARE_TRANSFER", "EVENT"),
        "transfer_lots": ("SHARE_TRANSFER", "TRANSFER_LOT"),
    }
    output: list[dict[str, Any]] = []
    for dataset in TRANSACTION_DATASETS:
        transaction_type, level = type_map[dataset]
        for row in stage6.datasets[dataset]:
            record_id = source_record_id(6, dataset, row)
            party_ids = dedupe([str(row[field]) for field in ("party_id", "transferor_party_id", "transferee_party_id") if row.get(field) not in (None, "")])
            trace = _record_trace(6, dataset, row)
            output.append({
                "canonical_transaction_id": f"TXN-{record_id}",
                "source_record_id": record_id,
                "source_dataset": dataset,
                "transaction_type": transaction_type,
                "transaction_level": level,
                "event_ids": trace["event_ids"],
                "party_ids": party_ids,
                "entity_ids": dedupe([party_to_entity[p] for p in party_ids if p in party_to_entity]),
                "evidence_ids": trace["evidence_ids"],
                "pdf_pages": trace["pdf_pages"],
                "printed_pages": trace["printed_pages"],
                "original_excerpts": trace["original_excerpts"],
                "attributes": copy.deepcopy(row),
                "derivation_type": "SOURCE_COPY_AND_EXPLICIT_ID_MAPPING",
                "program_version": __version__,
                "rule_ids": ["S09-B008", "S09-B009"],
                "review_status": trace["source_review_status"],
            })
    return output


def _build_snapshots(stage6: AdaptedStage, party_to_entity: dict[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for dataset in SNAPSHOT_DATASETS:
        for row in stage6.datasets[dataset]:
            record_id = source_record_id(6, dataset, row)
            party_id = row.get("party_id")
            trace = _record_trace(6, dataset, row)
            output.append({
                "canonical_snapshot_record_id": f"SNP-{record_id}",
                "source_record_id": record_id,
                "record_type": "SNAPSHOT" if dataset == "snapshots" else "HOLDING",
                "snapshot_id": row.get("snapshot_id"),
                "party_id": party_id,
                "entity_id": party_to_entity.get(str(party_id)) if party_id else None,
                "event_ids": trace["event_ids"],
                "evidence_ids": trace["evidence_ids"],
                "pdf_pages": trace["pdf_pages"],
                "printed_pages": trace["printed_pages"],
                "original_excerpts": trace["original_excerpts"],
                "attributes": copy.deepcopy(row),
                "derivation_type": "SOURCE_COPY_AND_EXPLICIT_ID_MAPPING",
                "program_version": __version__,
                "rule_ids": ["S09-B010"],
                "review_status": trace["source_review_status"],
            })
    return output


def _build_numeric(stage7: AdaptedStage, reference_catalog: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_values: list[dict[str, Any]] = []
    for row in stage7.datasets["source_values"]:
        ref_info = _resolve_supporting_references(row.get("evidence_ids"), reference_catalog, context_event_id=row.get("event_id"))
        source_values.append({
            "canonical_source_value_id": f"NUMSRC-{row['source_value_id']}",
            "source_value_id": row["source_value_id"],
            "event_id": row.get("event_id"),
            "supporting_references": ref_info,
            "pdf_pages": split_tokens(row.get("pdf_pages")),
            "printed_pages": split_tokens(row.get("printed_pages")),
            "original_excerpt": row.get("original_excerpt"),
            "attributes": copy.deepcopy(row),
            "derivation_type": "SOURCE_COPY_AND_REFERENCE_NORMALIZATION",
            "program_version": __version__,
            "rule_ids": ["S09-B011", "S09-B012"],
            "review_status": row.get("source_verification_status"),
        })

    results = {str(row["validation_id"]): row for row in stage7.datasets["validation_results"]}
    inputs_by_validation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    validation_event = {str(row["validation_id"]): row.get("event_id") for row in stage7.datasets["validation_items"]}
    for row in stage7.datasets["calculation_inputs"]:
        validation_id = str(row["validation_id"])
        input_copy = copy.deepcopy(row)
        input_copy["source_reference_resolution"] = _classify_source_reference(row.get("source_value_id"), reference_catalog, validation_event.get(validation_id))
        input_copy["supporting_references"] = _resolve_supporting_references(row.get("evidence_ids"), reference_catalog, context_event_id=validation_event.get(validation_id))
        inputs_by_validation[validation_id].append(input_copy)

    review_by_validation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stage7.datasets["manual_review_items"]:
        validation_ids = normalize_reference_tokens(row.get("validation_id"))["expanded_tokens"]
        for validation_id in validation_ids:
            item = copy.deepcopy(row)
            event_id = validation_event.get(validation_id)
            item["resolved_validation_id"] = validation_id
            item["supporting_references"] = _resolve_supporting_references(row.get("evidence_ids"), reference_catalog, context_event_id=event_id)
            review_by_validation[validation_id].append(item)

    validations: list[dict[str, Any]] = []
    for item in stage7.datasets["validation_items"]:
        validation_id = str(item["validation_id"])
        validations.append({
            "canonical_validation_id": f"NUM-{validation_id}",
            "validation_id": validation_id,
            "event_id": item.get("event_id"),
            "snapshot_id": item.get("snapshot_id"),
            "item": copy.deepcopy(item),
            "inputs": inputs_by_validation.get(validation_id, []),
            "result": copy.deepcopy(results.get(validation_id)),
            "manual_review_items": review_by_validation.get(validation_id, []),
            "supporting_references": _resolve_supporting_references(item.get("evidence_ids"), reference_catalog, context_event_id=item.get("event_id")),
            "pdf_pages": split_tokens(item.get("pdf_pages")),
            "printed_pages": split_tokens(item.get("printed_pages")),
            "derivation_type": "SOURCE_JOIN_BY_VALIDATION_ID",
            "program_version": __version__,
            "rule_ids": ["S09-B011", "S09-B012", "S09-B013"],
            "review_status": item.get("final_status"),
        })
    return source_values, validations


def _build_pevc(stage8: AdaptedStage, reference_catalog: dict[str, list[str]]) -> dict[str, Any]:
    investments: list[dict[str, Any]] = []
    semantic_variance: list[str] = []
    for row in stage8.datasets["investment_records"]:
        link_value = row.get("stage07_validation_id")
        link_resolution = _classify_source_reference(link_value, reference_catalog, row.get("event_id"))
        if link_value and link_resolution["resolved_type"] == "CALCULATION":
            semantic_variance.append(str(row["investment_record_id"]))
        investments.append({
            "canonical_investment_id": f"PEVC-{row['investment_record_id']}",
            "attributes": copy.deepcopy(row),
            "stage07_or_upstream_link_resolution": link_resolution,
            "supporting_references": _resolve_supporting_references(row.get("evidence_ids"), reference_catalog, context_event_id=row.get("event_id")),
            "derivation_type": "SOURCE_COPY_AND_REFERENCE_NORMALIZATION",
            "program_version": __version__,
            "review_status": row.get("review_status"),
        })
    edges = [{
        "edge_id": row["edge_id"],
        "attributes": copy.deepcopy(row),
        "supporting_references": _resolve_supporting_references(row.get("evidence_id"), reference_catalog, context_event_id=row.get("event_id")),
        "derivation_type": "SOURCE_COPY_AND_REFERENCE_NORMALIZATION",
        "program_version": __version__,
        "review_status": row.get("review_status"),
    } for row in stage8.datasets["path_edges"]]
    final = [{
        "final_record_id": row["final_record_id"],
        "entity_id": row["entity_id"],
        "attributes": copy.deepcopy(row),
        "supporting_references": _resolve_supporting_references(row.get("evidence_ids"), reference_catalog, context_event_id=row.get("first_entry_event_id")),
        "derivation_type": "SOURCE_COPY_AND_REFERENCE_NORMALIZATION",
        "program_version": __version__,
        "review_status": row.get("final_review_conclusion"),
    } for row in stage8.datasets["final_identification"]]
    return {
        "investment_records": investments,
        "path_edges": edges,
        "final_identification": final,
        "review_items": copy.deepcopy(stage8.datasets["review_items"]),
        "semantic_variance_record_ids": sorted(semantic_variance),
    }


def _preferred_reference_type(token: str, types: list[str], *, context: str) -> str | None:
    """Select a deterministic type for a multi-role upstream identifier."""
    available = set(types)
    if context == "supporting":
        # A field explicitly named evidence_ids is authoritative evidence when an
        # evidence record exists, even if a later stage reused the same identifier.
        for candidate in ("EVIDENCE", "EVIDENCE_OR_REVIEW", "NUMERIC_SOURCE_VALUE", "CALCULATION", "NUMERIC_VALIDATION", "NUMERIC_VALIDATION_RESULT"):
            if candidate in available:
                return candidate
    else:
        # source_value_id fields refer to calculation inputs. Prefixes and the
        # upstream type set disambiguate them without name similarity inference.
        if token.startswith("S6-CAL-") and "CALCULATION" in available:
            return "CALCULATION"
        if token.startswith("VAL-") and ("NUMERIC_VALIDATION" in available or "NUMERIC_VALIDATION_RESULT" in available):
            return "NUMERIC_VALIDATION"
        for candidate in ("NUMERIC_SOURCE_VALUE", "CALCULATION", "NUMERIC_VALIDATION", "NUMERIC_VALIDATION_RESULT", "EVIDENCE", "EVIDENCE_OR_REVIEW"):
            if candidate in available:
                return candidate
    return types[0] if len(types) == 1 else ("MULTI_TYPE_REFERENCE" if types else None)


def _classify_source_reference(value: Any, catalog: dict[str, list[str]], context_event_id: str | None) -> dict[str, Any]:
    if value in (None, ""):
        return {"original_value": value, "resolved_id": None, "resolved_type": "NONE", "candidate_types": [], "status": "NOT_APPLICABLE"}
    token = str(value)
    normalized = normalize_reference_tokens(token, context_event_id=context_event_id)
    expanded = normalized["expanded_tokens"]
    if len(expanded) != 1:
        resolutions = []
        for item in expanded:
            types = catalog.get(item, [])
            preferred = _preferred_reference_type(item, types, context="source")
            resolutions.append({"reference_id": item, "reference_type": preferred, "candidate_types": types})
        return {
            "original_value": token,
            "resolved_id": expanded,
            "resolved_type": "RANGE_OR_MULTI_REFERENCE",
            "resolutions": resolutions,
            "status": "RESOLVED" if all(item["reference_type"] for item in resolutions) else "UNRESOLVED",
        }
    candidate = expanded[0]
    types = catalog.get(candidate, [])
    preferred = _preferred_reference_type(candidate, types, context="source")
    if preferred:
        return {"original_value": token, "resolved_id": candidate, "resolved_type": preferred, "candidate_types": types, "status": "RESOLVED"}
    if candidate.startswith("UNIT-CONV-"):
        return {"original_value": token, "resolved_id": candidate, "resolved_type": "CONVERSION_CONSTANT", "candidate_types": [], "status": "RESOLVED_BY_TYPE"}
    if candidate.startswith("S6-SNP-"):
        return {"original_value": token, "resolved_id": candidate, "resolved_type": "SNAPSHOT_DERIVED_VALUE", "candidate_types": [], "status": "RESOLVED_BY_TYPE"}
    return {"original_value": token, "resolved_id": candidate, "resolved_type": "UNKNOWN", "candidate_types": [], "status": "UNRESOLVED"}


def _resolve_supporting_references(value: Any, catalog: dict[str, list[str]], context_event_id: str | None) -> dict[str, Any]:
    normalized = normalize_reference_tokens(value, context_event_id=context_event_id)
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for token in normalized["expanded_tokens"]:
        types = catalog.get(token, [])
        preferred = _preferred_reference_type(token, types, context="supporting")
        if preferred:
            resolved.append({"reference_id": token, "reference_type": preferred, "candidate_types": types})
        else:
            unresolved.append(token)
    return {**normalized, "resolved_references": resolved, "unresolved_tokens": unresolved}


def _dedupe_dicts(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output
