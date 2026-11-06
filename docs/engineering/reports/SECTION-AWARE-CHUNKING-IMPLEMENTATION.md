# SECTION-AWARE-CHUNKING-IMPLEMENTATION

- Task ID / 阶段：SECTION-AWARE，用户授权的 Python Chunk 增量改造。
- 交付核对日期：2026-11-06（Asia/Shanghai）；原始执行时间以各 JSON 日志的 UTC 时间为准。
- 基线：`9d301b3c4be0425d5d78561a35a12ec6c2a9c3c8`；分支：`codex/section-aware-chunking`；本次未提交、推送或合并。
- 范围：附件 §§3–11；契约 `contracts/section-aware-chunking-v0.12.md`、原 SourceAnchor 和 Embedding 哈希约束。
- 平台：macOS 26.2 ARM64，Python 3.12.13；未使用真实用户数据库；未调用付费 API、下载模型或上传文献。
- 功能测试：PASS（395 PASS / 0 FAIL / 0 SKIP）。真实 Windows 安装测试：NOT EXECUTED。科研质量验收：BLOCKED（缺人工金标）。

## 1. 原有实现及局限

审查了 pipeline、mapping、Docling/PDFium worker、发布、tables、incremental/embeddings、检索、迁移和相关测试。原实现使用每页 `page["text"]`，最大 400 个 Unicode 字符、相邻 80 字符重叠，在后半窗口寻找换行或句末边界。Docling 已保存 label/provenance/字符区间到 parse_page_structure，但 Chunk 生成没有消费这些块，也没有章节树或段落 ID。

这意味着跨段落/章节边界的页内窗口、视觉换行边界和短标题都可能被混在同一 Chunk。不能据此认定原 Embedding 模型、向量数据库失效，也不能保证本次切分调整改善回答质量。

## 2. 章节与类型识别

新增 `chunking/structure.py`，只消费序列化文本/块，不依赖 Docling 内部 Python 对象。Docling 的合法 start/end 块优先；未知标签记录 unknown；无位置或重叠块不虚构位置，未覆盖的页文本仍进入原生规则。

统一类型覆盖 document_title、abstract、section_header、paragraph、list_item、caption、table、formula、reference、appendix、unknown。标题/表格/公式等完整识别优先依靠可选 Docling；默认 PDFium 不假装具有这些结构的完整识别能力。

标题规则结合中英文常见名称、1/1.1/1.1.1 编号、附录 A/A.1、长度、标点、词形与 Docling 标题标签。标题元数据可压缩换行空白，原始文本从不改变。连续三个页面边缘重复的标题作为运行页眉/页脚抑制；图中 C T1、O B-PER O 不能当作附录。编号子标题必须属于匹配编号前缀的父标题；漏识别父标题时保留独立子章节，不伪造父节点，也不把 3.1 挂到 2 下。

每个章节持久化 id/title/level/parent/path/start_page/end_page/detection_method/confidence。0.65/0.9 是规则评分，**不是经金标校准的正确率**。PDFium 现有 worker 没有输出可直接使用的逐行字体/段间距字段，本轮没有新增字体几何提取；保留保守文本降级，不把它写成已完成版面重建。

## 3. 段落与长段落策略

原生文本以空行、明确标题和独立列表/图注/参考标记形成边界。普通视觉换行聚合在同一逻辑段内，不把每一行当作段落，也不删除换行/连字符/Unicode 字符。Docling 使用已有块范围。没有足够结构时保留页内连续文本作为兜底段。

短段和普通段各生成一个完整 Chunk，不强制合并。长段调用边界内核：最大 400、重叠 80、优先后半窗口的句末，找不到时硬切；忽略单纯视觉换行。不会跨段、跨章节或跨页拼接。一个长段拆出的所有 Chunk 共用 paragraph_id。

