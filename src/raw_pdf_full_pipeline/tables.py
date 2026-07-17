from __future__ import annotations

from typing import Iterable

from .common import IDX_RE, is_number_token, normalize_name, parse_decimal, decimal_to_json

HEADER_TOKENS = {
    "序号",
    "股东姓名/名称",
    "股东名称",
    "发起人",
    "持股数量",
    "持股数量（股）",
    "持股比例",
    "持股比例（%）",
    "注册资本",
    "注册资本（万元）",
    "出资额",
    "出资额（万元）",
}


def _find_after(lines: list[str], marker: str) -> int | None:
    for i, line in enumerate(lines):
        if marker in line:
            return i + 1
    return None


def parse_two_value_table(
    lines: list[str],
    marker: str,
    stop_markers: Iterable[str] = (),
) -> tuple[list[dict], list[str] | None]:
    start = _find_after(lines, marker)
    if start is None:
        return [], None
    try:
        start = next(i for i in range(start, len(lines)) if lines[i] == "序号") + 1
    except StopIteration:
        return [], None
    while start < len(lines) and not IDX_RE.fullmatch(lines[start]):
        start += 1
    rows: list[dict] = []
    total: list[str] | None = None
    i = start
    stops = tuple(stop_markers)
    while i < len(lines):
        line = lines[i]
        if stops and any(m in line for m in stops):
            break
        if line == "合计":
            vals: list[str] = []
            j = i + 1
            while j < len(lines) and len(vals) < 2:
                if is_number_token(lines[j]):
                    vals.append(lines[j])
                elif stops and any(m in lines[j] for m in stops):
                    break
                j += 1
            total = vals or None
            break
        if line == "序号":
            i += 1
            while i < len(lines) and not IDX_RE.fullmatch(lines[i]):
                i += 1
            continue
        if IDX_RE.fullmatch(line):
            index = int(line)
            i += 1
            name_parts: list[str] = []
            while i < len(lines) and not is_number_token(lines[i]):
                if lines[i] in HEADER_TOKENS or lines[i] == "序号":
                    i += 1
                    continue
                if stops and any(m in lines[i] for m in stops):
                    return rows, total
                name_parts.append(lines[i])
                i += 1
            if i >= len(lines):
                break
            amount_text = lines[i]
            i += 1
            while i < len(lines) and not is_number_token(lines[i]):
                if lines[i] in HEADER_TOKENS:
                    i += 1
                    continue
                break
            percentage_text = lines[i] if i < len(lines) and is_number_token(lines[i]) else None
            if percentage_text is not None:
                i += 1
            rows.append(
                {
                    "row_index": index,
                    "shareholder_original_name": normalize_name(" ".join(name_parts)),
                    "holding_value": decimal_to_json(parse_decimal(amount_text)),
                    "holding_percentage": decimal_to_json(parse_decimal(percentage_text)),
                }
            )
            continue
        i += 1
    return rows, total


def parse_pre_post_table(lines: list[str], marker: str) -> tuple[list[dict], list[str] | None]:
    start = _find_after(lines, marker)
    if start is None:
        return [], None
    try:
        start = next(i for i in range(start, len(lines)) if lines[i] == "序号") + 1
    except StopIteration:
        return [], None
    while start < len(lines) and not IDX_RE.fullmatch(lines[start]):
        start += 1
    headers = HEADER_TOKENS | {"发行前", "发行后", "持股数", "（股）", "（%）"}
    rows: list[dict] = []
    total: list[str] | None = None
    i = start
    while i < len(lines):
        line = lines[i]
        if line == "合计":
            vals: list[str] = []
            i += 1
            while i < len(lines) and len(vals) < 4:
                if is_number_token(lines[i]):
                    vals.append(lines[i])
                i += 1
            total = vals or None
            break
        if line == "序号":
            i += 1
            while i < len(lines) and not IDX_RE.fullmatch(lines[i]):
                i += 1
            continue
        if IDX_RE.fullmatch(line):
            index = int(line)
            i += 1
            name_parts: list[str] = []
            while i < len(lines) and not is_number_token(lines[i]):
                if lines[i] in headers:
                    i += 1
                    continue
                name_parts.append(lines[i])
                i += 1
            numbers: list[str] = []
            while i < len(lines) and len(numbers) < 4:
                if is_number_token(lines[i]):
                    numbers.append(lines[i])
                    i += 1
                elif lines[i] in headers:
                    i += 1
                else:
                    break
            if len(numbers) == 4:
                rows.append(
                    {
                        "row_index": index,
                        "shareholder_original_name": normalize_name(" ".join(name_parts)),
                        "holding_value": decimal_to_json(parse_decimal(numbers[0])),
                        "holding_percentage": decimal_to_json(parse_decimal(numbers[1])),
                        "post_holding_value": decimal_to_json(parse_decimal(numbers[2])),
                        "post_holding_percentage": decimal_to_json(parse_decimal(numbers[3])),
                    }
                )
            continue
        i += 1
    return rows, total
