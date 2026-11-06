# SECTION-AWARE（2026-11-05）

用户附件授权Python解析/Chunk/元数据迁移/测试/评估，不改前端/Rust、不动真实用户库、不调用付费API、不直接推main。基线9d301b3干净。

现状：page.text固定400/80切块，Docling块已保存但未消费；章节树不存在。新策略保留Unicode原始切片、内容哈希语义，新增21元数据表而非改chunks列。统一结构块与保守文本行规则、空行段落；长段落句末优先400/80；不改视觉换行原文，仅逻辑聚合。不能识别的标题/跨页段落关系不推断。

全量与部分发布在原事务内建立新的结构快照，顺序扫描当前published_pages（每次一页），重算后续章节上下文但不修改未选页Chunk/向量。旧Chunk跨新段落边界时标记legacy_boundary，历史元数据快照保留。章节metadata是注释，不是引用；原有SourceAnchor校验优先。

验证：新单元/集成覆盖层级、误识别、offset、400/80、迁移、部分发布、回滚及备份；完整pytest与既有真实PDF/E5候选。用公开PDF离线比较A/B/C；无人工金标的Recall/MRR/nDCG/支持性不能报通过。资源与数据库/迁移边界不放宽。

## 实际结果（2026-11-06）

工程实现及隔离验证完成：schema21；所有旧迁移未变；章节编号父子校验、图标签/页眉排除、段落偏移和句末400/80；部分解析完整重算结构快照。原始切片、content_sha256、向量链接/排序/授权规则保留。按页Chunk索引避免逐页全表扫描。

新增定向41 PASS；完整Python395 PASS/0 FAIL/0 SKIP，Ruff通过；最终verified冻结侧车构建通过，102项源码与产物哈希一致。真实公开PDF两篇29页A424/B208/C574Chunk，B因EMBEDDING_CONTEXT_LIMIT未完成索引，C原文切片574/574、部分重解析后571向量复用/0新增。科研门禁工具实际exit2/BLOCKED/0金标，不能宣称召回或回答质量提升。

详细文件、命令、失败及限制见[实施报告](../reports/SECTION-AWARE-CHUNKING-IMPLEMENTATION.md)。Windows/千篇/金标/用户原库重新解析和GUI部署未完成验收；本次没有提交、推送、发布或自动处理用户库。