章节未知时保留段落与页面，仍在这些范围中执行句末优先的 400/80 页内兜底，记录 section_unclassified；没有可靠段落边界则对连续文本执行同一内核。这里复用原 chunk_page 的有界切分机制，但关闭“看到视觉换行就优先截断”的分支。未知类型记录 content_type_unclassified。旧数据没有结构时返回 legacy_unclassified；旧 Chunk 跨新段落边界时返回 legacy_or_unresolved_boundary。

跨页自然段缺少可靠续接证据时按页保留独立 paragraph_id，第一版没有臆测跨页共享 ID。

## 4. 来源、Embedding 与检索契约

每个 Chunk 的 clean_text 仍等于 `raw_text[start_offset:end_offset]`，offset 是 Unicode 码点半开区间；content_sha256 仍是该原文 UTF-8 的 SHA256。标题和章节路径不拼到 clean_text，也不进入 Embedding 输入。原 Embeddings.link 哈希校验、缓存、向量发布、BM25/RRF/Top-K、版本/项目范围和证据检查不变。

关键词与向量 hit、SourceAnchor 增加可选 structure；旧 Anchor JSON 仍合法。生成输入只在 source 元数据中增加 section_path（最多 3 层，每层 100 字符），quote/实际输入收据保持原文，不把章节注释伪装成引用。纯旧消费者可以忽略新增字段。

## 5. 数据模型与迁移

schema 20 → 21，仅新增 `0021_section_aware_chunking.sql`，0001–0020 已逐文件与 HEAD 核对一致。

```text
DocumentVersion + ParseRun + publication revision
  → structure_publications（不可变结构快照）
  → document_sections（父子树、跨页区间）
  → document_paragraphs（element、单页原始区间）
  → chunk_structure（已有 Chunk 的章节/段落关联）
```

不改 chunks 布局或旧向量记录。增加 chunk_structure 按 Chunk 查询索引、章节快照索引，以及 `chunks_by_element_offsets(element_id,start_offset)`，避免发布结构时每页扫描全库 Chunk；集成测试使用 EXPLAIN QUERY PLAN 核对该索引被使用。

迁移沿用已有先备份、写事务、校验迁移哈希的机制。测试从真实执行 0001–0020 得到的 SQLite 构造 v20 快照，验证直接升级保留行，以及旧格式清单/哈希核验后的备份恢复再升级。新 schema21 的真实公开 PDF 数据也完成备份/恢复与外键检查。上述都是隔离测试库，不是用户原库升级实测。

失败恢复使用升级前独立备份；旧程序拒绝 schema21，不支持直接降版本读写。没有修改历史迁移或覆盖原件。

## 6. 全量与部分发布

在原任务租约/revision 写事务中，同时发布页面指针和结构快照。全量解析创建所有新 Chunk；部分解析只替换选页 Chunk，再按页顺序扫描当前 published_pages 的既有 text/blocks，重新计算整篇章节归属。未选页不重读 PDF、不重切、不改 Chunk ID 或向量链接。

因此，第二页新增章节时第三页的旧 Chunk 会获得新的章节上下文；发生异常则页面指针和结构快照一起回滚。旧章节快照保留；当前读取按 parse_state.revision 选择，历史 Evidence 保留当时的 Anchor JSON。

扫描和段落/Chunk 归属采用单页加载、单向游标与有索引读取；没有为每个 Chunk 重解析整篇 PDF。原解析器 500 页、每页 50000 字符及现有资源/任务限制未放宽。部分发布仍需重算全文元数据，极限容量事务耗时待测。

## 7. 实际文件变更

