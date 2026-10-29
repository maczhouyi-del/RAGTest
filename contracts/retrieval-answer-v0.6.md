# 检索到回答增量契约 v0.6（RAG-01，2026-10-27）

RAG-02当前查询/历史、重排预算、API输入与诊断增量见[v0.7](retrieval-answer-v0.7.md)；以下保留RAG-01当时行为记录，正式质量门禁没有因后续功能自动通过。

继承search-v0.2、workbench-v0.2及mvp-v0.5；以下为当前实现，替代旧文中的无条件历史拼接和展开后排名语义。IPC握手0.1.0、`/v0`、health.api_revision=0.5-local、SQLite schema18不变，无数据迁移。质量门禁未通过。

## 阶段与失败边界

| 阶段 | 输入 → 输出 | 失败/验证 |
|---|---|---|
| 意图 | 原问题 → 精确系统主题列表及保留的论文子问题 | 引擎FORMS为唯一问法清单；不按“模型”等主题词放行；不识别的完整问题保留 |
| 范围 | 选定版本/项目 → ScopeSnapshot（论文身份、SHA、解析批次） | SCOPE_NOT_AVAILABLE / SCOPE_STALE / SCOPE_IDENTITY_CHANGED；不扩大范围 |
| 召回 | 实际查询及范围 → 词法/向量独立候选 | 参数INVALID_SEARCH；向量未配/损坏/旧代明确错误；GUI未就绪时明确选keyword |
| 融合 | 原始通道rank → RRF与确定性Chunk排序 | 单通道单Chunk只投一票，重复关联不累加；ID破同分 |
| 上下文选择 | 融合候选 → 优先不同内容、逻辑论文配额、最终≤8 | 同内容来源content_sources保留；无可用来源不伪造结果 |
| 证据判断 | 当前候选 → 摘录/生成草稿/拒答 | 无命中不调用生成；有命中不自动等于能支持答案 |
| 生成与核验 | 当前池及非证据历史 → Claim/Evidence | 本轮池+精确quote+当前SourceAnchor+发布前冻结范围复查；任一失败整轮不发布 |
| 输出 | 状态、诊断、候选/结论/人工状态 → UI及持久历史 | completed/refused/failed/cancelled保持；辅助outcome区分具体结果 |

测试分别见test_system_information、test_retrieval_ranks、test_answer_pipeline、既有生命周期/模型/范围测试，以及浏览器MVP03路由回归。

## 系统问法与复合问题

`system_information.FORMS`覆盖当前/你/现在的生成模型、Embedding、索引状态和检索策略的有限中英文问法。NFKC、lower、去空白和Unicode标点；health返回标准化问法，React只匹配该清单，不维护另一份主题词规则。纯系统问题可空文献范围，不检索、不加载/调用生成模型、不调用外部API、不生成引用。保存配置、凭据可用、文献问答授权、已加载、当前会话历史连接/生成验证分别记录，`inference_performed=false`只描述系统信息部分。

配置回答描述问答界面本轮选择，不能当作已调用模型。Embedding与生成模型角色区分。检索策略记录selected_strategy与executed_strategy=null；索引未就绪仍可读取原因，不伪称混合已执行。

复合问题只按明确标点/连接词拆出与清单完全匹配的系统子句，其余文字保留为literature_question并检索。`intent=mixed`同时保存/展示system_information与论文结果；未识别到完整系统子句时保留原问题，禁止静默删掉内容。确定性清单不是通用语言意图分类器。

## 检索、RRF和配额

