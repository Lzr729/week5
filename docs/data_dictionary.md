# 阶段五数据字典

## equity_timeline.json

一项实际股本变化事件一条记录。核心字段：

| 字段 | 含义 |
|---|---|
| `timeline_id` | 阶段五时间线唯一编号 |
| `event_id` | 阶段四验收事件或子事件编号 |
| `parent_event_id` | 父级复合事件编号 |
| `display_sequence` | 展示顺序，不必然代表法律行为逐笔先后 |
| `time_node_ids` | 关联时间节点编号数组 |
| `capital_*_original` | 招股说明书直接披露值 |
| `capital_*_calculated` | 时间线衔接计算值 |
| `calculation_ids` | 关联计算登记编号数组 |
| `evidence_ids` | PDF原文证据编号数组 |
| `pdf_pages` | PDF阅读器页码数组 |
| `printed_pages` | 正文印刷页码数组 |
| `undisclosed_items` | 原文未披露事项 |
| `manual_judgment` | 人工判断及边界 |
| `review_status` | 阶段五人工验收状态 |

## time_nodes.json

一项独立日期事实一条记录。日期字段标准化为ISO格式；月份级信息仍保留在`original_date_text`和`date_precision`中，不推定具体日。

## calculations.json

一项衔接计算一条记录。每项计算保留输入值、输入来源编号、公式说明、计算结果、原文比较值和差异。计算值不能覆盖原文披露值。

## exclusions.json

不进入主时间线的父级容器和特殊权利事项。

## auxiliaries.json

验资复核、后续验资报告等不另建资本事件的辅助程序。

## review_items.json

阶段五确认后转入后续阶段的事项，包括CE-005数值差异以及复合事件内部排序边界。

## acceptance_checks.json

17个主时间线事件的逐项验收结果。

## 空值规则

- `null`：该字段在本事件中无值或原文未直接披露；
- `[]`：多值字段没有可列示项目；
- 不得把`null`或空数组解释为零；
- 人工判断、原文披露值和计算值必须分开。
