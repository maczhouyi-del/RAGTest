# 核心实体字典（P0 初稿；非已审批 SQL）

**依据：** v1.1 §3.1–3.5、§6.2、§7.1。

## 数据真值与存储分层

| 对象 | SQLite 权威字段/唯一性建议 | 文件系统/派生层 | 生命周期或一致性约束 |
|---|---|---|---|
| `Document` | `id`, 标题/DOI/作者/规范化逻辑身份 | 无 | 不能简单用 DOI 当唯一文件；同一论文可能有多个文件版本 |
| `DocumentVersion` | `id`, `document_id`, 版本描述、当前可见性、源版本序号 | 对应不可变原件引用 | 版本不可覆盖；删除先撤销检索可见性 |
| `FileAsset` | `sha256`（或 id+唯一 SHA）, size_bytes, media_type, state | `papers/<sha256>.pdf` | SHA 校验/去重；原件写入采用 temp + fsync/原子改名等故障安全方式，并在 Windows 实测 |
| `DocumentVersionFile` | `doc_version_id`, `file_asset_id`, 作用/主附件标识 | 无 | 支持版本关联文件，不以文件哈希决定逻辑论文身份 |
| `Project` / `ProjectDocument` | `project_id`, `document_id`, 关联属性 | 无 | 多项目/论文多对多；P1 实现完整 UI |
| `ParseRun` | `id`, `doc_version_id`, parser_version, config_fingerprint, status, quality_signals, started/finished | 原始 Element/坐标结构化产物 | 每页错误与部分成功可见；升级解析保留旧运行记录 |
| `Element` / `SourceRegion` | `id`, `parse_run_id`, page, structural_type, source_anchor mapping | 页坐标/表格结构 | 无法证明区域可靠时降级到 page-only |
| `Chunk` | `id`, `doc_version_id`, `parse_run_id`, content_sha256, clean_text, offsets, visibility | 可根据 ParseRun 重建 | chunk 对应来源映射必须存在，不能引用另一个版本 |
| `EmbeddingSpace` | `id`, model_weight_sha256, tokenizer/preproc hash, dim, metric, normalization, status | 权重引用 | 影响向量可比性参数变化 → 新空间 |
| `EmbeddingRecord` | `id`, chunk fingerprint, space_id, vector storage ref/status | 持久向量字节或其可核对引用 | 可按内容+空间指纹复用；不得跨不兼容空间共享 |
| `IndexGeneration` | `id`, space_id, status: STAGING/ACTIVE/RETIRED, manifest | sqlite-vec/LanceDB 派生结构 | 仅换空间或全量重建采用世代切换，新增 1–N 篇直接幂等 upsert/delete |
| `Job` / `JobAttempt` / `Event` | 幂等键、lease_until、心跳、attempt、status、错误码、日志/结果引用 | 有界任务副产物 | short txn，耗时推理/解析事务外；过期租约可恢复 |
| `ScopeSnapshot`（P2+） | 此轮允许 `doc_version_id` 快照/过滤/时间及 scope hash | 无 | 不可越过本轮授权范围；会话历史不是证据 |
| `EvidenceSpan` / `Claim`（P3） | 来源版本、清洗偏移、条件限定、自动核验/人工复核各状态 | 引用 PDF 的锚定关系 | Claim/Evidence 与人工审查分离；不可以字符串出现代替语义支持 |
| `StudyObservation` / `EvidenceMatrix`（P4） | paper/实验行/指标/数值/单位/实验条件/源表格单元/审查状态 | 报告修订/附件 | 研究覆盖需逐篇处理清单、缺失与不可比说明 |

## 主键和外键原则

- 内部 ID 使用稳定不可变标识符，跨端传输统一编码为字符串；不将文件路径当实体主键。
- 所有引用到 DocumentVersion 的子实体必须指向**特定版本**，不能仅指 `Document`（否则一篇论文更新后会错引旧版本）。
- `Chunk` → `SourceRegion` 的多对多映射允许一个段落跨区域/页面；不得以简单 page/bbox 假定所有文本连续。
- 源文正文单独保存，不得把检索清洗文本覆盖原始解析文本。`EmbeddingRecord` 使用其内容和 EmbeddingSpace 完整指纹。
- 若复用相同内容的向量但保留不同论文 Chunk 的证据定位，应考虑 `ChunkEmbeddingLink` 辅助映射；这是**实现设计待决项**，不在 v1.1 已审批实体名单中。
- SQLite `foreign_keys=ON`、事务原子提交、缺失/孤儿引用拒绝发布、schema migration 版本记录。

## 目录与备份

建议数据根 `%LOCALAPPDATA%\\RAGSystem\\`（用户可迁移），包含 `data/research.db`、`papers/`、`parsed/`、`vectors/`（LanceDB 时）、`models/`、`reports/`、`backups/`、`logs/`、`manifests/`。从用户选择的其他盘符迁入/恢复需先校验 SHA，用户卸载不默认删除原件。

**备份核心条件：** SQLite Online Backup API 用于 DB 一致快照；外部 PDF/解析/向量/报告须有与该快照一致的 Manifest 或足以恢复的明确重建策略。不能将“可重建索引”与“可重建已付费/昂贵 Embedding”混同。备份可不含可重建检索索引，但含不含 Embedding、权重如何恢复必须明确告知。
