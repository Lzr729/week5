# 阶段三结构化数据字段说明

## 1. `data/candidate_events.csv`

| 字段 | 含义 |
|---|---|
| `event_id` | 阶段三固定的候选事件编号。 |
| `parent_event_id` | 轮次级候选项所属父级事件组。 |
| `event_level` | `main`、`group` 或 `round_candidate`。 |
| `event_date` | 原文可稳定识别的日期；未在阶段三统一确定时留空。 |
| `event_name` | 候选事件名称，不代表已完成逐笔交易拆分。 |
| `event_types` | 多个类型以 `|` 分隔。 |
| `primary_section` | 主证据所在章节编号。 |
| `pdf_start_page` / `pdf_end_page` | PDF 阅读器页码。 |
| `printed_start_page` / `printed_end_page` | 正文印刷页码。 |
| `evidence_excerpt` | 最短充分原文证据或视觉证据摘要。 |
| `evidence_source` | `pdf_text`、`flowchart_visual_review`、`manual_visual_confirmation` 等。 |
| `compound_event` | 是否包含多个交易组成部分。 |
| `duplicate_disclosure` | 同一事件的其他披露位置。 |
| `shareholder_entry_exit_signal` | 仅记录进入或退出候选信号，不代表阶段三最终认定。 |
| `review_status` | 阶段三复核状态。 |
| `stage4_action` | 阶段四应执行的人工理解任务。 |
| `notes` | 阶段边界、数值校验提示等。 |

## 2. `data/flowchart_nodes.csv`

记录 C2-3 三页跨页流程图的视觉识别结果。`node_label_original` 保留左侧事件框原文；`detail_evidence_excerpt` 只保留右侧框的最短充分摘要。`duplicate_with_c3` 用于标记与 C3 正文的重复披露。

## 3. `data/auxiliary_findings.csv`

记录否定性披露、合理性说明、静态股东信息和重复性辅助说明。该文件中的记录不计入资本事件数量。

## 4. `evidence/stage3_evidence_index.csv`

建立证据位置与事件编号之间的映射。视觉截图本身不随验收包重复分发，复核时应打开源招股说明书的对应页。

## 5. 状态值

| 状态 | 含义 |
|---|---|
| `confirmed` | 已通过文本或人工复核确认。 |
| `confirmed_by_visual_review` | 已通过连续页面视觉复核确认。 |
| `negative_disclosure_confirmed` | 已确认原文为否定性披露。 |
| `pending_manual_review` | 仍需人工复核；本验收版中该状态数量为0。 |

## 6. 数值口径

结构化文件中的注册资本、股本和股份数量均为原文披露信息或原文标签的一部分，不是本项目计算值。任何加总、差额、单价、持股比例和估值均应在后续阶段另列计算字段，不得覆盖原文值。
