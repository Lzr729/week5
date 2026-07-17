from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from artifact_tool import Blob, SpreadsheetFile, Workbook

from .review import DECISIONS, REVIEW_STATUSES

HEADER_FILL = "#1F4E78"
SUBHEADER_FILL = "#D9EAF7"
EDIT_FILL = "#FFF2CC"
PASS_FILL = "#E2F0D9"
WARN_FILL = "#FCE4D6"
TITLE_FILL = "#17365D"
WHITE = "#FFFFFF"


def _join(values: list[Any]) -> str:
    return "；".join(str(v) for v in values if v not in (None, ""))


def _style_title(sheet, cell_range: str, title: str) -> None:
    sheet.merge_cells(cell_range)
    first = cell_range.split(":")[0]
    sheet.get_range(first).values = [[title]]
    sheet.get_range(cell_range).format = {
        "fill": TITLE_FILL,
        "font": {"bold": True, "color": WHITE, "size": 16},
        "horizontal_alignment": "center",
        "vertical_alignment": "center",
        "row_height": 30,
    }


def _style_header(rng) -> None:
    rng.format = {
        "fill": HEADER_FILL,
        "font": {"bold": True, "color": WHITE},
        "horizontal_alignment": "center",
        "vertical_alignment": "center",
        "wrap_text": True,
        "borders": {"items": [{"side": side, "style": "continuous", "color": "#B4C6E7", "weight": 1} for side in ("top", "bottom", "left", "right")]},
    }


def _style_body(rng) -> None:
    rng.format = {
        "vertical_alignment": "top",
        "wrap_text": True,
        "borders": {"items": [{"side": side, "style": "continuous", "color": "#D9E2F3", "weight": 1} for side in ("top", "bottom", "left", "right")]},
    }


def _write_table(sheet, start_cell: str, headers: list[str], rows: list[list[Any]], table_name: str | None = None) -> tuple[int, int]:
    start_col = ord(start_cell[0].upper()) - ord("A")
    start_row = int(start_cell[1:]) - 1
    matrix = [headers] + rows
    end_row = start_row + len(matrix)
    end_col = start_col + len(headers)
    rng = sheet.get_range_by_indexes(start_row, start_col, len(matrix), len(headers))
    rng.values = matrix
    _style_header(sheet.get_range_by_indexes(start_row, start_col, 1, len(headers)))
    if rows:
        _style_body(sheet.get_range_by_indexes(start_row + 1, start_col, len(rows), len(headers)))
    if table_name and rows:
        sheet.tables.add(rng, True, table_name)
    return end_row, end_col


