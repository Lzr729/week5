#!/usr/bin/env python3
"""Export Stage 05 approved Excel workbook to normalized JSON and CSV.

Only Python standard-library modules are used. The workbook remains the
human-reviewed source of truth; generated JSON/CSV files are derivatives.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS_MAIN = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_DOC = {
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
NS_REL = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

DATE_FIELDS = {"normalized_date", "period_start", "period_end", "review_date"}
MULTI_ID_FIELDS = {
    "time_node_ids", "calculation_ids", "evidence_ids", "value_ids", "source_ids"
}
MULTI_PAGE_FIELDS = {"pdf_pages", "printed_pages"}
MULTI_PERSON_FIELDS = {
    "new_shareholders", "increased_shareholders", "decreased_shareholders",
    "exited_shareholders",
}
BOOL_FIELDS = {"needs_manual_review", "is_primary_display_node"}


def excel_serial_to_iso(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        dt = datetime(1899, 12, 30) + timedelta(days=float(value))
        return dt.date().isoformat()
    return value


def split_multi(value: Any, separator: str) -> list[str]:
    if value in (None, ""):
        return []
    return [part.strip() for part in str(value).split(separator) if part.strip()]


def parse_scalar(text: str | None, cell_type: str | None, shared_strings: list[str]) -> Any:
    if text is None:
        return None
    if cell_type == "s":
        return shared_strings[int(text)]
    if cell_type == "b":
        return text == "1"
    if cell_type in {"str", "inlineStr"}:
        return text
    try:
        number = float(text)
        return int(number) if number.is_integer() else number
    except ValueError:
        return text


def column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    index = 0
    for ch in letters:
        index = index * 26 + ord(ch) - ord("A") + 1
    return index - 1


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for si in root.findall("x:si", NS_MAIN):
        texts = [node.text or "" for node in si.iterfind(".//x:t", NS_MAIN)]
        strings.append("".join(texts))
    return strings


def workbook_sheet_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("r:Relationship", NS_REL)
    }
    result: dict[str, str] = {}
    for sheet in workbook.findall("x:sheets/x:sheet", NS_DOC):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ]
        target = rel_map[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        result[name] = target
    return result


def read_sheet_matrix(zf: zipfile.ZipFile, path: str, shared_strings: list[str]) -> list[list[Any]]:
    root = ET.fromstring(zf.read(path))
    rows: list[list[Any]] = []
    max_col = 0
    parsed: list[dict[int, Any]] = []

    for row_node in root.findall(".//x:sheetData/x:row", NS_MAIN):
        row_values: dict[int, Any] = {}
        for cell in row_node.findall("x:c", NS_MAIN):
            ref = cell.attrib["r"]
            idx = column_index(ref)
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                text = "".join(node.text or "" for node in cell.iterfind(".//x:t", NS_MAIN))
            else:
                value_node = cell.find("x:v", NS_MAIN)
                text = value_node.text if value_node is not None else None
            row_values[idx] = parse_scalar(text, cell_type, shared_strings)
            max_col = max(max_col, idx)
        parsed.append(row_values)

    for row_values in parsed:
        row = [None] * (max_col + 1)
        for idx, value in row_values.items():
            row[idx] = value
        rows.append(row)
    return rows


def records_from_rows(matrix: list[list[Any]], header_row: int, first_data_row: int, last_data_row: int) -> list[dict[str, Any]]:
    headers = matrix[header_row - 1]
    records: list[dict[str, Any]] = []
    for row_num in range(first_data_row, last_data_row + 1):
        row = matrix[row_num - 1]
        record = {
            str(headers[i]): row[i] if i < len(row) else None
            for i in range(len(headers))
            if headers[i] not in (None, "")
        }
        if any(value not in (None, "") for value in record.values()):
            records.append(normalize_record(record))
    return records


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in record.items():
        if key in DATE_FIELDS:
            normalized[key] = excel_serial_to_iso(value)
        elif key in MULTI_ID_FIELDS:
            parts = split_multi(value, "｜")
            if key == "calculation_ids":
                normalized[key] = [m for part in parts for m in re.findall(r"CAL-[0-9]{3}", part)]
            elif key == "time_node_ids":
                normalized[key] = [m for part in parts for m in re.findall(r"TN-[0-9]{3}", part)]
            else:
                normalized[key] = parts
        elif key in MULTI_PAGE_FIELDS:
            normalized[key] = split_multi(value, "｜")
        elif key in MULTI_PERSON_FIELDS:
            normalized[key] = split_multi(value, "；")
        elif key in BOOL_FIELDS:
            if value == "是":
                normalized[key] = True
            elif value == "否":
                normalized[key] = False
            else:
                normalized[key] = value
        else:
            normalized[key] = value
    return normalized


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def flatten_for_csv(value: Any) -> Any:
    if isinstance(value, list):
        return "｜".join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames = list(records[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({k: flatten_for_csv(record.get(k)) for k in fieldnames})


def export(xlsx_path: Path, output_dir: Path) -> dict[str, Any]:
    json_dir = output_dir / "json"
    csv_dir = output_dir / "csv"
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = load_shared_strings(zf)
        sheet_paths = workbook_sheet_paths(zf)
        matrices = {
            name: read_sheet_matrix(zf, path, shared_strings)
            for name, path in sheet_paths.items()
        }

    timeline = records_from_rows(matrices["01_股本变化时间线"], 3, 4, 20)
    time_nodes = records_from_rows(matrices["02_时间节点明细"], 3, 4, 46)
    calculations = records_from_rows(matrices["03_计算值登记"], 3, 4, 19)
    exclusions = records_from_rows(matrices["04_排除项及待复核"], 3, 4, 12)
    auxiliaries = records_from_rows(matrices["04_排除项及待复核"], 15, 16, 17)
    review_items = records_from_rows(matrices["04_排除项及待复核"], 20, 21, 23)
    acceptance_checks = records_from_rows(matrices["05_验收清单"], 3, 4, 20)

    metadata = {
        "project": "招股说明书工程化学习",
        "stock_code": "301563",
        "issuer_short_name": "云汉芯城",
        "stage": 5,
        "stage_name": "股本变化时间线",
        "status": "final_approved",
        "primary_fact_source": "301563云汉芯城招股说明书",
        "structured_source": xlsx_path.name,
        "approval_date": "2026-07-17",
        "data_policy": {
            "original_values_and_calculated_values_separated": True,
            "undisclosed_information_not_invented": True,
            "pdf_and_printed_page_evidence_retained": True,
            "stage_07_validation_pending_for_ce_005": True,
        },
    }

    payloads = {
        "equity_timeline": timeline,
        "time_nodes": time_nodes,
        "calculations": calculations,
        "exclusions": exclusions,
        "auxiliaries": auxiliaries,
        "review_items": review_items,
        "acceptance_checks": acceptance_checks,
    }

    for name, records in payloads.items():
        write_json(json_dir / f"{name}.json", records)
        write_csv(csv_dir / f"{name}.csv", records)

    bundle = {"metadata": metadata, **payloads}
    write_json(json_dir / "stage05_bundle.json", bundle)
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    bundle = export(args.xlsx, args.output_dir)
    print(
        "Export complete:",
        f"{len(bundle['equity_timeline'])} timeline events,",
        f"{len(bundle['time_nodes'])} time nodes,",
        f"{len(bundle['calculations'])} calculations.",
    )


if __name__ == "__main__":
    main()