| 文件 | 作用 |
|---|---|
| engine/ragsystem/chunking/structure.py | 新增统一块、标题、段落和长段切分 |
| engine/ragsystem/chunking/publication.py | 新增结构快照发布、父子校验、元数据读取 |
| engine/ragsystem/chunking/mapping.py | 增加仅句末边界选项，旧默认行为不变 |
| engine/ragsystem/parsing/pipeline.py | 接入结构 Chunk、发布和新配置指纹 |
| engine/ragsystem/storage/database.py | schema21 |
| engine/ragsystem/storage/migrations/0021_section_aware_chunking.sql | 新表及必要索引 |
| engine/ragsystem/retrieval/source_search.py | 关键词 hit 和 Anchor 附带结构 |
| engine/ragsystem/retrieval/hybrid.py | 向量 hit 附带结构 |
| engine/ragsystem/workflows/workbench.py | 传递 source.section_path |
| engine/ragsystem/models/provider.py | 校验/限制章节元数据，保持 quote |
| contracts/source-anchor.schema.json | 可选 structure，向后兼容 |
| contracts/section-aware-chunking-v0.12.md | 指纹、发布、兼容与降级说明 |
| tests/unit/test_section_chunking.py | 新结构/偏移/重叠/上下文测试 |
| tests/integration/test_section_publication.py | 新迁移/发布/缓存/恢复测试 |
| tests/integration/test_pipeline_refinements.py | 两项输入收据测试明确选择足够长的片段 |
| tests/integration/test_single_provider.py | schema 期望由 20 更新到 21 |
| tools/compare_section_chunking.py | 同源公开 PDF A/B/C 离线对照 |
| docs/engineering/execplans/SECTION-AWARE.md | 授权边界、实施计划与结果 |
| PLANS.md | 本任务状态 |
| 本报告 | 最终实现、证据与剩余门禁 |

未修改 React/TypeScript/CSS、Rust/Tauri、依赖锁、旧迁移、Embedding 实现或检索排序规则。Docling/worker/tables/既有 publication 已审查并复用，不为文件列表而机械改写。

## 8. 测试及中途发现

新增 41 项测试实例：三级标题、中英文、无编号名称、缩写/版本标题、附录、误识别（列表/正文/图中标签）、视觉换行/Unicode/OCR 噪声、空文本、400/80、原始偏移、Docling 间隙及跨行标题、生成元数据和 quote 分离；集成覆盖真实 BERT、跨页章节、同段子 Chunk、部分发布后下游归属、失败回滚、向量链接不变、重复页眉、缺父标题、索引计划、v20 升级/旧备份恢复、v21 新备份恢复。

中途失败均保留记录，未删测试或降低验收：

- SourceAnchor 初次新增字段被严格 schema 拒绝：补上可选契约后复测通过。
- 两个旧测试假定首个 BERT 命中至少有 100 字符，新策略保留短标题后不再成立。改为明确选择长命中，继续验证只可引用实际发给模型的 40 字符，不放松证据安全断言。
- 首次 A/B/C 临时目录落到 macOS `/var` 符号链接路径，被已有索引路径校验拒绝。评估工具改用 resolved 隔离目录，没有放松生产路径校验。
- BERT 实测漏识别 3 BERT 并误挂 3.1：增加缩写标题与编号祖先校验。附录扩展曾误认图中标签：增加排除规则。原生标题仍有漏识别风险，不能只凭规则测试声称准确率达标。
- 一次 Ruff 未指定项目配置误用了环境规则，产生 45 条诊断；按 CI 的 `--config engine/pyproject.toml` 执行并修复本次新增导入排序，最终通过。原失败日志保留。
- 一个中间冻结构建期间补入按页 Chunk 索引，构建器以 SOURCE_CHANGED_DURING_BUILD 拒绝发布该候选；保留失败记录，最终 verified 候选在源码稳定后重新构建并通过 102 项源码/二进制哈希核对。
- 新增生成元数据测试首次用错已有字段名 text，纠正为 quote 和 E1 映射；测试的是现有格式，未改变生成格式。

