from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

NUM_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
IDX_RE = re.compile(r"^\d+$")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: str | Path, obj: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_decimal(value: str | int | float | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def decimal_to_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def is_number_token(value: str) -> bool:
    return bool(NUM_RE.fullmatch(value.replace(" ", "")))


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def normalize_name(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)
    # Remove line-wrap spaces inside Chinese legal names, while preserving English names.
    value = re.sub(r"(?<=[\u4e00-\u9fff）)])\s+(?=[\u4e00-\u9fff（(])", "", value)
    return value


def comparison_name(value: str) -> str:
    value = normalize_name(value)
    value = value.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s·,，。.;；:：()（）\-—_]", "", value).upper()
