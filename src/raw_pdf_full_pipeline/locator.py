from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .pdf_reader import PageRecord


@dataclass(frozen=True)
class LocatedRange:
    range_id: str
    title: str
    start_pdf_page: int
    end_pdf_page: int
    start_printed_page: int | None
    end_printed_page: int | None
    locator_rule: str


def find_heading_page(rows: list[PageRecord], phrase: str, start: int = 1) -> int | None:
    target = re.sub(r"\s+", "", phrase)
    for row in rows[start - 1 :]:
        for raw in row.text.splitlines():
            line = re.sub(r"\s+", "", raw.strip())
            if line == target or line.startswith(target):
                return row.pdf_page
    return None


def locate_ranges(rows: list[PageRecord]) -> list[LocatedRange]:
    history_start = find_heading_page(rows, "二、发行人的设立情况", start=45)
    history_end = find_heading_page(rows, "四、发行人重大资产重组情况", start=history_start or 45)
    terminal_start = find_heading_page(rows, "八、发行人股本情况", start=80)
    if history_start is None or history_end is None:
        raise RuntimeError("无法自动定位历史沿革起止章节")
    ranges = [
        LocatedRange(
            range_id="R-HISTORY",
            title="发行人的设立情况及股份公司设立后的股东变化",
            start_pdf_page=history_start,
            end_pdf_page=history_end - 1,
            start_printed_page=rows[history_start - 1].printed_page,
            end_printed_page=rows[history_end - 2].printed_page,
            locator_rule="start=二、发行人的设立情况; end=四、发行人重大资产重组情况",
        )
    ]
    if terminal_start:
        ranges.append(
            LocatedRange(
                range_id="R-TERMINAL-SNAPSHOT",
                title="本次发行前后的股本情况",
                start_pdf_page=terminal_start,
                end_pdf_page=min(terminal_start + 3, len(rows)),
                start_printed_page=rows[terminal_start - 1].printed_page,
                end_printed_page=rows[min(terminal_start + 2, len(rows) - 1)].printed_page,
                locator_rule="heading=八、发行人股本情况",
            )
        )
    return ranges


def ranges_to_dicts(ranges: list[LocatedRange]) -> list[dict]:
    return [asdict(x) for x in ranges]
