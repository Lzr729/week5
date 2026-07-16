# 状态字段定义

本项目使用以下统一状态值：

| 状态值 | 含义 |
|---|---|
| `confirmed` | 已由 PDF 原文定位并经人工复核确认 |
| `calculated` | 根据原文数据或页码关系计算得出，尚未完成独立人工复核 |
| `inferred` | 根据上下文作出的研究推断，不等同于原文明确披露 |
| `pending_manual_review` | 尚需人工打开 PDF 核对 |
| `not_disclosed` | 招股说明书未披露，不能补造 |
| `not_started` | 对应阶段尚未开始 |

## 来源类型建议

| 来源类型 | 含义 |
|---|---|
| `pdf_original` | 直接来自 PDF 原文、标题、目录或页面版式 |
| `manual_confirmation` | 研究者打开 PDF 后人工确认 |
| `calculated_from_pdf` | 由 PDF 原文值或页码关系计算得到 |
| `conversation_record` | 阶段验收过程中的人工确认记录；正式引用仍应回到 PDF |

## 使用原则

- 原文标题的起始页通常标记为 `confirmed`。
- 根据下一标题推算的终止页，在人工核对前标记为 `calculated`。
- 完成逐页人工核对后，可将相应终止页状态更新为 `confirmed`，但应在备注中保留其最初的计算方法。
- `inferred` 不得替代 `confirmed`。