最终命令/退出码/数量记录如下，所有原始记录位于 `docs/engineering/evidence/SECTION-AWARE/`，该目录沿用仓库忽略规则、不自动提交原始日志或临时数据库。

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 新增定向 pytest | 41 PASS / 0 FAIL / 0 SKIP，exit 0 | *-targeted-verified.json |
| 项目 Ruff | PASS，exit 0 | *-static-verified.json |
| 完整 Python（含最终冻结侧车） | 395 PASS / 0 FAIL / 0 SKIP，exit 0，125.30 s；1 条既有依赖弃用警告 | *-python-verified.json |
| 最终 macOS ARM64 侧车构建/哈希 | PASS，exit 0；102 项源码及二进制哈希一致 | *-freeze-verified.json / frozen-source-check.json |
| A/B/C 离线比较执行 | exit 0；A/C 可建立索引，B 明确失败 | comparison-verified.json |
| 源码边界、旧迁移和锁 | PASS，20 个旧迁移未变 | scope-check.json；git diff --check |
| Windows 干净机器安装 | NOT EXECUTED | 当前仅 macOS |
| Rust/TS/远端 CI | NOT EXECUTED（本轮未修改这些层，未推送触发） | 无新远端运行 |
| 既有科研评估工具 | BLOCKED，exit 2；scored_cases=0，所有指标无值 | *-scientific-gate.json；scientific-gate/scientific-evaluation.json |

执行命令（仓库根目录，均使用现有环境和已批准本地候选）：

```sh
engine/.venv/bin/python -m ruff check --config engine/pyproject.toml engine/ragsystem tests tools/compare_section_chunking.py
engine/.venv/bin/python -m pytest -c engine/pyproject.toml -q tests/unit/test_section_chunking.py tests/integration/test_section_publication.py
engine/.venv/bin/python -m pytest -c engine/pyproject.toml -q
engine/.venv/bin/python tools/compare_section_chunking.py --model .tools/models/intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3 --output docs/engineering/evidence/SECTION-AWARE/comparison-verified.json
engine/.venv/bin/python packaging/build_sidecar.py --build-label SECTION-AWARE-verified --include-vector-lab --include-generation-lab --include-ocr-lab --include-docling-lab --output-directory .tools/build/SECTION-AWARE-verified-sidecar --evidence-directory docs/engineering/evidence/SECTION-AWARE
engine/.venv/bin/python tools/evaluate_scientific_quality.py --gold docs/evaluation/gold-cases.template.jsonl --predictions docs/evaluation/predictions.template.jsonl --manifest tests/fixtures/public/manifest.json --thresholds docs/evaluation/thresholds.proposed.json --output docs/engineering/evidence/SECTION-AWARE/scientific-gate
git diff --check
```

完整 pytest 提供 RAGSYSTEM_MODEL_DIR（上述 E5）、RAGSYSTEM_OCR_MODEL_DIR（现有 tessdata-fast-65727574dfcd264acbb0c3e07860e4e9e9b22185）、RAGSYSTEM_DOCLING_MODEL_DIR（现有 docling-heron-tableformer-fast-candidates）、RAGSYSTEM_OCR_SCAN_PDF（现有 REMEDIATE-01/derived-BERT-page1.pdf）和 RAGSYSTEM_FROZEN_SIDECAR（最终 verified 目录）。具体绝对路径/argv/时间/退出码见日志及验证清单。未把 Mock 回答或合成页测试当作真实模型质量验收。

## 9. 现有文献启用新策略

1. 在现有备份功能生成备份，并验证恢复到独立目录；保留原 PDF、数据库和旧程序版本。
2. 使用当前源码对应的新侧车打开工作区时仅执行 schema 增量迁移；此操作本身不会自动重切旧文献。
3. 在明确选定文献上执行完整重新解析，以采用 section_paragraph_v1。已有页面局部修复仍可用，但会暂时混合新旧 Chunk；不能把局部重解析称作整篇策略升级。
4. 重新建立当前索引；内容哈希/模型指纹相同的向量复用，不同 Chunk 内容才重算。验证 SourceAnchor、范围和代表性问题后再逐批继续。
5. 失败保留日志和旧快照；需要退回旧程序时从升级前备份恢复到独立目录，不在 schema21 库上直接降级。

