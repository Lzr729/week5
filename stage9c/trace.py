from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

TOKEN_SPLIT_RE = re.compile(r"[｜|；;、,，]+")


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def as_tokens(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(as_tokens(item))
        return dedupe(result)
    return dedupe([part.strip() for part in TOKEN_SPLIT_RE.split(str(value)) if part.strip()])


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def evidence_lookup(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["evidence_id"]): row for row in model.get("canonical_evidence", [])}


def trace_from_evidence(model: dict[str, Any], evidence_ids: Iterable[str]) -> dict[str, list[str]]:
    lookup = evidence_lookup(model)
    ids = dedupe(str(x) for x in evidence_ids if x)
    pages: list[str] = []
    printed: list[str] = []
    excerpts: list[str] = []
    for evidence_id in ids:
        row = lookup.get(evidence_id)
        if not row:
            continue
        pages.extend(str(x) for x in row.get("pdf_pages", []) if x not in (None, ""))
        printed.extend(str(x) for x in row.get("printed_pages", []) if x not in (None, ""))
        excerpts.extend(str(x) for x in row.get("original_excerpts", []) if x not in (None, ""))
    return {
        "evidence_ids": ids,
        "pdf_pages": dedupe(pages),
        "printed_pages": dedupe(printed),
        "original_excerpts": dedupe(excerpts),
    }


def event_ids_from_record(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("event_ids", "event_id", "first_entry_event_id", "last_exit_event_id"):
        values.extend(as_tokens(record.get(key)))
    attrs = record.get("attributes") or {}
    for key in ("event_id", "parent_event_id", "first_entry_event_id", "last_exit_event_id", "investment_event_ids"):
        values.extend(as_tokens(attrs.get(key)))
    return dedupe(values)


def evidence_ids_from_record(record: dict[str, Any]) -> list[str]:
    values = as_tokens(record.get("evidence_ids"))
    attrs = record.get("attributes") or {}
    values.extend(as_tokens(attrs.get("evidence_ids")))
    values.extend(as_tokens(attrs.get("evidence_id")))
    supporting = record.get("supporting_references") or {}
    values.extend(str(x) for x in supporting.get("expanded_tokens", []) if x)
    return dedupe(values)
