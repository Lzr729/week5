from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .archive_io import SafeArchive, sha256_bytes
from .xlsx_reader import read_xlsx_tables

LIST_DELIMITER_RE = re.compile(r"[｜|；;，,]+")
NOT_APPLICABLE = {"不适用", "N/A", "NA", "not applicable"}
CE_EVENT_RE = re.compile(r"^CE-\d{3}(?:-(?:\d{2}|A|B|C|D|DPLUS))?$")
SHORT_VALUE_RE = re.compile(r"^V\d+$")

ID_FIELDS: dict[int, dict[str, str]] = {
    1: {"pdf_metadata": "record_id", "evidence": "evidence_id"},
    2: {"sections": "section_id", "evidence": "evidence_id"},
    3: {
        "candidate_events": "event_id",
        "flowchart_nodes": "flow_node_id",
        "auxiliary_findings": "finding_id",
        "evidence": "evidence_id",
    },
    4: {
        "event_master": "event_id",
        "participants": "participant_id",
        "evidence": "evidence_id",
        "source_values": "value_id",
        "review_checks": "event_id",
    },
    5: {
        "equity_timeline": "timeline_id",
        "time_nodes": "time_node_id",
        "calculations": "calculation_id",
        "exclusions": "record_id",
        "auxiliaries": "record_id",
        "review_items": "review_item_id",
        "acceptance_checks": "timeline_id",
    },
    6: {
        "parties": "party_id",
        "increase_events": "increase_id",
        "subscriptions": "subscription_id",
        "transfer_events": "transfer_event_id",
        "transfer_lots": "transfer_lot_id",
        "snapshots": "snapshot_id",
        "snapshot_holdings": "snapshot_holding_id",
        "calculations": "calculation_id",
        "evidence_reviews": "record_id",
        "acceptance_checks": "check_id",
        "audit_log": "issue_id",
    },
    7: {
        "source_values": "source_value_id",
        "validation_items": "validation_id",
        "calculation_inputs": "input_id",
        "validation_results": "validation_id",
        "manual_review_items": "review_item_id",
        "acceptance_checks": "check_id",
        "review_log": "log_id",
    },
    8: {
        "entities": "entity_id",
        "name_mappings": "name_record_id",
        "investment_records": "investment_record_id",
        "path_edges": "edge_id",
        "evidence": "evidence_id",
        "review_items": "review_id",
        "qa_results": "check_id",
        "final_identification": "final_record_id",
    },
}

EVENT_FIELDS = (
    "event_id",
    "parent_event_id",
    "linked_event_id",
    "linked_record_ids",
    "first_event_id",
    "last_event_id",
    "related_event_id",
    "trigger_event_id",
    "source_event_id",
    "event_or_snapshot_id",
    "first_entry_event_id",
    "last_exit_event_id",
    "valid_from_event_id",
    "valid_to_event_id",
    "investment_event_ids",
)
EVIDENCE_FIELDS = (
    "evidence_ids",
    "evidence_id",
    "related_evidence",
    "conflicting_or_supporting_evidence_ids",
)
PDF_PAGE_FIELDS = ("pdf_pages", "pdf_page", "pdf_start_page", "pdf_end_page")
PRINTED_PAGE_FIELDS = ("printed_pages", "printed_page", "printed_start_page", "printed_end_page")
EXCERPT_FIELDS = (
    "original_quote",
    "original_excerpt",
    "core_original_excerpt",
    "original_evidence_or_issue",
    "original_quote_or_description",
    "original_text_or_description",
    "evidence_excerpt",
    "detail_evidence_excerpt",
    "node_label_original",
)
REVIEW_FIELDS = (
    "review_status",
    "review_decision",
    "verification_status",
    "final_status",
    "final_conclusion",
    "acceptance_status",
    "overall_check_status",
    "status",
    "user_decision",
)


@dataclass(frozen=True)
class AdaptedStage:
    source_stage: int
    metadata: dict[str, Any]
    datasets: dict[str, list[dict[str, Any]]]


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON value must be an object")
    return data


