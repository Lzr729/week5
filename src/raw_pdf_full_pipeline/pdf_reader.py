from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import fitz

from .common import sha256_text


@dataclass(frozen=True)
class PageRecord:
    pdf_page: int
    printed_page: int | None
    text: str
    text_char_count: int
    image_count: int
    text_layer_status: str
    parser_used: str
    text_sha256: str


def _printed_page(text: str) -> int | None:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for i, line in enumerate(lines[:4]):
        if line.isdigit() and len(line) <= 3:
            try:
                return int(line)
            except ValueError:
                pass
    m = re.search(r"招股说明书\s*\n\s*(\d{1,3})\s*\n", text)
    return int(m.group(1)) if m else None


def read_pdf(path: str | Path) -> tuple[fitz.Document, list[PageRecord]]:
    doc = fitz.open(path)
    rows: list[PageRecord] = []
    for idx, page in enumerate(doc):
        text = page.get_text("text")
        images = page.get_images(full=True)
        n = len(text.strip())
        if n < 90 and images:
            status = "IMAGE_DOMINANT"
        elif n < 300 and images:
            status = "SPARSE_TEXT_WITH_IMAGE"
        elif n:
            status = "TEXT_AVAILABLE"
        else:
            status = "EMPTY"
        rows.append(
            PageRecord(
                pdf_page=idx + 1,
                printed_page=_printed_page(text),
                text=text,
                text_char_count=n,
                image_count=len(images),
                text_layer_status=status,
                parser_used="pymupdf_text",
                text_sha256=sha256_text(text),
            )
        )
    return doc, rows


def page_records_to_dicts(rows: Iterable[PageRecord]) -> list[dict]:
    return [asdict(r) | {"text": None} for r in rows]


def clean_page_lines(text: str, pdf_page: int) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        value = " ".join(raw.strip().split())
        if not value:
            continue
        if "云汉芯城（上海）互联网科技股份有限公司" in value and "招股说明书" in value:
            continue
        out.append(value)
    if out and out[0].isdigit():
        expected = pdf_page - 1
        if abs(int(out[0]) - expected) <= 2:
            out = out[1:]
    return out


def combine_lines(rows: list[PageRecord], start_page: int, end_page: int) -> list[str]:
    lines: list[str] = []
    for p in range(start_page, end_page + 1):
        rec = rows[p - 1]
        lines.extend(clean_page_lines(rec.text, p))
    return lines
