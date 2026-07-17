from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF = re.compile(r"([A-Z]+)(\d+)")


def read_xlsx_tables(data: bytes, sheet_names: list[str]) -> dict[str, list[dict[str, Any]]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        _check_safe(archive)
        shared_strings = _read_shared_strings(archive)
        sheet_paths = _sheet_paths(archive)
        output: dict[str, list[dict[str, Any]]] = {}
        for sheet_name in sheet_names:
            if sheet_name not in sheet_paths:
                raise KeyError(f"Worksheet not found: {sheet_name}")
            rows = _read_sheet_rows(archive, sheet_paths[sheet_name], shared_strings)
            output[sheet_name] = _rows_to_records(rows)
        return output


def _check_safe(archive: zipfile.ZipFile) -> None:
    unsafe = []
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if info.filename.startswith("/") or ".." in path.parts:
            unsafe.append(info.filename)
    if unsafe:
        raise ValueError(f"Unsafe XLSX member paths: {unsafe}")


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall(f"{{{_MAIN}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{_MAIN}}}t")))
    return values


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{_PKG_REL}}}Relationship")
    }
    output: dict[str, str] = {}
    for sheet in workbook.findall(f".//{{{_MAIN}}}sheet"):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{_REL}}}id"]
        target = targets[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        output[name] = _normalize_posix(target)
    return output


def _normalize_posix(path: str) -> str:
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def _read_sheet_rows(archive: zipfile.ZipFile, path: str, shared: list[str]) -> list[list[Any]]:
    root = ET.fromstring(archive.read(path))
    rows: list[list[Any]] = []
    for row in root.findall(f".//{{{_MAIN}}}sheetData/{{{_MAIN}}}row"):
        cells: dict[int, Any] = {}
        for cell in row.findall(f"{{{_MAIN}}}c"):
            ref = cell.attrib.get("r")
            if not ref:
                continue
            match = _CELL_REF.fullmatch(ref)
            if not match:
                continue
            column = _column_index(match.group(1))
            cells[column] = _cell_value(cell, shared)
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(index) for index in range(width)])
        else:
            rows.append([])
    return rows


def _cell_value(cell: ET.Element, shared: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{_MAIN}}}t"))
    value_node = cell.find(f"{{{_MAIN}}}v")
    if value_node is None or value_node.text is None:
        return None
    text = value_node.text
    if cell_type == "s":
        return shared[int(text)]
    if cell_type == "b":
        return text == "1"
    if cell_type in ("str", "e"):
        return text
    return _parse_number(text)


def _parse_number(text: str) -> int | float | str:
    try:
        if re.fullmatch(r"[-+]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return text


def _column_index(letters: str) -> int:
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - 64)
    return value - 1


def _rows_to_records(rows: list[list[Any]]) -> list[dict[str, Any]]:
    nonempty = [row for row in rows if any(value not in (None, "") for value in row)]
    if not nonempty:
        return []
    headers = [str(value).strip() if value not in (None, "") else "" for value in nonempty[0]]
    while headers and not headers[-1]:
        headers.pop()
    if not headers or any(not header for header in headers):
        raise ValueError(f"Blank or invalid header row: {headers}")
    if len(headers) != len(set(headers)):
        raise ValueError(f"Duplicate headers: {headers}")
    records: list[dict[str, Any]] = []
    for row in nonempty[1:]:
        values = list(row[: len(headers)]) + [None] * max(0, len(headers) - len(row))
        record = {headers[index]: values[index] for index in range(len(headers))}
        if any(value not in (None, "") for value in record.values()):
            records.append(record)
    return records
