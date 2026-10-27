# 科研 PDF 与检索金标：构建规范（未提供真实测试样本）

**来源：** v1.1 §9.2–9.5；其它标注字段与流程是本包提出的执行建议。**目前无真实金标/答案，所有数值是源方案拟议样本规模。**

## 评测三阶段

1. **A / 基础 PDF 质量：** 30–50 篇许可明确的中英文论文、约 120–200 道人工核对问题。覆盖普通/双栏/图表/数学公式/扫描/混合/旋转/CropBox 等页；标记文本顺序、关键表格表头/行/单位、页码、区域/单元格位置。
2. **B / 检索模型选择：** 100–200 篇，中文→英文、英文→中文、混合术语、材料名/符号/短检索词；人工标注论文 ID、段落/页面与多条可接受证据；记录具体 Embedding 模型和 IndexSpace 指纹。
3. **C / 目标全库：** 约 1000 篇真实论文，评估规模、范围隔离、候选文献发现/逐篇覆盖机制、失败率；不得用 Top-K 的样本覆盖冒充完整处理清单。

各阶段**逐级进行**，小样本通过不意味着 1000 篇级科研准确率已获验证。

## 样本分层标签

- 语言：中文、英文、混排；OCR 语言/科研符号。
- PDF 内容：数字文本、扫描、混合；单栏/双栏；表格、复杂表头、数学公式、图注、脚注；有/无可提取目录。
- 页坐标：正常、页面旋转、CropBox、不连续文本块、OCR 置信度低。
- 科研任务：定位方法、参数条件、实验组、数据集、评价指标、样本量、数据划分、结果数值/单位、无证据应拒答。
- 检索风险：同义词/缩写、多语种、时间限定、不同论文同名指标、相同数值不同实验条件、重复版本。

## 标注单元与双重校对（建议）

每道 query 保存：问题、预期范围、目标 DocumentVersion、标准证据片段、PDF 原页/区域、实际研究条件、可接受同义结果、问题是否可回答、金标说明与标注人。研究值提取还要保存 `table_id/row/column/metric/value/unit/experimental_conditions`，防止只校对数字不校对含义。

- 关键字段至少两轮独立人工核对或由标注负责人复核；存在分歧保留修订历史和 adjudication 理由。
- Gold Set 中的论文应具有文件 SHA、许可/使用范围、PDF 可重现版本；不可随意上传受限 PDF 或将标注过的样本公开。
- 数据抽取错误单独分类：漏识别、引用错页、错表格单元、单位混淆、实验条件丢失、越过允许范围、错误拒答。

## 不同测试与不同指标

| 测试层 | 指标（计划） | 注意 |
|---|---|---|
| PDF 解析与 SourceAnchor | 页码正确性、来源区域正确性、表格值-表头-条件绑定准确率 | 自动评分必须和人工金标比对；坐标不可靠降级为 page-only |
| 检索 | 文献级/Chunk 级 Recall@5/10、MRR@10、nDCG@10 | 单篇/跨语种/语料干扰分组，限定当前授权论文集 |
| Claim 支持（P3） | source_validity、supported/contradicted/uncertain、无支持论断率、正确拒答率 | 来源存在 ≠ 语义支持；模型评审 ≠ 人工证明 |
| 研究提取（P4） | 提取字段正确率、科学可比性、`explicit_not_reported` 假阳性 | 缺失检索 ≠ 原文明确未报告 |
| 系统工程 | P50/P95（拆分）、RAM/磁盘、重建/恢复正确性 | 不与科研准确率混用；记录真机与模拟/CI 边界 |

## 文件约定

- `corpus-manifest.template.csv`：空表头，真实数据由授权的用户/测试人员填写。
- `gold-questions.template.csv`：空表头，真正问题和答案由人工标注。
- `benchmark-run.template.csv`：空表头，不预填虚构实测结果。
- 建议将真实 PDF 放 `tests/fixtures/private/`（Git 忽略），可分发样本由许可证允许且经审查后才放到 Git。

## 科研测量门槛决议

在未观察分布前，v1.1 没有给出所有解析与语义质量百分比硬阈值。本包**不自行编造**准确率 KPI。P0-00 确定目标和人工复核流程，注册评测指标/抽样方法；真实测量后在 ADR 中决定下一阶段推进方式。未达到用户批准的指标时明确 FAIL/CONDITIONAL 而非隐藏失败集。

## HARDEN-01 可执行离线格式

