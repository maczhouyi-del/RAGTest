# 本地布局与表格候选增量契约 v0.2

状态：本地工程实现，非解析器最终选型/科研验收。沿用0.1.0握手与`/v0`认证边界，API revision仍`0.2-local`；旧合法请求保持兼容。SQLite从10事务升级至11前保存OnlineBackup，旧程序拒绝新schema。未修改原SourceAnchor/EvidenceSpan草案。

依据v1.1 §§3.2–3.5、4.1–4.2、5.3–5.4、6.2–6.3、7、9；用户明确批准两个固定候选及本项目内Docling/PyTorch依赖。权重、配置、版本、来源和校验值见`docs/legal/docling-model-register.json`与`engine/uv.lock`。

## 配置与处理

- `POST /v0/internal/directory-grants`新增purpose=`docling`，仅原生broker选择普通本机目录后签发；前端只持一次性grant ID。祖先/子目录符号链接、网络目录和目录替换沿用拒绝规则。
- `GET /v0/docling`返回configured/fingerprint/candidate_only，不返回绝对模型路径。`POST /v0/docling`仅接受model_grant_id/idempotency_key，后台verify任务在私有worker真实加载固定权重后发布配置；取消/失租不得发布。
- `POST /v0/documents/{version}/parse`新增可选`use_docling=false`。与`use_ocr`同时为true时返回PARSER_OPTIONS_CONFLICT。普通解析、显式OCR、显式布局/表格分别执行；尚未交付自动质量路由或单页增强，不将它们描述为测试通过。
- Docling默认外部服务/插件/OCR/代码公式/图片/图表增强均关闭，CPU2线程、批次1、队列2、固定TableFormer fast。HF/Transformers离线并使用固定本地目录；worker的Python socket连接函数额外拒绝联网。这是纵深防护，不是完整OS沙箱。
- 增强候选最多40页，144dpi页面面积最多800万像素、每页5万字符/全文150万字符、200表/1万单元格；父进程300秒墙钟、worker240秒CPU，私有输入16KiB/输出8MiB、日志有界。Mac/Windows没有承诺完整硬内存限额。页面/像素在模型加载前检查；取消/失租每100ms检查并终止确切子进程。
- PDF哈希校验后处理。新ParseRun、页元素、Chunk、块结构、表格、单元格及FTS发布为一个短事务；发布前再次核对可见性/lease。模型加载/转换/校验/数据库失败保留旧可见结果，原PDF不可变。重试保留use_docling。

## 文本映射与结构

`parse_page_structure`保存每页有序块、标签、Docling item引用、原始模型对象/provenance及页文本codepoint范围。单页文本可进入页元素；跨页文本仅在charspan构成完整、不重叠且边界合法的分区时按对应页分配。不能验证时保留原始对象和DOCLING_ITEM_LOCATION_UNRESOLVED，整体解析标partial，不把整段归到第一页。

`parse_tables`以新的不可变UUID关联DocumentVersion/ParseRun/页元素，保留模型self_ref、原始结构、候选页集合、行列数。多页单元格归属无法确定时page/element和cell偏移为NULL；保存候选供核对，文字不冒充某一页的科学来源。

`table_cells`保存独立UUID、从0开始的半开行列范围、列头/行头标志、原始模型结构和文本。单页序列化只加入实际单元格文本与tab/换行；不把人工生成的行列编号当论文原文。每格的页元素codepoint偏移在事务内校验精确子串。跨Chunk只按quote与非空cell的真实偏移交集关联，最多返回100个候选标识。

模型给出的bbox保留为未经校准的原始数据。SourceAnchor继续page_only、bbox_norm=NULL；reason标DOCLING布局表格未经审查。EvidenceSpan形状不变；证据私有快照另存`table_candidates`（table/cell ID、行列范围、表头标志），公共Evidence返回同样候选列表及text_origin。报告保留相关候选标识并标结构待核对；这不能证明列对齐、单位或科学含义正确。

## 读取、人工审查与历史

- `GET /v0/documents/{version}/tables?offset=0`按当前已发布ParseRun返回20条表摘要/总数/next_offset，offset限制0–200；不可见版本拒绝。
- `GET /v0/tables/{id}?row_offset=0`返回10行涉及的单元格（包含起于前页但跨到本页的span），row_offset限制0–1000，返回next_row_offset；来源、表格ID、行列数、当前复核及最近20条修订可查看。
- `POST /v0/tables/{id}/review`接受expected_revision、unreviewed/confirmed/rejected/uncertain及1–4000字符note。短事务CAS，旧revision拒绝REVIEW_CONFLICT；原结构不改写，复核另存不可覆盖修订。confirmed仅表示用户记录结构确认，科学可比性仍not_assessed，不联动Claim/数值含义的人工确认。
- 重新解析成功后旧table ID留存数据库/历史引用，但新读取和结构复核返回SCOPE_STALE。停用/撤稿后新表格读取同样拒绝；旧报告正文不改写。备份包含新结构和复核表，恢复原ID。
- React显示单元格的行列范围/跨度/原始文本，不把错位候选渲染成已确认矩阵；可跳至实际PDF页核对。所有论文文本通过React文本节点显示，不作为HTML、shell或工具指令执行。

工程验证与科研质量分别报告。当前两篇实测中已出现多列文本合并，且部分跨页段落无法可靠定位；没有人工金标，不能报告表格正确率或以候选计数替代质量。