def export_review_workbook(bundle_9c: dict[str, Any], review_bundle: dict[str, Any], output_path: str | Path) -> None:
    wb = Workbook.create()

    # 01 Summary
    sh = wb.worksheets.add("01_运行摘要")
    _style_title(sh, "A1:H1", "阶段九9D：人工复核闭环工作簿")
    summary = review_bundle["summary"]
    kpis = [
        ["9C基线状态", review_bundle["metadata"]["input_baseline_status"], "9C自动评价数", summary["automatic_evaluations_in_9c"]],
        ["待复核事项", summary["review_item_count"], "开放程序异常", summary["exceptions_open"]],
        ["已关闭复核", summary["closed"], "未完成复核", summary["pending"]],
    ]
    sh.get_range("A3:D5").values = kpis
    sh.get_range("A3:D5").format = {"borders": {"items": [{"side": s, "style": "continuous", "color": "#B4C6E7", "weight": 1} for s in ("top", "bottom", "left", "right")]}, "wrap_text": True}
    sh.get_range("A3:A5").format = {"fill": SUBHEADER_FILL, "font": {"bold": True}}
    sh.get_range("C3:C5").format = {"fill": SUBHEADER_FILL, "font": {"bold": True}}
    type_rows = [[k, v] for k, v in sorted(summary["review_type_counts"].items())]
    _write_table(sh, "A8", ["复核类型", "数量"], type_rows, "ReviewTypeSummary")
    sh.get_range("F3:H3").merge()
    sh.get_range("F3").values = [["操作说明"]]
    sh.get_range("F3:H3").format = {"fill": SUBHEADER_FILL, "font": {"bold": True}, "horizontal_alignment": "center"}
    instructions = [
        ["1", "在“08_人工复核决定”填写黄色列。"],
        ["2", "人工修正必须填写修正值和复核说明。"],
        ["3", "保留未知或退回重新检查必须填写复核说明。"],
        ["4", "填写复核人、复核日期，并将状态设为已关闭。"],
        ["5", "不要修改自动结果、证据、页码、事件ID或规则ID。"],
    ]
    sh.get_range("F4:G8").values = instructions
    sh.get_range("F4:G8").format = {"wrap_text": True, "vertical_alignment": "top"}
    chart = sh.charts.add("column", sh.get_range(f"A8:B{8+len(type_rows)}"))
    chart.title_text = "待复核事项构成"
    chart.has_legend = False
    chart.set_position("F10", "L24")
    sh.freeze_panes.freeze_rows(1)
    sh.get_range("A1:L25").format.autofit_columns()
    for col, width in {"A":24,"B":18,"C":22,"D":16,"F":8,"G":44}.items():
        sh.get_range(f"{col}:{col}").format.column_width = width

    # 02 Rules
    sh = wb.worksheets.add("02_规则结果")
    _style_title(sh, "A1:H1", "9C规则结果（只读）")
    rule_rows = [[r.get("rule_id"), r.get("result"), r.get("evaluated_object_count"), r.get("applicable_object_count"), _join(r.get("failed_object_ids", [])), r.get("program_version"), r.get("rule_set_version"), r.get("review_status")] for r in bundle_9c["rule_results"]]
    _write_table(sh, "A3", ["规则ID","结果","评价对象数","适用对象数","失败对象ID","程序版本","规则集版本","复核状态"], rule_rows, "RuleResults")
    sh.freeze_panes.freeze_rows(3)
    sh.get_range("A:H").format.autofit_columns()
    sh.get_range("E:E").format.column_width = 28

    # 03 Exceptions
    sh = wb.worksheets.add("03_异常队列")
    _style_title(sh, "A1:J1", "程序异常队列")
    if review_bundle["exceptions"]:
        rows = []
    else:
        rows = [["无", "本次9C无开放程序异常", "非异常", "不阻断", "—", "—", "—", "—", "—", "待复核事项见08_人工复核决定"]]
    _write_table(sh, "A3", ["异常ID","说明","类型","阻断性","对象类型","对象ID","事件ID","证据ID","状态","处理建议"], rows, "ExceptionQueue")
    sh.get_range("A:J").format.autofit_columns()
    sh.get_range("B:B").format.column_width = 34
    sh.get_range("J:J").format.column_width = 34

    # 04 Candidate review items
    sh = wb.worksheets.add("04_候选复核事项")
    _style_title(sh, "A1:M1", "候选与待判断事项（只读）")
    review_rows = []
    for r in review_bundle["review_items"]:
        review_rows.append([r["review_item_id"],r["review_type"],r["priority"],r["object_type"],r["object_id"],_join(r["event_ids"]),_join(r["evidence_ids"]),_join(r["pdf_pages"]),_join(r["printed_pages"]),_join(r["original_excerpts"]),r["auto_result"],_join(r["rule_ids"]),r["recommended_action"]])
    _write_table(sh, "A3", ["复核事项ID","复核类型","优先级","对象类型","对象ID","事件ID","证据ID","PDF页码","正文页码","原文证据","自动结果","规则ID","建议操作"], review_rows, "ReviewCandidates")
    sh.freeze_panes.freeze_rows(3)
    sh.get_range("A:M").format.autofit_columns()
    for col, width in {"J":48,"K":42,"M":42}.items(): sh.get_range(f"{col}:{col}").format.column_width=width

    # 05 Name merge boundary
    sh = wb.worksheets.add("05_名称合并候选")
    _style_title(sh, "A1:F1", "名称合并候选")
    _write_table(sh, "A3", ["候选ID","原名称","候选标准名称","依据","状态","说明"], [["无","—","—","—","不适用","9D不执行模糊名称匹配；只使用阶段八已验收名称映射。"]], "NameMergeCandidates")
    sh.get_range("A:F").format.autofit_columns(); sh.get_range("F:F").format.column_width=50

    # 06 Numeric differences
    sh = wb.worksheets.add("06_数值差异")
    _style_title(sh, "A1:L1", "数值差异与舍入事项（只读）")
    numeric_rows=[]
    for r in bundle_9c["numeric_evaluations"]:
        if r.get("comparison_value") is None or r.get("absolute_difference") not in (None,"0","0.0","0.00"):
            cls = next((c.get("observed",{}).get("classification") for c in r.get("checks",[]) if c.get("rule_id")=="S09-N006" and isinstance(c.get("observed"),dict)), None)
            numeric_rows.append([r["object_id"],_join(r["event_ids"]),r.get("formula_type"),r.get("recomputed_value"),r.get("comparison_value"),r.get("absolute_difference"),cls,_join(r["pdf_pages"]),_join(r["printed_pages"]),_join(r["evidence_ids"]),_join(r["original_excerpts"]),r.get("review_status")])
    _write_table(sh, "A3", ["校验ID","事件ID","公式类型","复算值","原文比较值","绝对差异","分类","PDF页码","正文页码","证据ID","原文证据","复核状态"], numeric_rows, "NumericDifferences")
    sh.freeze_panes.freeze_rows(3); sh.get_range("A:L").format.autofit_columns(); sh.get_range("K:K").format.column_width=50

    # 07 PEVC candidates/path exclusions
    sh = wb.worksheets.add("07_PEVC路径候选")
    _style_title(sh, "A1:L1", "PE/VC分类候选与路径排除事项（只读）")
    pevc_rows=[]
    for r in review_bundle["review_items"]:
        if r["review_type"].startswith("PEVC_"):
            pevc_rows.append([r["review_item_id"],r["review_type"],r["object_type"],r["object_id"],_join(r["event_ids"]),_join(r["evidence_ids"]),_join(r["pdf_pages"]),_join(r["printed_pages"]),_join(r["original_excerpts"]),r["auto_result"],_join(r["rule_ids"]),r["recommended_action"]])
    _write_table(sh, "A3", ["复核事项ID","复核类型","对象类型","对象ID","事件ID","证据ID","PDF页码","正文页码","原文证据","自动结果","规则ID","建议操作"], pevc_rows, "PEVCReviewItems")
    sh.freeze_panes.freeze_rows(3); sh.get_range("A:L").format.autofit_columns();
    for col,width in {"I":50,"J":44,"L":42}.items(): sh.get_range(f"{col}:{col}").format.column_width=width

    # 08 Human decisions
    sh = wb.worksheets.add("08_人工复核决定")
    _style_title(sh, "A1:U1", "人工复核决定（黄色列可编辑）")
    headers=["复核事项ID","复核类型","优先级","对象类型","对象ID","事件ID","证据ID","PDF页码","正文页码","原文证据","自动结果","规则ID","建议操作","人工决定","修正值","复核说明","复核人","复核日期","复核状态","导入校验结果","必填提示"]
    rows=[]
    for r in review_bundle["review_items"]:
        rows.append([r["review_item_id"],r["review_type"],r["priority"],r["object_type"],r["object_id"],_join(r["event_ids"]),_join(r["evidence_ids"]),_join(r["pdf_pages"]),_join(r["printed_pages"]),_join(r["original_excerpts"]),r["auto_result"],_join(r["rule_ids"]),r["recommended_action"],None,None,None,None,None,"待复核",None,None])
    end_row,_=_write_table(sh,"A3",headers,rows,"HumanReviewDecisions")
    last=3+len(rows)
    if rows:
        sh.get_range(f"N4:N{last}").data_validation={"rule":{"type":"list","values":DECISIONS}}
        sh.get_range(f"S4:S{last}").data_validation={"rule":{"type":"list","values":REVIEW_STATUSES}}
        sh.get_range(f"N4:S{last}").format.fill=EDIT_FILL
        sh.get_range("T4").formulas=[["=IF(AND(N4=\"\",S4=\"待复核\"),\"待填写\",IF(AND(N4=\"人工修正\",OR(O4=\"\",P4=\"\")),\"不完整\",IF(AND(OR(N4=\"保留未知\",N4=\"退回重新检查\"),P4=\"\"),\"不完整\",IF(AND(N4<>\"\",Q4<>\"\",R4<>\"\",S4=\"已关闭\"),\"可导入\",\"待关闭\"))))"]]
        sh.get_range(f"T4:T{last}").fill_down()
        sh.get_range("U4").formulas=[["=IF(N4=\"人工修正\",\"必填：修正值、说明、复核人、日期、已关闭\",IF(OR(N4=\"保留未知\",N4=\"退回重新检查\"),\"必填：说明、复核人、日期、已关闭\",IF(N4=\"确认自动结果\",\"必填：复核人、日期、已关闭\",\"请选择人工决定\")))"]]
        sh.get_range(f"U4:U{last}").fill_down()
        sh.get_range(f"T4:T{last}").conditional_formats.add_custom('=T4="可导入"', {"fill": PASS_FILL})
        sh.get_range(f"T4:T{last}").conditional_formats.add_custom('=OR(T4="不完整",T4="待关闭")', {"fill": WARN_FILL})
    sh.freeze_panes.freeze_rows(3); sh.freeze_panes.freeze_columns(5)
    sh.get_range("A:U").format.autofit_columns()
    for col,width in {"J":48,"K":44,"M":42,"P":38,"U":44}.items(): sh.get_range(f"{col}:{col}").format.column_width=width
    sh.get_range("R:R").format.number_format="yyyy-mm-dd"

    # 09 Acceptance
    sh = wb.worksheets.add("09_验收检查")
    _style_title(sh, "A1:E1", "9D验收检查")
    acc_rows=[[r["check_id"],r["check_item"],r["result"],str(r["observed"]),"用户复核全部关闭后方可进入9E" if r["result"]=="PENDING" else ""] for r in review_bundle["acceptance_checks"]]
    _write_table(sh,"A3",["检查ID","检查事项","结果","观察值","说明"],acc_rows,"AcceptanceChecks")
    sh.get_range("A:E").format.autofit_columns(); sh.get_range("B:B").format.column_width=38; sh.get_range("E:E").format.column_width=42

    # 10 Change log
    sh = wb.worksheets.add("10_变更日志")
    _style_title(sh, "A1:M1", "人工复核变更日志")
    _write_table(sh,"A3",["操作ID","复核事项ID","对象类型","对象ID","修改前自动结果","人工决定","修正值","复核说明","复核人","复核日期","校验结果","程序版本","规则集版本"],[["暂无","—","—","—","原自动结果不覆盖","—","—","待导入人工决定后生成","—","—","PENDING","0.5.0-9d","9D.1.0"]],"ChangeLog")
    sh.get_range("A:M").format.autofit_columns(); sh.get_range("E:E").format.column_width=44; sh.get_range("H:H").format.column_width=42

    SpreadsheetFile.export_xlsx(wb).save(str(output_path))