本轮没有对用户工作区执行上述批量操作，也没有把源码自动部署到已安装 GUI。用户在旧 App 中看到的旧 Chunk 不会仅因本次源码修改而变化。

## 10. A/B/C 同条件对照

已有公开 fixtures：BERT N19-1423.pdf（16 页）、Dense Passage Retrieval 2020.emnlp-main.550.pdf（13 页），合计 2 篇/29 页。每臂独立临时 SQLite/索引；相同 PDF、两条问题、E5 模型指纹、CPUExecutionProvider、sqlite-vec、hybrid、K=5，不启用重排或付费生成。

E5：intfloat/multilingual-e5-small，revision 614241f622f53c4eeff9890bdc4f31cfecc418b3，384 维、cosine、L2，max_length=512、超限拒绝；完整权重/tokenizer/config/runtime 哈希见 comparison-verified.json。未截断 B 的超限文本来伪装成功。

A=原页内字符边界；B=章节/段落但不做长段切分；C=最终章节/段落+400/80。A 仍经本轮相同存储/元数据管线，耗时不是旧版本程序基准。解析列包括导入、解析和持久化；Embedding 列包括索引构建，B 是失败前耗时。

| 臂 | Chunk | 平均字符 | >400 | 解析/持久化 | Embedding/构建 | 索引状态 |
|---|---:|---:|---:|---:|---:|---|
| A | 424 | 363.31 | 0 | 0.288 s | 6.469 s | completed / 无错误 |
| B | 208 | 588.67 | 72 | 0.290 s | 0.893 s | failed / EMBEDDING_CONTEXT_LIMIT |
| C | 574 | 264.33 | 0 | 0.304 s | 7.629 s | completed / 无错误 |

A 新算 424 条向量；C 新算 571 条（574 个 Chunk 中有相同内容复用）。C Chunk 数比 A 多约 35.4%，单次构建时间也增加，不能宣称性能优化。C 对 BERT 第 2 页局部重解析后，549 个未选页 Chunk 保持 ID，索引复用 571、新算 0，574 个当前 Anchor 全部通过原文/文件校验。

原文切片内部一致性：A 424/424、B 208/208、C 574/574。**这不是独立人工评估的证据定位准确率，也不是引用准确率**；PDF 坐标仍诚实降级为 page_only。工程检查只证明切片/哈希/关联可追溯。

相同问题为 “What is masked language modeling?” 和 “How does dense passage retrieval work?”；A/C 各两轮返回 5 个结果并保存排名、章节及 Anchor。B 因长段超出模型上下文而不能完成同条件向量检索。现有 gold-cases/retrieval-cases 模板为空，无法公平计算跨新旧 Chunk 的 Recall@5、MRR、nDCG，也未执行新回答人工支持性审查；这些值均 NOT EVALUATED。没有以两题演示替代科研验收或宣称 C 优于 A。另实际运行仓库既有 evaluate_scientific_quality.py 对现有空金标/预测模板进行门禁检查：exit 2 / BLOCKED / scored_cases=0，记录了金标、类别、人工审查、样本量及阈值尚未批准等阻塞项；没有降低阈值或编造标注。

## 11. 一篇真实 PDF 的完整链路

论文：**BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding**，本地公开 fixture `tests/fixtures/public/N19-1423.pdf`，SHA256 `987545ffb087f1ece898142c403a516baeabeb70ce19089397fac6f7db12c3d4`。

```text
BERT PDF（16 页，PDFium 实际提取）
  → 3 BERT（第 3–5 页）
  → 3.1 Pre-training BERT（二级，第 4–5 页）
  → 第 5 页逻辑段落 [434,1265)，831 字符
  → [434,732)、[652,975)、[895,1265)
  → 长度 298/323/370，相邻重叠 80/80
  → 同一 paragraph_id 与 [3 BERT, 3.1 Pre-training BERT]
  → 原文切片 SHA256 + E5 持久向量
  → sqlite-vec/hybrid 检索命中与 page_only 来源定位
```

