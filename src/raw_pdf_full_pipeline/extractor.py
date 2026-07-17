from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any

import fitz

from .common import decimal_to_json, normalize_name, parse_decimal
from .pdf_reader import PageRecord, combine_lines
from .tables import parse_pre_post_table, parse_two_value_table

HEADING_RE = re.compile(r"^（([一二三四五六七八九十]+)）(.+)$")
DATE_RE = re.compile(r"(?P<year>\d{4})\s*年\s*(?P<m1>\d{1,2})\s*月(?:\s*至\s*(?P<m2>\d{1,2})\s*月)?")


@dataclass
class AutoEvent:
    auto_event_id: str
    event_date_original: str | None
    event_date_normalized: str | None
    event_name: str
    event_types: list[str]
    pdf_pages: list[int]
    printed_pages: list[int]
    evidence_excerpt: str
    extraction_method: str
    review_status: str
    review_reason: str | None
    source_text_sha256s: list[str]


def normalize_date(text: str) -> tuple[str | None, str | None]:
    m = DATE_RE.search(text)
    if not m:
        return None, None
    original = m.group(0).replace(" ", "")
    y, m1, m2 = m.group("year"), int(m.group("m1")), m.group("m2")
    normalized = f"{y}-{m1:02d}" if not m2 else f"{y}-{m1:02d}/{int(m2):02d}"
    return original, normalized


def classify_types(text: str) -> list[str]:
    types: list[str] = []
    if "增资" in text or "增加注册资本" in text:
        types.append("capital_increase")
    if "股权转让" in text or "股份转让" in text:
        types.append("equity_transfer")
    if "整体变更" in text:
        types.append("overall_conversion")
    if "设立" in text and not types:
        types.append("establishment")
    if "对赌协议" in text or "特殊权利" in text:
        types.extend(["special_rights_agreement", "termination"])
    return list(dict.fromkeys(types))


def _printed_pages(rows: list[PageRecord], start: int, end: int) -> list[int]:
    return [x for x in (rows[p - 1].printed_page for p in range(start, end + 1)) if x is not None]


def _excerpt(text: str, limit: int = 350) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    return value[:limit]


