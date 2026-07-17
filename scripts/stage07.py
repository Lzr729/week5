#!/usr/bin/env python3
"""Validate and export the stage 07 numeric-validation bundle."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any


def load_bundle(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


def validate_bundle(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "metadata", "source_values", "validation_items", "calculation_inputs",
        "validation_results", "manual_review_items", "acceptance_checks", "review_log"
    ]
    for key in required:
        if key not in data:
            errors.append(f"missing top-level key: {key}")

    if errors:
        return errors

    metadata = data["metadata"]
    if metadata.get("stage") != 7:
        errors.append("metadata.stage must equal 7")
    if metadata.get("status") != "final_approved":
        errors.append("metadata.status must be final_approved")

    validations = data["validation_items"]
    validation_ids = [row.get("validation_id") for row in validations]
    if len(validation_ids) != len(set(validation_ids)):
        errors.append("validation_id is not unique")
    if len(validations) != 55:
        errors.append(f"expected 55 validation items, got {len(validations)}")

    pending = [
        row.get("validation_id")
        for row in validations
        if row.get("final_status") in (None, "", "待用户复核", "待进一步复核")
    ]
    if pending:
        errors.append(f"unclosed validation items: {pending}")

    inputs = data["calculation_inputs"]
    if len(inputs) != 179:
        errors.append(f"expected 179 calculation inputs, got {len(inputs)}")
    validation_set = set(validation_ids)
    bad_refs = sorted({
        row.get("validation_id") for row in inputs
        if row.get("validation_id") not in validation_set
    })
    if bad_refs:
        errors.append(f"input validation references not found: {bad_refs}")

    results = {row.get("validation_id"): row for row in data["validation_results"]}
    ce005 = results.get("VAL-012")
    if not ce005:
        errors.append("VAL-012 missing")
    else:
        if dec(ce005.get("signed_difference_excel")) != Decimal("0.00574"):
            errors.append("VAL-012 difference must equal 0.00574")
        if ce005.get("final_conclusion") != "确认原文存在差异并保留":
            errors.append("VAL-012 final conclusion is incorrect")

    shares = [
        dec(row["standardized_value"])
        for row in inputs
        if row.get("validation_id") == "VAL-044"
        and str(row.get("input_role", "")).startswith("lot_")
    ]
    prices = [
        dec(row["standardized_value"])
        for row in inputs
        if row.get("validation_id") == "VAL-045"
        and str(row.get("input_role", "")).startswith("lot_")
    ]
    if len(shares) != 10 or sum(shares) != Decimal("1659535"):
        errors.append(f"CE-013 share rows invalid: count={len(shares)}, sum={sum(shares)}")
    if len(prices) != 10 or sum(prices) != Decimal("8563.19"):
        errors.append(f"CE-013 price rows invalid: count={len(prices)}, sum={sum(prices)}")

    review_items = data["manual_review_items"]
    unclosed_reviews = [
        row.get("review_item_id")
        for row in review_items
        if row.get("user_decision") in (None, "", "待用户复核", "待进一步复核")
    ]
    if unclosed_reviews:
        errors.append(f"unclosed manual reviews: {unclosed_reviews}")

    failed_checks = [
        row.get("check_id")
        for row in data["acceptance_checks"]
        if row.get("status") != "通过"
    ]
    if failed_checks:
        errors.append(f"acceptance checks not passed: {failed_checks}")

    counts = metadata.get("record_counts", {})
    actual_counts = {
        "validation_items": len(data["validation_items"]),
        "source_values": len(data["source_values"]),
        "calculation_inputs": len(data["calculation_inputs"]),
        "validation_results": len(data["validation_results"]),
        "manual_review_items": len(data["manual_review_items"]),
        "acceptance_checks": len(data["acceptance_checks"]),
        "review_log": len(data["review_log"]),
    }
    for key, actual in actual_counts.items():
        if counts.get(key) != actual:
            errors.append(f"record_counts.{key}: metadata={counts.get(key)}, actual={actual}")

    return errors


def export_csvs(data: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for key in [
        "source_values", "validation_items", "calculation_inputs",
        "validation_results", "manual_review_items",
        "acceptance_checks", "review_log"
    ]:
        rows = data[key]
        if not rows:
            continue
        fieldnames = list(rows[0].keys())
        with (output / f"{key}.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data" / "stage07_bundle.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    export_parser = sub.add_parser("export-csv")
    export_parser.add_argument("--output", type=Path, default=root / "build" / "csv")
    args = parser.parse_args()

    data = load_bundle(args.data)
    if args.command == "validate":
        errors = validate_bundle(data)
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        counts = data["metadata"]["record_counts"]
        print("PASS: stage07 bundle validated")
        print(json.dumps(counts, ensure_ascii=False, indent=2))
        return 0

    export_csvs(data, args.output)
    print(f"CSV files exported to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