该次隔离试验的真实标识（随机 UUID，不是产品固定标识）：

- doc_version_id：`ec4377a8-94f0-4ef9-8ae4-658e90eab9c8`
- parse_run_id / 初次结构 publication_id：`593bf51f-0e7e-47cd-b1ca-8819f64e4240`
- element_id：`1263082b-0a19-484c-9c70-f635810e3bf8`
- section_id：`3bc623a3-c1ea-4c42-894c-d5f06a86e5e9`；parent：`c990c3fa-5b20-4c2c-8050-72387bdbf5fd`
- paragraph_id：`8e726f9c-2792-4e61-8c32-89eedea43d32`
- 首个子 Chunk：`7f07fd87-fdf8-4932-8245-d1b1eef536b3`，page=5，offset=[434,732)
- content_sha256：`d1a92b9a32433735a017198cd19cc1bb63affc9af8a3123c467075378fa2c4ea`
- embedding_id：`4c448bcd-8937-44c2-96ad-277401c5a5d6`

原文开头为 “The NSP task is closely related to representation…”；换行、特殊断词字符完整保留在 JSON 中。`comparison-verified.json` 的 `arms[2].real_example` 保存完整 Chunk/元数据/Anchor。另以 “What objectives is the NSP task related to?” 在该 PDF 内实际 hybrid 检索，首位命中上述 Chunk；见 `real-pdf-example.json`。这是单例可追溯演示，不是 gold relevance 或回答正确率。

## 12. 风险、限制与尚未完成事项

- 原生文本段落/标题是保守启发式，遇到无空行、多栏阅读顺序、跨行标题、表格和公式可能漏识别。真实 BERT 的部分跨行标题仅保留首行；没有宣称章节树完全正确或覆盖所有期刊版式。需要真实版式/段落金标评测后再扩展字体、缩进和几何能力。
- 规则置信值未校准；跨页自然段续接未推断；没有强制短段合并。短标题也进入原有检索，Chunk 增多有召回/排序成本，需金标决定后续策略。
- 400 字符不是任意语言下 512 token 的数学保证；本次公开英文样本 C 成功，其他文本仍可能触发已有 EMBEDDING_CONTEXT_LIMIT，未绕过模型上限。
- 元数据重建在现有原子发布事务内；逐页有界且有索引，但 1000 篇/极限 500 页文档、并发导入、RAM/P95 和磁盘放大量未实测。结构历史快照随解析次数增长，未新增自动清理。
- Windows 干净机器/签名/安装/发布，以及远端 CI 未执行；本轮本机侧车测试不替代这些门禁。构建可选包钩子仍有非必需子模块警告，记录保留。
- 无独立人工科研金标，Recall/MRR/nDCG、引用语义准确率和回答支持性仍未验收；不把模型自评当人工金标。
- 没有更换 Embedding、重写检索算法、改前端或自动部署旧 App；实际用户库策略升级仍需用户选择范围后执行。

## 13. 阶段状态

代码与隔离验证已完成，可供本地代码审阅；科研质量和真实 Windows 发行门禁保持 BLOCKED/NOT EXECUTED，不作发布 GO。设计记录采用任务契约 v0.12（没有变更主架构，不新增架构 ADR）。需要后续人工标注/验收的仅为科研与平台门禁；本任务已授权的实现与测试自主完成。最新用户禁止直接推 main 的要求优先于历史任务的推送授权。

最终侧车 SHA256：`e6ef0680e523a640c968f938ef35f7dc47cf2fe7683450fad20ce15d9a35e590`；manifest：`docs/engineering/evidence/SECTION-AWARE/sidecar-20261106T032854876253Z.json`。产物是隔离开发侧车，不是新 GUI 安装包。