def extract_events(rows: list[PageRecord], history_start: int, history_end: int) -> tuple[list[AutoEvent], list[dict]]:
    events: list[AutoEvent] = []
    review_items: list[dict] = []
    seq = 1

    # Establishment from explicit narrative.
    establishment_pages = [p for p in range(history_start, history_end + 1) if "共同申请设立公司前身上海云汉电子有限公司" in re.sub(r"\s+", "", rows[p - 1].text)]
    if establishment_pages:
        p = establishment_pages[0]
        text = rows[p - 1].text
        events.append(
            AutoEvent(
                auto_event_id=f"AUTO-EVT-{seq:03d}",
                event_date_original="2008年5月",
                event_date_normalized="2008-05",
                event_name="上海云汉电子有限公司设立",
                event_types=["establishment"],
                pdf_pages=[p, p + 1],
                printed_pages=_printed_pages(rows, p, p + 1),
                evidence_excerpt=_excerpt(text[text.find("2008 年4 月17 日") :]),
                extraction_method="narrative_rule",
                review_status="AUTO_EXTRACTED",
                review_reason=None,
                source_text_sha256s=[rows[p - 1].text_sha256, rows[p].text_sha256],
            )
        )
        seq += 1

    # Overall conversion from explicit narrative.
    conversion_pages = [p for p in range(history_start, history_end + 1) if "发行人系由上海云汉电子有限公司整体变更设立" in re.sub(r"\s+", "", rows[p - 1].text)]
    if conversion_pages:
        p = conversion_pages[0]
        combined = rows[p - 1].text + "\n" + rows[p].text
        events.append(
            AutoEvent(
                auto_event_id=f"AUTO-EVT-{seq:03d}",
                event_date_original="2015年12月",
                event_date_normalized="2015-12",
                event_name="有限公司整体变更设立股份公司",
                event_types=["overall_conversion"],
                pdf_pages=[p, p + 1, p + 2],
                printed_pages=_printed_pages(rows, p, p + 2),
                evidence_excerpt=_excerpt(combined[combined.find("发行人系由") :]),
                extraction_method="narrative_rule",
                review_status="AUTO_EXTRACTED",
                review_reason=None,
                source_text_sha256s=[rows[x - 1].text_sha256 for x in [p, p + 1, p + 2]],
            )
        )
        seq += 1

    # Image-dominant flowchart cluster. Route rather than fabricate node contents.
    flow_heading_page = next(
        (p for p in range(history_start, history_end + 1) if "（三）云汉有限设立以来股本演变情况" in re.sub(r"\s+", "", rows[p - 1].text)),
        None,
    )
    post_company_heading = next(
        (p for p in range(history_start, history_end + 1) if "三、发行人股份公司设立后的股东变化情况" in re.sub(r"\s+", "", rows[p - 1].text)),
        None,
    )
    if flow_heading_page and post_company_heading:
        image_pages = [
            p
            for p in range(flow_heading_page, post_company_heading + 1)
            if rows[p - 1].image_count and rows[p - 1].text_char_count < 700
        ]
        if image_pages:
            review_id = "RVW-FLOWCHART-001"
            review_items.append(
                {
                    "review_item_id": review_id,
                    "review_type": "IMAGE_DOMINANT_FLOWCHART",
                    "pdf_pages": image_pages,
                    "printed_pages": _printed_pages(rows, min(image_pages), max(image_pages)),
                    "reason": "股本演变流程图节点不在PDF文本层，程序不使用空白文本推断事件",
                    "recommended_action": "查看已导出的页面PNG，逐节点确认日期、事件类型和数值",
                    "status": "OPEN",
                }
            )
            events.append(
                AutoEvent(
                    auto_event_id=f"AUTO-EVT-{seq:03d}",
                    event_date_original=None,
                    event_date_normalized=None,
                    event_name="有限公司设立以来股本演变流程图事件簇",
                    event_types=["visual_event_cluster"],
                    pdf_pages=image_pages,
                    printed_pages=_printed_pages(rows, min(image_pages), max(image_pages)),
                    evidence_excerpt="流程图图片页；文本层仅保留“转下图/续上图”等说明。",
                    extraction_method="image_presence_detector",
                    review_status="REVIEW_REQUIRED",
                    review_reason=review_id,
                    source_text_sha256s=[rows[p - 1].text_sha256 for p in image_pages],
                )
            )
            seq += 1

    # Text headings for post-incorporation events.
    headings: list[tuple[int, str]] = []
    for p in range(history_start, history_end + 1):
        for raw in rows[p - 1].text.splitlines():
            line = " ".join(raw.strip().split())
            m = HEADING_RE.match(line)
            if not m:
                continue
            title = m.group(2).strip()
            if any(k in title for k in ["股权转让", "股份转让", "增资", "增加注册资本", "对赌协议解除"]):
                headings.append((p, line))
    for idx, (start_page, heading) in enumerate(headings):
        end_page = (headings[idx + 1][0] - 1) if idx + 1 < len(headings) else history_end
        original_date, normalized_date = normalize_date(heading)
        text = "\n".join(rows[p - 1].text for p in range(start_page, end_page + 1))
        types = classify_types(heading)
        events.append(
            AutoEvent(
                auto_event_id=f"AUTO-EVT-{seq:03d}",
                event_date_original=original_date,
                event_date_normalized=normalized_date,
                event_name=re.sub(r"^（[一二三四五六七八九十]+）", "", heading),
                event_types=types,
                pdf_pages=list(range(start_page, end_page + 1)),
                printed_pages=_printed_pages(rows, start_page, end_page),
                evidence_excerpt=_excerpt(text),
                extraction_method="heading_and_section_rule",
                review_status="AUTO_EXTRACTED",
                review_reason=None,
                source_text_sha256s=[rows[p - 1].text_sha256 for p in range(start_page, end_page + 1)],
            )
        )
        seq += 1
    return events, review_items


