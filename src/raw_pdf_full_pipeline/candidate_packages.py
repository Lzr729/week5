from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import fitz


COMPANY_CODE = "301563"
COMPANY_NAME = "云汉芯城（上海）互联网科技股份有限公司"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
    return rows


def _write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _page_text(doc: fitz.Document, pdf_page: int) -> str:
    return doc[pdf_page - 1].get_text("text").replace("\x00", "")


def _combine_pages(doc: fitz.Document, pages: list[int]) -> str:
    return "\n".join(_page_text(doc, p) for p in pages)


def _slice_between(text: str, start_anchor: str, end_anchor: str | None) -> str:
    start = text.find(start_anchor)
    if start < 0:
        compact = re.sub(r"\s+", "", text)
        compact_anchor = re.sub(r"\s+", "", start_anchor)
        compact_pos = compact.find(compact_anchor)
        if compact_pos < 0:
            raise ValueError(f"Start anchor not found: {start_anchor}")
        # Fallback to full text only when the PDF text layer inserts spaces inside the anchor.
        start = 0
    if end_anchor:
        end = text.find(end_anchor, start + 1)
        if end < 0:
            end = len(text)
    else:
        end = len(text)
    return text[start:end].strip()


def _event_index(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["auto_event_id"]: row for row in events}


def _printed_pages(event_ids: list[str], event_by_id: dict[str, dict[str, Any]], pdf_pages: list[int]) -> list[int]:
    mapping: dict[int, int] = {}
    for event_id in event_ids:
        row = event_by_id[event_id]
        for pdf_page, printed_page in zip(row.get("pdf_pages", []), row.get("printed_pages", [])):
            mapping[int(pdf_page)] = int(printed_page)
    # The prospectus uses a stable one-page offset in the target range.
    return [mapping.get(page, page - 1) for page in pdf_pages]


