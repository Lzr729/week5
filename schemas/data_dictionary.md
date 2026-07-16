# 阶段四工作簿字段字典

## `00_使用说明`

记录阶段用途、事实来源、填写顺序、阶段边界、验收状态和完成率。该页用于快速理解工作簿，不作为原始事实明细表。

## `01_事件主表`

每个主事件、父事件组、子事件或轮次级候选项占一行。

| 字段 | 含义 |
|---|---|
| `event_id` | 事件唯一编号，例如 CE-010-01 |
| `parent_event_id` | 所属父事件编号；未拆分时通常等于自身编号 |
| `event_level` | 主事件、父级事件组、子事件或轮次级候选项 |
| `stage3_date` | 阶段三固定的候选事件时间 |
| `stage3_title` | 阶段三固定的候选事件标题 |
| `standard_event_name` | 阶段四人工理解后的标准事件名称 |
| `chapter_no` | 章节定位编号 |
| `chapter_title` | 招股说明书中的章节标题 |
| `pdf_pages` | PDF 阅读器页码范围 |
| `printed_pages` | 正文印刷页码范围 |
| `event_type` | 设立、增资、股权转让、整体变更、特殊权利等 |
| `title_date` | 标题或流程图披露的时间 |
| `application_or_resolution_date` | 申请日、股东会或其他决议日 |
| `agreement_date` | 协议签署日 |
| `payment_or_verification_date` | 缴款、验资或审验相关时间 |
| `registration_date` | 工商登记或备案时间 |
| `actual_completion_date` | 原文明示的实际完成节点 |
| `date_notes` | 时间精度、辅助节点及未披露说明 |
| `is_composite` | 是否为复合事件 |
| `split_result` | 不拆分或拆分结果 |
| `split_reason` | 事件拆分或不拆分的判断依据 |
| `shareholder_change_summary` | 各主体股东变化方向摘要 |
| `original_values_summary` | 原文披露数值摘要，不含人工复算 |
| `special_agreement_tag` | A、B、C、D、D+等特殊权利轮次标记 |
| `confirmed_facts` | 原文可直接确认的事实 |
| `manual_judgment` | 人工理解、事件边界及方向判断 |
| `undisclosed_items` | 原文未披露事项 |
| `review_questions` | 复核时关注的判断 |
| `review_status` | 未开始、待人工复核或已验收通过 |
| `reviewer` | 复核人或标注来源 |
| `review_date` | 复核日期 |
| `source_note` | 事实来源和页码备注 |

## `02_参与方`

每个事件中的每个主体占一行。

| 字段 | 含义 |
|---|---|
| `participant_id` | 参与方记录唯一编号 |
| `event_id` | 对应事件或子事件编号 |
| `original_name` | 招股说明书原文中的主体名称或简称 |
| `standardized_name` | 统一后的主体名称 |
| `disclosed_entity_type` | 原文披露或当前证据能够确认的主体类型 |
| `event_role` | 转让方、受让方、增资方、发起人等角色 |
| `before_status` | 事件发生前的状态 |
| `action` | 本次事件中的行为 |
| `change_direction` | 新增、退出、持股增加、持股减少等 |
| `after_status` | 事件发生后的状态 |
| `judgment_nature` | 原文明确披露、事件衔接判断等判断性质 |
| `judgment_basis` | 角色和变化方向的证据依据 |
| `evidence_ids` | 对应证据编号 |
| `review_note` | 口径限制和待复核说明 |
| `review_status` | 当前复核状态 |

## `03_原文证据`

每段正文、表格、流程图或注释证据占一行。

| 字段 | 含义 |
|---|---|
| `evidence_id` | 证据唯一编号 |
| `event_id` | 对应事件编号 |
| `chapter_no`、`chapter_title` | 章节定位 |
| `pdf_page`、`printed_page` | 双页码 |
| `location_type` | 正文、表格、流程图、注释等 |
| `cross_page` | 是否跨页 |
| `original_quote_or_description` | 原文摘录或表格的准确描述 |
| `supported_fields` | 该证据支持的事实或字段 |
| `related_evidence` | 需要结合使用的其他证据编号 |
| `evidence_note` | 证据限制、简称或页码说明 |
| `needs_review` | 是否存在证据层面的人工核对提示 |
| `review_status` | 当前复核状态 |

## `04_原文数值`

每个原文数值和其口径占一行。

| 字段 | 含义 |
|---|---|
| `value_id` | 数值记录唯一编号 |
| `event_id` | 对应事件编号 |
| `evidence_id` | 数值来源证据编号 |
| `field_name` | 注册资本、增资额、股份数量、价款等 |
| `original_value` | 招股说明书直接披露值 |
| `unit` | 元、万元、亿元、股、%、日期或比例等 |
| `related_party` | 数值对应主体或交易方向 |
| `related_sub_event` | 对应子事件 |
| `value_nature` | 原文披露值或其他数值性质 |
| `calculation_status` | 是否计算；阶段四原则上为未计算 |
| `口径备注` | 数值范围、约数及禁止推导说明 |
| `review_status` | 当前复核状态 |

## `05_复核清单`

逐事件检查证据、时间、角色、拆分、数值和阶段边界。`overall_check_status`由各检查项综合形成，最终记录复核人、日期和结论。

## `06_批量复核摘要`

汇总 CE-004 至 CE-014 的事件名称、双页码、拆分结论、核心时间、主体变化、原文数值、关键人工判断和用户结论，并记录阶段四最终验收结论。

## 辅助工作表

- `99_下拉选项`：数据验证下拉值；
- `06_当前事件复核`：历史单事件复核页，最终成果以批量摘要及其他底表为准。