def _section_text(rows: list[PageRecord], event: AutoEvent) -> str:
    return "\n".join(rows[p - 1].text for p in event.pdf_pages)


def _clean_party(value: str) -> str:
    value = normalize_name(value)
    prefixes = ["根据该协议，", "其中，", "同时，该协议还约定，", "该协议还约定，", "根据发行人与", "约定"]
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value[len(prefix) :]
    if "，" in value:
        value = value.split("，")[-1]
    return normalize_name(value)


def _unit_price(amount_wan: Decimal | None, shares: Decimal | None, shares_unit: str) -> Decimal | None:
    if amount_wan is None or shares is None or shares == 0:
        return None
    if shares_unit == "万股":
        return amount_wan / shares
    if shares_unit == "股":
        return amount_wan * Decimal("10000") / shares
    return None


def extract_transaction_legs(rows: list[PageRecord], events: list[AutoEvent]) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    seq = 1
    for event in events:
        if event.review_status != "AUTO_EXTRACTED":
            continue
        text = _section_text(rows, event)
        compact = re.sub(r"\s+", "", text)
        # Capital increase: cash + registered capital.
        pattern_capital = re.compile(
            r"(?P<party>[^；。]+?)以现金(?P<cash>[\d,\.]+)万元(?:的等值美元)?认缴新增注册资本(?P<capital>[\d,\.]+)万元"
        )
        for m in pattern_capital.finditer(compact):
            party = _clean_party(m.group("party"))
            cash = parse_decimal(m.group("cash"))
            capital = parse_decimal(m.group("capital"))
            legs.append(
                {
                    "auto_leg_id": f"AUTO-LEG-{seq:03d}",
                    "auto_event_id": event.auto_event_id,
                    "transaction_type": "CAPITAL_INCREASE",
                    "investor_or_transferee": party,
                    "transferor": None,
                    "cash_amount_wan": decimal_to_json(cash),
                    "registered_capital_wan": decimal_to_json(capital),
                    "shares": decimal_to_json(capital),
                    "shares_unit": "万股",
                    "disclosed_unit_price_yuan_per_share": None,
                    "calculated_unit_price_yuan_per_share": decimal_to_json(_unit_price(cash, capital, "万股")),
                    "pdf_pages": event.pdf_pages,
                    "evidence_excerpt": m.group(0),
                    "derivation_type": "PDF_DIRECT_TEXT+DETERMINISTIC_CALCULATION",
                }
            )
            seq += 1
        # Capital increase: cash + new shares.
        pattern_shares = re.compile(
            r"(?P<party>[^；。]+?)以(?:现金)?(?P<cash>[\d,\.]+)万元(?:的等值美元)?认购(?:上述|公司)?新增股份(?P<shares>[\d,\.]+)万股"
        )
        for m in pattern_shares.finditer(compact):
            party = _clean_party(m.group("party"))
            cash = parse_decimal(m.group("cash"))
            shares = parse_decimal(m.group("shares"))
            legs.append(
                {
                    "auto_leg_id": f"AUTO-LEG-{seq:03d}",
                    "auto_event_id": event.auto_event_id,
                    "transaction_type": "CAPITAL_INCREASE",
                    "investor_or_transferee": party,
                    "transferor": None,
                    "cash_amount_wan": decimal_to_json(cash),
                    "registered_capital_wan": decimal_to_json(shares),
                    "shares": decimal_to_json(shares),
                    "shares_unit": "万股",
                    "disclosed_unit_price_yuan_per_share": None,
                    "calculated_unit_price_yuan_per_share": decimal_to_json(_unit_price(cash, shares, "万股")),
                    "pdf_pages": event.pdf_pages,
                    "evidence_excerpt": m.group(0),
                    "derivation_type": "PDF_DIRECT_TEXT+DETERMINISTIC_CALCULATION",
                }
            )
            seq += 1
        # 2018-style transfer clauses.
        pattern_transfer_wan = re.compile(
            r"(?P<from>[^；。]+?)将其持有的发行人(?P<shares>[\d,\.]+)万股股份转让予(?P<to>[^，；。]+)，转让价格为(?P<amount>[\d,\.]+)万元"
        )
        for m in pattern_transfer_wan.finditer(compact):
            amount = parse_decimal(m.group("amount"))
            shares = parse_decimal(m.group("shares"))
            legs.append(
                {
                    "auto_leg_id": f"AUTO-LEG-{seq:03d}",
                    "auto_event_id": event.auto_event_id,
                    "transaction_type": "EQUITY_TRANSFER",
                    "investor_or_transferee": normalize_name(m.group("to")),
                    "transferor": _clean_party(m.group("from")),
                    "cash_amount_wan": decimal_to_json(amount),
                    "registered_capital_wan": None,
                    "shares": decimal_to_json(shares),
                    "shares_unit": "万股",
                    "disclosed_unit_price_yuan_per_share": None,
                    "calculated_unit_price_yuan_per_share": decimal_to_json(_unit_price(amount, shares, "万股")),
                    "pdf_pages": event.pdf_pages,
                    "evidence_excerpt": m.group(0),
                    "derivation_type": "PDF_DIRECT_TEXT+DETERMINISTIC_CALCULATION",
                }
            )
            seq += 1
        # 2018 first transfer, all shares.
        pattern_first = re.compile(
            r"(?P<from>[^，。]+?)将其持有的云汉芯城全部(?P<shares>[\d,]+)股股份（.*?）转让给(?P<to>[^，。]+)，转让价格.*?(?P<amount>[\d,]+)万元确定"
        )
        for m in pattern_first.finditer(compact):
            amount, shares = parse_decimal(m.group("amount")), parse_decimal(m.group("shares"))
            legs.append(
                {
                    "auto_leg_id": f"AUTO-LEG-{seq:03d}",
                    "auto_event_id": event.auto_event_id,
                    "transaction_type": "EQUITY_TRANSFER",
                    "investor_or_transferee": normalize_name(m.group("to")),
                    "transferor": _clean_party(m.group("from")),
                    "cash_amount_wan": decimal_to_json(amount),
                    "registered_capital_wan": None,
                    "shares": decimal_to_json(shares),
                    "shares_unit": "股",
                    "disclosed_unit_price_yuan_per_share": None,
                    "calculated_unit_price_yuan_per_share": decimal_to_json(_unit_price(amount, shares, "股")),
                    "pdf_pages": event.pdf_pages,
                    "evidence_excerpt": m.group(0),
                    "derivation_type": "PDF_DIRECT_TEXT+DETERMINISTIC_CALCULATION",
                }
            )
            seq += 1
        # 2019 transferee-first clauses.
        pattern_2019 = re.compile(
            r"(?P<to>[^，。]+?)以(?P<amount>[\d,\.]+)万元的价格受让(?P<from>[^，。]+?)持有的发行人股份(?P<shares>[\d,\.]+)万股"
        )
        for m in pattern_2019.finditer(compact):
            amount, shares = parse_decimal(m.group("amount")), parse_decimal(m.group("shares"))
            legs.append(
                {
                    "auto_leg_id": f"AUTO-LEG-{seq:03d}",
                    "auto_event_id": event.auto_event_id,
                    "transaction_type": "EQUITY_TRANSFER",
                    "investor_or_transferee": _clean_party(m.group("to")),
                    "transferor": normalize_name(m.group("from")),
                    "cash_amount_wan": decimal_to_json(amount),
                    "registered_capital_wan": None,
                    "shares": decimal_to_json(shares),
                    "shares_unit": "万股",
                    "disclosed_unit_price_yuan_per_share": None,
                    "calculated_unit_price_yuan_per_share": decimal_to_json(_unit_price(amount, shares, "万股")),
                    "pdf_pages": event.pdf_pages,
                    "evidence_excerpt": m.group(0),
                    "derivation_type": "PDF_DIRECT_TEXT+DETERMINISTIC_CALCULATION",
                }
            )
            seq += 1
        # 2020 transfer table parsed from line sequence.
        if "转让股份合计1,659,535股" in compact:
            lines = combine_lines(rows, min(event.pdf_pages), max(event.pdf_pages))
            try:
                start = lines.index("转让方") + 4
            except ValueError:
                start = -1
            if start >= 0:
                tokens: list[str] = []
                for line in lines[start:]:
                    if line.startswith("2020 年9 月23 日") or line.startswith("2020年9月23日"):
                        break
                    tokens.append(line)
                current_from: str | None = None
                i = 0
                while i < len(tokens):
                    if i + 3 < len(tokens) and not parse_decimal(tokens[i]) and not parse_decimal(tokens[i + 1]) and parse_decimal(tokens[i + 2]) is not None and parse_decimal(tokens[i + 3]) is not None:
                        current_from = normalize_name(tokens[i])
                        transferee, shares_text, amount_text = normalize_name(tokens[i + 1]), tokens[i + 2], tokens[i + 3]
                        i += 4
                    elif current_from and i + 2 < len(tokens) and not parse_decimal(tokens[i]) and parse_decimal(tokens[i + 1]) is not None and parse_decimal(tokens[i + 2]) is not None:
                        transferee, shares_text, amount_text = normalize_name(tokens[i]), tokens[i + 1], tokens[i + 2]
                        i += 3
                    else:
                        i += 1
                        continue
                    amount, shares = parse_decimal(amount_text), parse_decimal(shares_text)
                    legs.append(
                        {
                            "auto_leg_id": f"AUTO-LEG-{seq:03d}",
                            "auto_event_id": event.auto_event_id,
                            "transaction_type": "EQUITY_TRANSFER",
                            "investor_or_transferee": transferee,
                            "transferor": current_from,
                            "cash_amount_wan": decimal_to_json(amount),
                            "registered_capital_wan": None,
                            "shares": decimal_to_json(shares),
                            "shares_unit": "股",
                            "disclosed_unit_price_yuan_per_share": None,
                            "calculated_unit_price_yuan_per_share": decimal_to_json(_unit_price(amount, shares, "股")),
                            "pdf_pages": event.pdf_pages,
                            "evidence_excerpt": f"{current_from}|{transferee}|{shares_text}|{amount_text}",
                            "derivation_type": "PDF_TABLE_TEXT+DETERMINISTIC_CALCULATION",
                        }
                    )
                    seq += 1
    # De-duplicate exact legs caused by overlapping regexes.
    unique: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for leg in legs:
        key = (
            leg["transaction_type"],
            leg["transferor"],
            leg["investor_or_transferee"],
            leg["cash_amount_wan"],
            leg["shares"],
            leg["shares_unit"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(leg)
    for i, leg in enumerate(unique, start=1):
        leg["auto_leg_id"] = f"AUTO-LEG-{i:03d}"
    return unique


def extract_snapshots(rows: list[PageRecord]) -> tuple[list[dict], list[dict]]:
    definitions = [
        ("AUTO-SNP-001", "2008年5月设立完成后", 55, 56, "有限公司设立时的出资比例如下", "万元注册资本", "50"),
        ("AUTO-SNP-002", "2015年12月整体变更设立时", 54, 55, "本公司整体变更设立时", "股", "40000000"),
        ("AUTO-SNP-003", "2018年4月股份转让后", 58, 59, "本次股权转让后", "股", "40000000"),
        ("AUTO-SNP-004", "2018年6月至7月复合变更完成后", 59, 61, "本次变更完成后", "股", "46350000"),
        ("AUTO-SNP-005", "2019年8月股份转让后", 61, 62, "本次转让后", "股", "46350000"),
        ("AUTO-SNP-006", "2020年5月增资后", 62, 63, "本次增资后", "股", "47480488"),
        ("AUTO-SNP-007", "2020年9月增资及转让后", 63, 65, "本次变更完成后", "股", "48837074"),
    ]
    snapshots: list[dict] = []
    holdings: list[dict] = []
    stop = ("（一）", "（二）", "（三）", "（四）", "（五）", "（六）", "（七）", "（八）", "（九）")
    for sid, label, start, end, marker, unit, expected_total in definitions:
        lines = combine_lines(rows, start, end)
        parsed, total = parse_two_value_table(lines, marker, stop)
        total_value = decimal_to_json(parse_decimal(total[0])) if total else None
        snapshots.append(
            {
                "auto_snapshot_id": sid,
                "snapshot_label": label,
                "pdf_pages": list(range(start, end + 1)),
                "printed_pages": [rows[p - 1].printed_page for p in range(start, end + 1)],
                "holding_unit": unit,
                "disclosed_total": total_value,
                "expected_total_from_narrative": expected_total,
                "row_count": len(parsed),
                "review_status": "AUTO_EXTRACTED" if parsed else "REVIEW_REQUIRED",
            }
        )
        for row in parsed:
            holdings.append(
                row
                | {
                    "auto_snapshot_id": sid,
                    "holding_unit": unit,
                    "pdf_pages": list(range(start, end + 1)),
                    "derivation_type": "PDF_TABLE_TEXT",
                }
            )
    # Terminal pre-IPO snapshot, located from heading text.
    terminal_page = next((p.pdf_page for p in rows[79:] if any(re.sub(r"\s+", "", line.strip()).startswith("八、发行人股本情况") for line in p.text.splitlines())), None)
    if terminal_page:
        lines = combine_lines(rows, terminal_page, min(terminal_page + 2, len(rows)))
        parsed, total = parse_pre_post_table(lines, "发行前后股东持股情况如下")
        sid = "AUTO-SNP-008"
        snapshots.append(
            {
                "auto_snapshot_id": sid,
                "snapshot_label": "本次发行前静态终点",
                "pdf_pages": list(range(terminal_page, min(terminal_page + 2, len(rows)) + 1)),
                "printed_pages": [rows[p - 1].printed_page for p in range(terminal_page, min(terminal_page + 2, len(rows)) + 1)],
                "holding_unit": "股",
                "disclosed_total": decimal_to_json(parse_decimal(total[0])) if total else None,
                "expected_total_from_narrative": "48837074",
                "row_count": len(parsed),
                "review_status": "AUTO_EXTRACTED" if parsed else "REVIEW_REQUIRED",
            }
        )
        for row in parsed:
            holdings.append(
                {
                    "auto_snapshot_id": sid,
                    "row_index": row["row_index"],
                    "shareholder_original_name": row["shareholder_original_name"],
                    "holding_value": row["holding_value"],
                    "holding_percentage": row["holding_percentage"],
                    "holding_unit": "股",
                    "pdf_pages": list(range(terminal_page, min(terminal_page + 2, len(rows)) + 1)),
                    "derivation_type": "PDF_TABLE_TEXT",
                }
            )
    return snapshots, holdings


def events_to_dicts(events: list[AutoEvent]) -> list[dict]:
    return [asdict(e) for e in events]


def render_review_images(doc: fitz.Document, review_items: list[dict], output_dir: str) -> list[dict]:
    from pathlib import Path
    from .common import sha256_file

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rendered: list[dict] = []
    pages = sorted({p for item in review_items for p in item.get("pdf_pages", [])})
    matrix = fitz.Matrix(2.0, 2.0)
    for p in pages:
        target = out / f"pdf_page_{p:03d}.png"
        pix = doc[p - 1].get_pixmap(matrix=matrix, alpha=False)
        pix.save(target)
        rendered.append({"pdf_page": p, "file": target.name, "sha256": sha256_file(target)})
    return rendered