`contracts/scientific-gold.schema.json`为JSONL金标行格式。空`gold-cases.template.jsonl`/`predictions.template.jsonl`没有虚构问题或页码；人工逐项填写id、category、question、answerable、实际PDF SHA/page/quote目标、expected_facts（field/value/unit/conditions）、至少两名独立reviewers和adjudicated状态。category覆盖methods/results/numeric_units/tables/cross_document/multi_turn/insufficient_evidence；多轮样例可另附conversation/context字段，不把历史回答当targets。

预测行包含同id、status、retrieved[{sha256,page}]、citations[{sha256,page,quote}]、facts，以及人工对**这次模型输出**的human_review{status,reviewers,fact_correct,semantic_support}。模型自审的supported或自评分不计作人工评分。工具监督解析原件并验证SHA/页/摘录，不虚构框；扫描/表格复杂布局需人工金标及额外诊断，自动文本匹配失败不强行当对。

执行：`PYTHONPATH=engine engine/.venv/bin/python tools/evaluate_scientific_quality.py --gold <人工JSONL> --predictions <本地预测JSONL> --manifest <合法语料manifest> --thresholds docs/evaluation/thresholds.proposed.json --output <本机目录>`。不运行生成模型/不联网，只离线评分。分别统计检索Recall@10、原文引用有效性、人工事实正确/语义支持、金标可回答性对应的拒答、数值单位条件结构化精确匹配；显示样本数与分组，不把缺数据当满分。量纲换算或容忍度必须先经人工注册，默认精确匹配。

thresholds.proposed.json提出初始建议值（来源有效性100%，Recall@10≥90%，其余≥95%），**全部待PI批准**，不是已批准标准。类别缺失、人工标注/输出审查不足、没有批准人或阈值时exit2/BLOCKED，即使局部指标为1也不算科研门禁PASS。还需批准样本量、交叉分组和统计口径；不根据本轮模型表现降低标准。失败样例保留在本地评价JSON，不上传私有文本。

## RAG-01 同范围策略比较与新增指标

`retrieval-cases.template.jsonl`是待填写模板，空问题/范围不会运行实验。用真实本地版本ID、问题、可选项目/filters替换；从冻结SQLite中标注relevance[{chunk_id,grade:0..3}]，至少两人独立审查并裁定annotation.status=adjudicated、reviewers和pool_complete=true。需要标注各策略候选并集和漏检相关片段；返回但未标注的候选不得自动当作相关性0，工具将该行指标留空。覆盖精确术语、短语、同义/跨语言、方法/参数/单位、多论文、冲突、无答案、全库问题；全库须另外检查Research逐篇清单。

```sh
engine/.venv/bin/python tools/compare_retrieval.py --workspace <本地工作区> --cases <本地JSONL> --output <新的实验目录> --strategies keyword,vector_exact,hybrid --repeats 10
```

工具只读备份原库和核对后复制派生索引，保留输出快照，不清理原库。三个策略使用同一问题/Chunk/范围/筛选及k=10，无论文配额；词法/向量候选各50，记录原始rank、世代、范围指纹及逐次耗时。`--strategies keyword,vector_exact,hybrid,hybrid_review --include-local-review`仅调用已配置的本地候选，不使用网络Provider。索引损坏或模型缺失的策略记录BLOCKED，不能假装混合已执行。MEASURED只表示实验运行完成。

Chunk级指标Recall@5/10、MRR、分级nDCG@10；相同ID重复不重复得分，但仍占用排名。无正例时Recall/MRR/nDCG为空，不伪填1。未裁定数据可以测量耗时，scientific_quality保持BLOCKED。P50为中位数，P95为nearest-rank；记录冷启动顺序/重复次数，工具计时包含查询Embedding与候选关联，不可直接与“不含查询Embedding”的P95≤1s建议目标比较。

现有科学预测JSONL可另填`latency_ms:{retrieval:<实测毫秒>,end_to_end:<实测毫秒>}`；人工审查增加`total_claims`和`unsupported_claims`（必须实际审阅本轮输出），评分器计算无支持论断比例，不读取模型自评分。同时新增页级Recall@5/MRR/nDCG（无分级标签时二元），保留原Recall@10。引用有效性要求来源验证且属于本轮retrieved页，语义正确仍由独立人工判断。minimum阈值方向为≥；可选maximum方向为≤，例如无支持比例，数值须另经批准，本轮不修改既有建议阈值或样本量。

检索/回答时延缺失、人工无支持审查缺失均登记缺口。索引构建耗时/磁盘/内存用既有`capacity_benchmark.py`，真实与synthetic分开；真实样本数不足时exit2/BLOCKED。无法用少数查询、合成1000页或模型自审宣布科研/1000篇容量合格。