def import_review_decisions(workbook_path: str | Path) -> list[dict[str, Any]]:
    wb = SpreadsheetFile.import_xlsx(Blob.load(str(workbook_path)))
    sheet = wb.worksheets.get_item("08_人工复核决定")
    values = sheet.get_range("A3:U1000").values
    if not values:
        return []
    headers = values[0]
    header_map = {name: idx for idx, name in enumerate(headers) if name}
    required = ["复核事项ID","人工决定","修正值","复核说明","复核人","复核日期","复核状态"]
    missing = [name for name in required if name not in header_map]
    if missing:
        raise ValueError(f"复核工作表缺少列: {missing}")
    decisions=[]
    for row in values[1:]:
        item_id=row[header_map["复核事项ID"]] if len(row)>header_map["复核事项ID"] else None
        if not item_id:
            continue
        review_date=row[header_map["复核日期"]] if len(row)>header_map["复核日期"] else None
        if review_date is not None and not isinstance(review_date,str):
            review_date=str(review_date)
        decisions.append({
            "review_item_id":item_id,
            "human_decision":row[header_map["人工决定"]] if len(row)>header_map["人工决定"] else None,
            "correction_value":row[header_map["修正值"]] if len(row)>header_map["修正值"] else None,
            "reviewer_note":row[header_map["复核说明"]] if len(row)>header_map["复核说明"] else None,
            "reviewer":row[header_map["复核人"]] if len(row)>header_map["复核人"] else None,
            "review_date":review_date,
            "review_status":row[header_map["复核状态"]] if len(row)>header_map["复核状态"] else None,
        })
    return decisions