- Sources保留FTS5/BM25；字面模式安全转义完整短语，keyword使用实际`cjk-unigrams-bigrams-tf-v2`：索引CJK单字+双字及词频、查询双字/单字与英文/数字词段，OR召回。连字符/单位分词不改写原文或引文偏移。没有人工金标，未声称OR噪声合格，未主观替换为交集算法。
- 每路候选上限为`max(k,50)`，搜索k严格为整数1–100；问答固定k=8，因此每路50。vector_exact不执行FTS召回，但独立校验范围；词法策略不加载向量或生成模型。相同内容+完整E5指纹继续复用向量。E5的query:/passage:、384维、L2归一化/cosine及512 token溢出拒绝规则不变。
- `lexical_rank`为BM25原始1-based排名；`vector_rank`为适配器返回Embedding的原始1-based排名。一个Embedding展开多个Chunk时共享vector_rank，后续Embedding排名不变。`RRF(d)=Σ 1/(60+rank_i(d))`，每个通道每Chunk只计一次；分数相同按Chunk ID排序。distance、bm25_score、rrf_score均不是相关性概率或科学可信度。
- 配额前先考虑不同内容，再用余位接纳重复来源；所有候选关联保存在SQLite，返回的content_sources保留该召回池中相同内容的Chunk/版本/页/锚点。该列表是来源关联元数据，不是额外送入模型或已核验的引用。最终rank重新编号用于展示；原始rank字段不变。
- 普通UI及Workbench默认每逻辑论文3片段、总≤8；已确认归并的不同PDF版本共用document_id计数。单选一篇仍默认3。旧API显式per_paper_limit=1–8保留兼容（历史8配额用例保留），GUI不再传8。Research逐篇覆盖与局部配额独立。
- 语义命中只允许映射回当前可见、范围内、同space且内容指纹相同的SQLite Chunk；孤儿命中INDEX_INCOMPLETE。慢查询后复查项目、可见性、元数据筛选、世代和Chunk指纹；无自动更换后端/模型/全库回退。

## 历史、输出和证据

独立问题只使用当前literature_question。检测到有限中文指代/继续比较或英文代词时才补入最近两轮问题；历史总预算1600字符、最多3轮缓存，系统信息与失败轮排除。历史答案只传给生成器作非证据上下文；引用池仅来自本轮检索。`context_policy`记录版本current-question-first-v2、strategy、turns、预算和真实retrieval_query，检索失败也保留查询诊断。此规则仍需真实多轮金标检验。

AnswerRun.result新增向后兼容诊断：

- `retrieval_status=hits|no_hits|not_completed`；`retrieval`保存实际strategy、世代、每路候选上限/数量、per_paper_limit和最终hits（去掉正文，保留原始排名、来源与内容关联）。
- `outcome=evidence_only|answered|no_hits|insufficient_evidence|retrieval_failed|generation_failed|system_info_failed|cancelled`。纯系统仍kind=system_info。
- no_hits为refused/NO_HITS、不调用模型、没有证据；insufficient_evidence为refused/INSUFFICIENT_EVIDENCE、保存候选和辅助支持意见及补证提示。
- 生成、引用或发布校验失败为failed、原具体error_code保留，kind=error/outcome=generation_failed，failure_stage说明失败环节。检索失败为retrieval_failed。失败result仅是诊断、claims/evidence_ids为空；不发布部分Claim/Evidence。旧历史result=null继续可读。
- 原source_status、model_support、comparability、human_status及审查历史不变；evidence_assessment明确精确原文验证与同模型支持意见的边界。UI只把supported草稿作为回答展示，其他支持意见和冲突警告保留；所有生成结果仍需人工核对。

回答提示要求考虑当前全部已送入模型的片段、冲突时引用双方并说明、保留条件/不确定性，证据不足返回空claims。本地prompt升级v11-conflicts，旧v9/v10仅提示版本可兼容，其他权重/运行时指纹仍须完全相同；网络提示v3-conflicts记录在冻结指纹。提示不是冲突识别准确率保证。未送入模型的片段由既有context_metadata标记，不能称已被审查。

可选keyword_review/hybrid_review仍默认关闭，只使用本地已配置候选对最多6片段作有界意见；即使回答选择网络Provider，也不借用它进行复核。未配置本地模型明确失败，不隐式调用外部Reranker。原/新序列、意见、指纹记录，科学质量NOT_EVALUATED。

## 评估与回退

`tools/compare_retrieval.py`只读打开原SQLite并备份到新的显式输出目录，复制并核对不可变派生索引，不复制PDF/下载模型/联网。全部策略共享快照、版本/项目/筛选、问题、k=10与无论文配额，保留每次排名/耗时。可选本地复核必须显式flag。未裁定/候选标签不全时不计算相关性分数。现有科学评分器补Recall@5、MRR/nDCG、人工无支持论断率与检索/端到端P50/P95；人工金标、阈值、时延缺失则BLOCKED。小样本及合成实验不解除1000篇、干净Windows或科研门禁。

无需删除/迁移数据库即可回退源码；旧客户端可忽略新增字段，失败仍按status识别。旧提示指纹源码回滚后可能要求显式重新校验已有本地模型，不删除旧配置。锁文件、原件、批注、向量和审查记录保持不变。
