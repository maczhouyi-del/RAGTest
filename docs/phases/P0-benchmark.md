# P0 真实 Benchmark 协议（预注册草案）

**目的：** 公平比较 sqlite-vec / LanceDB 精确 KNN；验证解析、持久 Embedding、Windows 运行与恢复。**不包含结果。**

## 1. 数据与版本冻结

- 收集论文级 Manifest：document_id、pdf_sha256、页数、数字文本/扫描/混合、多栏/表格比率、语言、版权/许可、相关金标题目。
- 100 / 1000 / 3000 篇是 v1.1 建议档，不是现有库的已知事实；若无法收齐，在报告中注明实际 N 与限制。
- 对照 KNN：使用完全相同的 `chunk_id`、向量 float32 数组、维度、归一化方式、精确距离、过滤范围、查询向量、排序/相同距离 tie-breaker。
- `index_generation`、模型 SHA256、tokenizer/预处理配置、查询范围快照均登记版本。禁止候选间一个使用 ANN、另一个使用 exact。

## 2. 机器与运行条件

| 维度 | 必填字段 |
|---|---|
| 机器 | Windows 11 版本/build、CPU 型号、核心数、RAM 8GB 或 16GB、SSD/HDD、剩余磁盘、功耗与节能状态 |
| 运行时 | SQLite/FTS5、sqlite-vec、LanceDB、Python/ONNX/PDFium、包装器版本及 SHA/lockfile |
| 数据 | 论文 N、页数、Chunk 总数、向量数量、维度、原件大小、ParseRun/EmbeddingSpace 指纹 |
| 条件 | 首次启动 vs 重启、冷/热查询、任务并发度、重复次数、进程内存、索引/缓存热度 |
| 操作 | 过滤条件（项目/论文/年份/标签）、Top-K、删改比例、备份及恢复时是否有任务在进行 |

## 3. 测试步骤

1. **正确性预检：** 对小规模固定随机种子向量构造可人工核对的精确距离金标（可用简单双重循环基线）；验证 KNN 排序、空集合、范围隔离、重复/删除/更新向量、维度不匹配错误。
2. **统一构建：** 不同候选从同一冻结 Embedding 输入生成索引；分别测导入、cold open、warm open、内存峰值、索引/数据文件大小。
3. **查询：** 用固定可复现的查询集与预热方法，至少明确重复轮数/采样时长；记录每次 query 内核耗时，不得把 Cloud LLM/Reranker/查询 Embedding 混入 KNN。
4. **增量：** 新增 1/10 篇、重复导入、更新同一 DocumentVersion、删除可见性，测耗时、结果一致性及原向量重复计算数（理想=0，除非参数改变）。
5. **故障/恢复：** kill Sidecar、磁盘满、向量库损坏、并发备份/重启等，验证原件 SHA、已发布与不可见记录、恢复路径和 Manifest。
6. **打包：** 同样在干净 Windows、中文/空格路径下验证两候选的实际 Runtime DLL/扩展加载；记载不能运行的情况，不把开发机成功冒充发布适用性。
7. **汇总：** 对比功能正确性、P50/P95、峰值 RAM、磁盘、恢复可靠性、许可和安装体积，不仅以速度作结论。

## 4. 推荐报告字段

- 时间字段：每次毫秒计量，`component` = `fts_only` / `knn_exact` / `hybrid` / `query_embed` / `rerank` / `llm`，**分开报告**。
- 每次记录：`run_id, backend, dataset_id, query_id, k, filter_id, is_cold, iteration, latency_ms, result_ids, correct, error_code`。
- 聚合：`n_queries, n_repeats, p50_ms, p95_ms, max_ms, peak_rss_mb, on_disk_mb, correctness_failures, recovery_failures`。
- Gold Set：FTS/跨语言等科研召回实验单独汇总 `Recall@5/10 / nDCG@10 / MRR@10`，不与工程 KNN 正确性混为一谈。

## 5. 选型规则（待用户批准的合理建议）

**先可用、再正确、再快。** 若某候选无法可靠 Windows 打包、备份或过滤正确性，不因少量速度优势而选用；若二者均满足实际时延/质量目标，优先维护成本更低/一致性边界更清晰者。若精确 KNN 能满足 P0/P2 后验收门槛，先不引入 ANN。

**注意：** 文档中的 16GB CPU 机器混合检索 P95 ≤ 1 s 为**初始努力目标**，非已验证 SLA；需要把查询 Embedding/云推理等排除在该指标之外，并说明混合排序框架在 P2 才完善。

## 6. 模板

- `docs/evaluation/benchmark-run.template.csv`：逐次测试记录；**没有伪造的数据**。
- `docs/architecture/adr/ADR-000-template.md`：正式决定时复制新建 ADR。
