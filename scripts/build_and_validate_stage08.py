#!/usr/bin/env python3
"""阶段八 PE/VC 主体及投资路径数据校验脚本。

仅使用 Python 标准库。默认校验 ../data/stage08_pevc_investment_paths.json。
不会连接外部数据库，也不会补充招股说明书未披露的信息。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def duplicate_values(values: list[str]) -> list[str]:
    counts = Counter(v for v in values if v)
    return sorted(v for v, count in counts.items() if count > 1)


def split_refs(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    text = str(value)
    for sep in ("｜", "；", ",", "，"):
        text = text.replace(sep, "|")
    return [part.strip() for part in text.split("|") if part.strip()]


def validate(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    metadata = data.get("metadata", {})
    entities = data.get("entities", [])
    investments = data.get("investment_records", [])
    edges = data.get("path_edges", [])
    evidence = data.get("evidence", [])
    reviews = data.get("review_items", [])
    qa_results = data.get("qa_results", [])

    if metadata.get("stage_status") != "FINAL_APPROVED":
        errors.append("metadata.stage_status 不是 FINAL_APPROVED。")

    entity_ids = [str(x.get("entity_id") or "") for x in entities]
    investment_ids = [str(x.get("investment_record_id") or "") for x in investments]
    edge_ids = [str(x.get("edge_id") or "") for x in edges]
    evidence_ids = [str(x.get("evidence_id") or "") for x in evidence]

    for label, ids in (
        ("entity_id", entity_ids),
        ("investment_record_id", investment_ids),
        ("edge_id", edge_ids),
        ("evidence_id", evidence_ids),
    ):
        blanks = sum(1 for x in ids if not x)
        dups = duplicate_values(ids)
        if blanks:
            errors.append(f"{label} 有 {blanks} 个空值。")
        if dups:
            errors.append(f"{label} 重复：{dups}")

    entity_set = set(entity_ids)
    evidence_set = set(evidence_ids)

    for inv in investments:
        inv_id = inv.get("investment_record_id")
        if inv.get("investor_entity_id") not in entity_set:
            errors.append(f"{inv_id}: investor_entity_id 不存在于主体主表。")
        if inv.get("investment_level") not in {"DIRECT", "INDIRECT"}:
            errors.append(f"{inv_id}: investment_level 非法或为空。")
        if inv.get("entry_method") not in {"CAPITAL_INCREASE", "SHARE_TRANSFER", "OTHER"}:
            errors.append(f"{inv_id}: entry_method 非法或为空。")
        if inv.get("value_type") == "NOT_DISCLOSED" and inv.get("cash_or_consideration_value") not in (None, ""):
            errors.append(f"{inv_id}: 未披露价款记录被填写了价款。")
        for ref in split_refs(inv.get("evidence_ids")):
            if ref not in evidence_set:
                warnings.append(f"{inv_id}: 证据引用 {ref} 未在证据表中找到。")

    for edge in edges:
        edge_id = edge.get("edge_id")
        if edge.get("upstream_entity_id") not in entity_set:
            errors.append(f"{edge_id}: upstream_entity_id 不存在。")
        if edge.get("downstream_entity_id") not in entity_set:
            errors.append(f"{edge_id}: downstream_entity_id 不存在。")
        relationship = str(edge.get("relationship_type") or "")
        if "GENERAL_PARTNER" in relationship and edge.get("path_forming_flag") != "否":
            errors.append(f"{edge_id}: GP关系不得默认形成发行人权益路径。")

    for ent in entities:
        if ent.get("pevc_status") == "CONFIRMED":
            if ent.get("confidence") != "HIGH":
                errors.append(f"{ent.get('entity_id')}: CONFIRMED 但置信度不是 HIGH。")
            if not ent.get("evidence_ids"):
                errors.append(f"{ent.get('entity_id')}: CONFIRMED 但缺少证据。")

    open_reviews = [x.get("review_id") for x in reviews if x.get("status") != "已关闭"]
    if open_reviews:
        errors.append(f"仍有未关闭复核项：{open_reviews}")

    failed_qa = [x.get("check_id") for x in qa_results if x.get("result") != "PASS"]
    if failed_qa:
        errors.append(f"质量检查未通过：{failed_qa}")

    # These are expected unknowns, not errors.
    unresolved = [x.get("entity_id") for x in entities if x.get("pevc_status") == "UNRESOLVED"]
    candidates = [x.get("entity_id") for x in entities if x.get("pevc_status") == "CANDIDATE"]
    if unresolved:
        warnings.append(f"保留 UNRESOLVED 主体：{unresolved}")
    if candidates:
        warnings.append(f"保留 CANDIDATE 主体：{candidates}")

    return errors, warnings


def main() -> int:
    default_path = Path(__file__).resolve().parents[1] / "data" / "stage08_pevc_investment_paths.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=default_path, help="阶段八 JSON 文件路径")
    args = parser.parse_args()

    data = load_json(args.json)
    errors, warnings = validate(data)

    summary = data.get("metadata", {}).get("summary", {})
    print("Stage 08 validation summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"- {item}")

    if errors:
        print("\nErrors:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("\nPASS: 阶段八JSON结构、引用关系、复核闭环和核心业务规则校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