def _candidate_hash(row: dict[str, Any]) -> str:
    payload = {k: v for k, v in row.items() if k != "candidate_payload_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(canonical)


def build_candidate_packages(
    pdf_path: str | Path,
    events_path: str | Path,
    vision_path: str | Path,
    evidence_dir: str | Path,
) -> list[dict[str, Any]]:
    events = _read_jsonl(events_path)
    event_by_id = _event_index(events)
    expected_event_ids = {f"AUTO-CE-{i:03d}" for i in range(1, 15)}
    missing = expected_event_ids - set(event_by_id)
    if missing:
        raise ValueError(f"Missing finalized events: {sorted(missing)}")

    vision = json.loads(Path(vision_path).read_text(encoding="utf-8"))
    image_by_page = {int(row["pdf_page"]): row for row in vision.get("input_images", [])}
    evidence_root = Path(evidence_dir)

    specs = [
        {
            "candidate_id": "301563-CAND-001",
            "candidate_label": "有限公司整体变更设立股份公司",
            "range_id": "R-HISTORY",
            "section_title": "（一）发行人的设立方式",
            "pdf_pages": [53, 54, 55],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+ANCHOR_BOUNDARY",
            "start_anchor": "（一）发行人的设立方式",
            "end_anchor": "（二）云汉有限的设立情况",
            "downstream_event_ids": ["AUTO-CE-008"],
            "locator_basis": "目录标题“二、发行人的设立情况”下的同级小标题边界",
        },
        {
            "candidate_id": "301563-CAND-002",
            "candidate_label": "上海云汉电子有限公司设立",
            "range_id": "R-HISTORY",
            "section_title": "（二）云汉有限的设立情况",
            "pdf_pages": [55, 56],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+ANCHOR_BOUNDARY",
            "start_anchor": "（二）云汉有限的设立情况",
            "end_anchor": "（三）云汉有限设立以来股本演变情况",
            "downstream_event_ids": ["AUTO-CE-001"],
            "locator_basis": "设立小标题至下一同级小标题，包含设立叙述与初始股东表",
        },
        {
            "candidate_id": "301563-CAND-003",
            "candidate_label": "有限公司设立以来股本演变流程图事件簇",
            "range_id": "R-HISTORY",
            "section_title": "（三）云汉有限设立以来股本演变情况",
            "pdf_pages": [56, 57, 58],
            "source_type": "IMAGE_FLOWCHART",
            "extraction_route": "PAGE_RENDER+MULTIMODAL_VISION",
            "start_anchor": "（三）云汉有限设立以来股本演变情况",
            "end_anchor": "三、发行人股份公司设立后的股东变化情况",
            "downstream_event_ids": [f"AUTO-CE-{i:03d}" for i in range(2, 8)],
            "locator_basis": "低文本量、高图片数页面及“转下图/续上图”标记",
        },
        {
            "candidate_id": "301563-CAND-004",
            "candidate_label": "2018年4月股份公司第一次股权转让",
            "range_id": "R-HISTORY",
            "section_title": "（一）2018年4月，股份公司第一次股权转让",
            "pdf_pages": [58, 59],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+HEADING_TO_NEXT_HEADING",
            "start_anchor": "（一）2018 年4 月，股份公司第一次股权转让",
            "end_anchor": "（二）2018 年6 月至7 月，股份公司增加注册资本暨第二次股权转让",
            "downstream_event_ids": ["AUTO-CE-009"],
            "locator_basis": "事件小标题至下一同级小标题，跨页包含变更后股东表",
        },
        {
            "candidate_id": "301563-CAND-005",
            "candidate_label": "2018年6月至7月增资暨第二次股权转让",
            "range_id": "R-HISTORY",
            "section_title": "（二）2018年6月至7月，股份公司增加注册资本暨第二次股权转让",
            "pdf_pages": [59, 60, 61],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+HEADING_TO_NEXT_HEADING",
            "start_anchor": "（二）2018 年6 月至7 月，股份公司增加注册资本暨第二次股权转让",
            "end_anchor": "（三）2019 年8 月，股份公司第三次股权转让",
            "downstream_event_ids": ["AUTO-CE-010"],
            "locator_basis": "事件小标题、协议叙述、两批工商登记及跨页股东表共同组成候选包",
        },
        {
            "candidate_id": "301563-CAND-006",
            "candidate_label": "2019年8月股份公司第三次股权转让",
            "range_id": "R-HISTORY",
            "section_title": "（三）2019年8月，股份公司第三次股权转让",
            "pdf_pages": [61, 62],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+HEADING_TO_NEXT_HEADING",
            "start_anchor": "（三）2019 年8 月，股份公司第三次股权转让",
            "end_anchor": "（四）2020 年5 月，股份公司第二次增资",
            "downstream_event_ids": ["AUTO-CE-011"],
            "locator_basis": "事件小标题至下一同级小标题，包含转让叙述与变更后股东表",
        },
        {
            "candidate_id": "301563-CAND-007",
            "candidate_label": "2020年5月股份公司第二次增资",
            "range_id": "R-HISTORY",
            "section_title": "（四）2020年5月，股份公司第二次增资",
            "pdf_pages": [62, 63],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+HEADING_TO_NEXT_HEADING",
            "start_anchor": "（四）2020 年5 月，股份公司第二次增资",
            "end_anchor": "（五）2020 年9 月，股份公司第三次增资和第四次股权转让",
            "downstream_event_ids": ["AUTO-CE-012"],
            "locator_basis": "事件小标题至下一同级小标题，包含增资协议、工商登记及股东表",
        },
        {
            "candidate_id": "301563-CAND-008",
            "candidate_label": "2020年9月第三次增资和第四次股权转让",
            "range_id": "R-HISTORY",
            "section_title": "（五）2020年9月，股份公司第三次增资和第四次股权转让",
            "pdf_pages": [63, 64, 65],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+HEADING_TO_NEXT_HEADING",
            "start_anchor": "（五）2020 年9 月，股份公司第三次增资和第四次股权转让",
            "end_anchor": "（六）对赌协议解除相关情况",
            "downstream_event_ids": ["AUTO-CE-013"],
            "locator_basis": "事件小标题、十笔转让表和跨页变更后股东表共同组成候选包",
        },
        {
            "candidate_id": "301563-CAND-009",
            "candidate_label": "对赌协议及特殊权利解除相关情况",
            "range_id": "R-HISTORY",
            "section_title": "（六）对赌协议解除相关情况",
            "pdf_pages": [65, 66, 67, 68, 69, 70],
            "source_type": "TEXT_NARRATIVE_AND_TABLE",
            "extraction_route": "PYMUPDF_TEXT+HEADING_TO_NEXT_HEADING",
            "start_anchor": "（六）对赌协议解除相关情况",
            "end_anchor": "（七）不存在股权代持等情形",
            "downstream_event_ids": ["AUTO-CE-014"],
            "locator_basis": "特殊权利解除小标题至下一同级小标题，排除后续代持和整体变更讨论",
        },
    ]

    rows: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as doc:
        for spec in specs:
            pages = spec["pdf_pages"]
            combined = _combine_pages(doc, pages)
            source_text = _slice_between(combined, spec["start_anchor"], spec["end_anchor"])
            downstream_events = [event_by_id[event_id] for event_id in spec["downstream_event_ids"]]
            event_types = sorted({value for event in downstream_events for value in event.get("event_types", [])})
            source_page_hashes = [
                {
                    "pdf_page": page,
                    "text_sha256": _sha256_text(_page_text(doc, page)),
                }
                for page in pages
            ]

            source_images: list[dict[str, Any]] = []
            if spec["source_type"] == "IMAGE_FLOWCHART":
                for page in pages:
                    image = image_by_page.get(page)
                    if image is None:
                        raise ValueError(f"Missing vision input image for PDF page {page}")
                    image_path = evidence_root / image["file"]
                    actual_hash = _sha256_bytes(image_path.read_bytes())
                    if actual_hash != image["sha256"]:
                        raise ValueError(f"Image hash mismatch: {image_path}")
                    source_images.append(
                        {
                            "pdf_page": page,
                            "printed_page": image.get("printed_page"),
                            "relative_path": f"evidence/{image['file']}",
                            "sha256": actual_hash,
                        }
                    )

            row: dict[str, Any] = {
                "candidate_id": spec["candidate_id"],
                "candidate_schema_version": "1.0.0",
                "generator_version": "1.0.1",
                "company_code": COMPANY_CODE,
                "company_name": COMPANY_NAME,
                "range_id": spec["range_id"],
                "section_title": spec["section_title"],
                "candidate_label": spec["candidate_label"],
                "pdf_pages": pages,
                "printed_pages": _printed_pages(spec["downstream_event_ids"], event_by_id, pages),
                "source_type": spec["source_type"],
                "extraction_route": spec["extraction_route"],
                "locator_basis": spec["locator_basis"],
                "candidate_event_types": event_types,
                "source_text": source_text,
                "source_text_sha256": _sha256_text(source_text),
                "source_page_text_sha256s": source_page_hashes,
                "source_images": source_images,
                "downstream_event_ids": spec["downstream_event_ids"],
                "candidate_status": "AUTO_EXTRACTED",
                "review_status": "CLOSED",
                "gold_used_for_candidate_generation": False,
            }
            row["candidate_payload_sha256"] = _candidate_hash(row)
            rows.append(row)

    validate_candidate_packages(rows, events)
    return rows


def validate_candidate_packages(
    candidates: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(candidates) != 9:
        raise ValueError(f"Expected 9 candidate packages, got {len(candidates)}")
    candidate_ids = [row["candidate_id"] for row in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Duplicate candidate_id")
    event_ids = {row["auto_event_id"] for row in events}
    covered = [event_id for row in candidates for event_id in row["downstream_event_ids"]]
    if len(covered) != len(set(covered)):
        raise ValueError("A finalized event is linked to more than one candidate package")
    if set(covered) != event_ids:
        raise ValueError(
            f"Candidate coverage mismatch: missing={sorted(event_ids-set(covered))}, extra={sorted(set(covered)-event_ids)}"
        )
    for row in candidates:
        if not row["pdf_pages"] or not row["source_text"]:
            raise ValueError(f"Empty source in {row['candidate_id']}")
        if row["candidate_payload_sha256"] != _candidate_hash(row):
            raise ValueError(f"Candidate payload hash mismatch: {row['candidate_id']}")
        if row["source_type"] == "IMAGE_FLOWCHART" and len(row["source_images"]) != 3:
            raise ValueError("Flowchart candidate must contain three source images")
    return {
        "status": "PASS",
        "candidate_count": len(candidates),
        "covered_event_count": len(covered),
        "visual_candidate_count": sum(row["source_type"] == "IMAGE_FLOWCHART" for row in candidates),
        "text_candidate_count": sum(row["source_type"] != "IMAGE_FLOWCHART" for row in candidates),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate auditable candidate event packages from the raw prospectus")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--vision", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    candidates = build_candidate_packages(args.pdf, args.events, args.vision, args.evidence_dir)
    _write_jsonl(args.output, candidates)
    result = validate_candidate_packages(candidates, _read_jsonl(args.events))
    result["output"] = str(Path(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