def extract_datasets(stage: int, data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if stage == 6:
        tables = data.get("tables")
        if not isinstance(tables, dict):
            raise ValueError("Stage 6 bundle must contain an object named 'tables'")
        datasets = {name: rows for name, rows in tables.items() if isinstance(rows, list)}
    else:
        datasets = {name: rows for name, rows in data.items() if isinstance(rows, list)}
    _check_dataset_names(stage, datasets)
    return datasets


def adapt_stage(stage: int, path: str | Path) -> AdaptedStage:
    """Backward-compatible JSON adapter used by unit fixtures for stages 6-8."""
    data = load_json(path)
    return AdaptedStage(
        source_stage=stage,
        metadata=copy.deepcopy(data.get("metadata", {})),
        datasets=copy.deepcopy(extract_datasets(stage, data)),
    )


def adapt_package(stage: int, path: str | Path) -> AdaptedStage:
    file_path = Path(path)
    if stage in (6, 7, 8) and file_path.suffix.lower() == ".json":
        return adapt_stage(stage, file_path)
    if file_path.suffix.lower() != ".zip":
        raise ValueError(f"Stage {stage} expects a ZIP package or a supported direct JSON file: {file_path}")
    with SafeArchive(file_path) as archive:
        if stage == 1:
            return _adapt_stage1(archive)
        if stage == 2:
            return _adapt_stage2(archive)
        if stage == 3:
            return _adapt_stage3(archive)
        if stage == 4:
            return _adapt_stage4(archive)
        if stage == 5:
            return _adapt_stage5(archive)
        if stage == 6:
            return _adapt_stage6(archive)
        if stage == 7:
            return _adapt_stage7(archive)
        if stage == 8:
            return _adapt_stage8(archive)
    raise ValueError(f"Unsupported stage: {stage}")


def _adapt_stage1(archive: SafeArchive) -> AdaptedStage:
    metadata = archive.read_json("data/pdf_metadata.json")
    status = archive.read_json("data/stage_status.json")
    audit = archive.verify_sha256s("SHA256SUMS.txt")
    pdf_record = copy.deepcopy(metadata)
    pdf_record["record_id"] = "S01-PDF-META-001"
    evidence = [row for row in archive.read_csv("evidence/evidence_index.csv") if str(row.get("stage")) == "1"]
    datasets = {"pdf_metadata": [pdf_record], "evidence": evidence}
    _check_dataset_names(1, datasets)
    return AdaptedStage(1, {"pdf_metadata": metadata, "stage_status": status, "package_audit": audit}, datasets)


def _adapt_stage2(archive: SafeArchive) -> AdaptedStage:
    status = archive.read_json("data/stage_status.json")
    audit = archive.verify_sha256s("SHA256SUMS.txt")
    sections = archive.read_csv("data/section_index.csv")
    evidence = [row for row in archive.read_csv("evidence/evidence_index.csv") if str(row.get("stage")) == "2"]
    datasets = {"sections": sections, "evidence": evidence}
    _check_dataset_names(2, datasets)
    return AdaptedStage(2, {"stage_status": status, "package_audit": audit}, datasets)


def _adapt_stage3(archive: SafeArchive) -> AdaptedStage:
    manifest_audit = archive.verify_manifest_files("metadata/stage3_manifest.json")
    manifest = manifest_audit["manifest"]
    datasets = {
        "candidate_events": archive.read_csv("data/candidate_events.csv"),
        "flowchart_nodes": archive.read_csv("data/flowchart_nodes.csv"),
        "auxiliary_findings": archive.read_csv("data/auxiliary_findings.csv"),
        "evidence": archive.read_csv("evidence/stage3_evidence_index.csv"),
    }
    _check_dataset_names(3, datasets)
    return AdaptedStage(3, {"manifest": manifest, "package_audit": manifest_audit}, datasets)


def _adapt_stage4(archive: SafeArchive) -> AdaptedStage:
    audit = archive.verify_sha256s("metadata/SHA256SUMS.txt")
    xlsx_member = archive.find("data/stage04_CE001_CE014_final_approved.xlsx")
    xlsx_bytes = archive.read_bytes(xlsx_member)
    sheets = read_xlsx_tables(xlsx_bytes, [
        "01_事件主表",
        "02_参与方",
        "03_原文证据",
        "04_原文数值",
        "05_复核清单",
    ])
    datasets = {
        "event_master": sheets["01_事件主表"],
        "participants": sheets["02_参与方"],
        "evidence": sheets["03_原文证据"],
        "source_values": sheets["04_原文数值"],
        "review_checks": sheets["05_复核清单"],
    }
    _check_dataset_names(4, datasets)
    return AdaptedStage(4, {
        "stage_status": "FINAL_APPROVED",
        "package_audit": audit,
        "workbook_member": xlsx_member,
        "workbook_sha256": sha256_bytes(xlsx_bytes),
        "sheet_record_counts": {name: len(rows) for name, rows in datasets.items()},
    }, datasets)


def _adapt_stage5(archive: SafeArchive) -> AdaptedStage:
    audit = archive.verify_manifest_files("manifest.json")
    bundle = archive.read_json("data/json/stage05_bundle.json")
    datasets = {name: copy.deepcopy(bundle[name]) for name in ID_FIELDS[5]}
    _check_dataset_names(5, datasets)
    return AdaptedStage(5, {"bundle_metadata": bundle.get("metadata", {}), "manifest": audit["manifest"], "package_audit": audit}, datasets)


def _adapt_stage6(archive: SafeArchive) -> AdaptedStage:
    audit = archive.verify_manifest_files("manifest.json")
    bundle = archive.read_json("data/stage06_bundle.json")
    datasets = extract_datasets(6, bundle)
    return AdaptedStage(6, {"bundle_metadata": bundle.get("metadata", {}), "manifest": audit["manifest"], "package_audit": audit}, copy.deepcopy(datasets))


def _adapt_stage7(archive: SafeArchive) -> AdaptedStage:
    audit = archive.verify_manifest_files("manifest.json")
    bundle = archive.read_json("data/stage07_bundle.json")
    datasets = extract_datasets(7, bundle)
    return AdaptedStage(7, {"bundle_metadata": bundle.get("metadata", {}), "manifest": audit["manifest"], "package_audit": audit}, copy.deepcopy(datasets))


def _adapt_stage8(archive: SafeArchive) -> AdaptedStage:
    bundle = archive.read_json("data/stage08_pevc_investment_paths.json")
    datasets = extract_datasets(8, bundle)
    workbook = archive.member_info("data/stage08_pevc_investment_paths.xlsx")
    expected_workbook_hash = bundle.get("metadata", {}).get("workbook_sha256")
    audit = {
        "result": "PASS" if workbook.sha256 == expected_workbook_hash else "FAIL",
        "entries": [{
            "declared_path": "data/stage08_pevc_investment_paths.xlsx",
            "archive_member": workbook.name,
            "declared_sha256": expected_workbook_hash,
            "observed_sha256": workbook.sha256,
            "observed_size_bytes": workbook.size_bytes,
            "result": "PASS" if workbook.sha256 == expected_workbook_hash else "FAIL",
        }],
        "issues": [] if workbook.sha256 == expected_workbook_hash else [{"type": "HASH_MISMATCH", "path": workbook.name}],
    }
    return AdaptedStage(8, {"bundle_metadata": bundle.get("metadata", {}), "package_audit": audit}, copy.deepcopy(datasets))


def _check_dataset_names(stage: int, datasets: dict[str, list[dict[str, Any]]]) -> None:
    expected = set(ID_FIELDS[stage])
    actual = set(datasets)
    if actual != expected:
        raise ValueError(f"Stage {stage} dataset mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def split_tokens(value: Any) -> list[str]:
    """Split explicit list delimiters while preserving range notation."""
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(split_tokens(item))
        return dedupe(result)
    text = str(value).strip()
    if not text or text in NOT_APPLICABLE:
        return []
    return dedupe([token.strip() for token in LIST_DELIMITER_RE.split(text) if token.strip()])


def expand_id_range(token: str) -> list[str]:
    """Expand a same-prefix identifier range; return the original token if unsafe."""
    if "—" not in token:
        return [token]
    left, right = token.split("—", 1)
    left_match = re.match(r"^(.*?)(\d+)$", left)
    right_match = re.match(r"^(.*?)(\d+)$", right)
    if not left_match or not right_match:
        return [token]
    left_prefix, left_number = left_match.groups()
    right_prefix, right_number = right_match.groups()
    if right_prefix not in ("", left_prefix):
        return [token]
    start, end = int(left_number), int(right_number)
    if end < start or end - start > 500:
        return [token]
    width = max(len(left_number), len(right_number))
    return [f"{left_prefix}{number:0{width}d}" for number in range(start, end + 1)]


def normalize_reference_tokens(value: Any, *, context_event_id: str | None = None) -> dict[str, list[str]]:
    original = split_tokens(value)
    expanded: list[str] = []
    contextual: list[str] = []
    for token in original:
        items = expand_id_range(token)
        for item in items:
            if SHORT_VALUE_RE.fullmatch(item) and context_event_id and CE_EVENT_RE.fullmatch(context_event_id):
                contextual.append(item)
                expanded.append(f"{context_event_id}-{item}")
            else:
                expanded.append(item)
    return {"original_tokens": original, "expanded_tokens": dedupe(expanded), "contextual_short_tokens": dedupe(contextual)}


def source_record_id(stage: int, dataset: str, record: dict[str, Any]) -> str | None:
    value = record.get(ID_FIELDS[stage][dataset])
    return None if value in (None, "") else str(value)


def collect_tokens(record: dict[str, Any], fields: Iterable[str]) -> list[str]:
    values: list[str] = []
    for field in fields:
        if field in record:
            values.extend(split_tokens(record.get(field)))
    return dedupe(values)


def first_present(record: dict[str, Any], fields: Iterable[str]) -> tuple[str | None, Any]:
    for field in fields:
        if field in record and record.get(field) not in (None, ""):
            return field, record.get(field)
    return None, None


def dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
