# 数据字典

## `data/pdf_metadata.json`

| 字段 | 类型 | 含义 |
|---|---|---|
| `document_name` | string | 唯一主要事实来源文件名 |
| `pdf_page_count` | integer | PDF 阅读器显示的总页数 |
| `toc` | object | 目录的双页码范围和确认状态 |
| `page_mapping` | object | PDF 页码与正文印刷页码映射 |
| `visual_review` | object | 必须人工查看的视觉结构范围 |
| `stage_status` | string | 阶段验收状态 |

## `data/section_index.csv`

| 字段 | 含义 |
|---|---|
| `section_id` | 稳定章节编号，例如 `C3-2` |
| `parent_id` | 上级章节编号；二级章节为空 |
| `section_level` | 标题层级 |
| `title` | PDF 原文标题 |
| `pdf_start_page` / `pdf_end_page` | PDF 阅读器物理页范围 |
| `printed_start_page` / `printed_end_page` | 正文印刷页范围 |
| `function` | 该章节在研究流程中的用途，不是事件结论 |
| `source_type` | 信息来源类型 |
| `review_status` | 人工复核状态 |
| `notes` | 跨页、同页边界等说明 |

## `evidence/evidence_index.csv`

| 字段 | 含义 |
|---|---|
| `evidence_id` | 稳定证据编号 |
| `stage` | 证据首次用于哪个阶段 |
| `section_id` | 关联章节编号；无关联时为空 |
| `pdf_start_page` / `pdf_end_page` | 证据在 PDF 阅读器中的页码范围 |
| `printed_start_page` / `printed_end_page` | 对应正文印刷页范围；封面可为空 |
| `evidence_type` | 目录、标题、跨页边界、视觉复核范围等 |
| `original_text_or_description` | 短标题原文或非数值化证据描述 |
| `used_for` | 该证据支持的定位结论 |
| `source_type` | PDF 原文、人工确认等来源 |
| `verification_status` | 复核状态 |
| `notes` | 使用限制和补充说明 |

## 页码范围规则

- 单页证据的起止页相同。
- 跨页证据分别填写起始页和终止页。
- 相邻章节可以共享同一个物理页，不能据此强制执行“上一章节终页 = 下一章节起页 - 1”。
