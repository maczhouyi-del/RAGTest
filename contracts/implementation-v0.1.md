# P0 实现子契约 0.1.0（实验实现，待冻结）

2026-10-24。对应v1.1 §§2–4、7–8、ADR-001/002/003/004/007/008。保留原`0.1-draft`草案；本文件说明实际实现差异，不把原草案中未实现功能标为可用。更改实验协议须同步Rust/TS/Python并更新版本；不承诺未发布数据库向后兼容，已有库始终先校验migration checksum/版本、升级前Online Backup。

## 信任边界和启动

React仅调用固定Tauri命令；Rust持有每次随机生成的32字节会话token，固定二进制路径，清理继承环境中的未列入允许名单变量。Sidecar通过匿名stdin接受一行≤16KiB JSON：`protocol_version=0.1.0`、64位小写hex `token`、绝对`data_root`。stdout仅协议版本+随机端口，不回显token；Rust再用token探测health。只绑定IPv4 `127.0.0.1`；Host必须为该IP，拒绝任何Origin、CORS、无/错/重复token，正文≤16KiB。此方案不能防御同一OS账户已被控制的恶意进程，不宣称OS沙箱或命名管道ACL。

启动/请求/关闭超时15s/5s/7s；关闭先EOF，后强制终止。固定解析worker监督超时40s，单worker串行调用PDFium，父进程死亡监测；Windows监测分支已写但未执行。页数≤500，每页≤50k字符，全文≤1.5M字符，输出≤8MiB；Mac内存上限及OS级网络隔离未实现。

## 已实现 API 与投影

所有端点包括health均鉴权。错误只返回稳定`code/message/retriable`，不反射Pydantic输入、路径、PDF内容或token。

| 接口 | 实际语义 |
|---|---|
| GET `/v0/health` | ready、引擎版本、能力和未配置原因，不代表Windows/科研验收 |
| POST `/v0/internal/file-grants` | 仅Rust原生选文件后调用；输入绝对本地路径，持有打开的只读句柄并固定SHA，拒绝符号链接/junction/UNC、超64MiB；120s期限、最多16份 |
| POST `/v0/imports` | `file_grant_id`+幂等键；不接受UI路径；单worker忙返回429；202表示已接收，需查询Job |
| GET `/v0/documents` | 当前库可见文件版本、标题、大小、hash、解析状态；尚非P1项目/论文身份管理 |
| GET `/v0/jobs`、GET `/v0/jobs/{id}` | P0投影：`job_id/type/status/attempt_count/max_attempts/error_code/result_ref/updated_at`；无payload/token/path，不等同job.schema完整实体 |
| POST `/v0/jobs/{id}/cancel` | 立即撤销发布租约并持久cancelled；不保证解析计算立即停止，受40s监督上限约束 |
| POST `/v0/documents/{version}/parse` | 幂等键，202，页文本提取/不可变ParseRun；空白页标待OCR，错误页不生成Chunk |
| POST `/v0/search` | `fts_only`，按可见文献版本范围先过滤再Top-K；`vector_exact`明确409未配置，不悄悄退回FTS |
| GET `/v0/source-anchors/{id}` | 以Chunk ID为稳定来源ID，重新检查可见性/原文substring/PDF hash；仅页级，无虚构bbox |

Rust命令：workspace_snapshot、choose_pdf_and_import、restart_engine、cancel_job、parse_document、search_sources、read_source。ID验证防止路径/路由注入。read_source只从授权anchor取得SHA后读固定papers目录并校验≤64MiB/hash；JS不拿路径和token。当前scope为单用户整个本地工作区，客户端版本列表只是检索子集；尚未实现P2 ScopeSnapshot/多项目权限，不可将客户端列表作为外部认证依据。

## 数据、任务与来源

SQLite `user_version=3`，WAL/FK/FULL、短写事务；PDF按SHA create-only发布，重复文件复用同版本。P0一个FileAsset对应一个DocumentVersion；P1逻辑论文/多项目/版本合并另行迁移。跨文件系统和SQLite不声称原子事务：先持久任务意图，原件发布后可按SHA恢复；失败/staging保留，不自动清理。租约token/CAS防止过期或取消worker发布；重启回收过期租约，不在未过期时假装安全接管；自动调度/重试UI尚不完整。

ParseRun含PDFium版本+分块参数指纹，页文本不做有损清洗；Chunk切片最大1200字符并尽量按换行。offset单位为Unicode codepoint，半开区间，TS不得直接以UTF-16索引替代。page_number从1开始，真实rotation；定位`page_only/bbox=null/alignment_confidence=unknown`，符合原SourceAnchor草案。重解析提交时同时撤下旧可见Chunk，失败保留旧结果；不能据文本非空判定科研正确。

EmbeddingSpace包含模型revision/权重/tokenizer SHA、预处理、归一化、维度、距离和运行时；向量float32原始BLOB持久化，内容hash与空间复用、Chunk独立关联。sqlite-vec/LanceDB两候选仅实验适配器，没有最终后端或已发布IndexGeneration。模型只在显式本地试验加载，不在默认应用自动下载/启用。

备份使用OnlineBackup+被引用原件SHA manifest；恢复只允许新目录并校验路径、hash、FK/integrity。原始向量随SQLite备份，外部索引恢复后重建；没有LanceDB与SQLite跨存储同点快照保证。备份库接口已测，GUI流程未交付。

未实现：Docling/OCR、表格结构/区域坐标、中文分词策略、混合检索/重排、LLM、Claim/Evidence核验、Research逐篇覆盖、云密钥、迁移旧数据、签名发布。现有API/DB不能作为这些能力已完成的证据。

## MVP-02 B additive conversation API (2026-10-25)

SQLite v15 adds conversations.updated_at, backfilled from existing answers, with activity/turn indexes. Existing answer and evidence IDs unchanged; migration saves pre-upgrade snapshot. POST /v0/conversations creates a conversation; GET /v0/history/conversations uses existing bounded cursor envelope sorted by recent activity; GET /v0/conversations/{id}/turns returns latest bounded page in chronological order with cursor for older pages. Existing answer/history endpoints remain supported. Rust validates UUID/cursor and uses authenticated engine bridge. A run can append to an existing conversation; concurrent active run rejected. History context is last <=3 turns/1600 text characters, is not evidence, and current retrieval/citation/support verification remains mandatory. External per-request consent includes bounded history. Prompt fingerprints updated for history semantics, no generation quality thresholds changed.

## MVP-02 C provider compatibility (2026-10-25)

SQLite v16 adds vendor/auth_mode/output_mode/token_parameter only; no secrets persisted. Existing bearer configs without a nonempty current key are unavailable (previous empty-key readiness was a bug). Explicit none authentication is restricted to loopback custom services. Probe accepts auth_mode and returns an opaque credential_token (single save, <=10 minutes, <=16 drafts, bound to endpoint/type/auth) while plaintext credentials stay in engine memory. Save can consume this draft without reentering key; key/token are never included in SQLite/jobs/fingerprint. Public status separates saved, credential_available, connection_verified, generation_verified and last_error; restart clears verification/credentials. GET models verifies directory/auth only; successful structured generation verifies generation separately. User-selected json_object or prompt_json and budget parameter are fingerprinted, never auto-switch/retry. Invalid citations still fail. API configuration/probe does not send PDF/question/context. Each answer requires explicit consent covering question, bounded history and current excerpts. Known local prompt v9→v10-history upgrade only is compatible when all remaining model/runtime/hash fingerprint fields match; no embedding change.

## MVP-02 D bibliographic metadata (2026-10-25)

SQLite v17 adds abstract/field_origins_json to document_metadata and metadata_candidates with immutable version, field/value/method/page/excerpt/extractor/review provenance. Existing origin='manual' column is legacy row provenance; field_origins_json is authoritative for per-field priority, with migration default protecting existing manual values. Automatic candidates overlay manual metadata only for unprotected fields; originals/chunks/indexes unchanged. MetadataUpdate adds optional abstract/field_actions/doc_version_id; old callers retain behavior and do not erase an omitted abstract. keep preserves current value, manual edits protect, confirm freezes current value, candidate UUID explicitly adopts that version's candidate. CAS revision remains mandatory. Import atomically registers one verify/extract_metadata intent per version/extractor. Engine lifespan pump resumes queued/retry intents independently of React/parse/index worker, reads <=2 pages via supervised PDF worker (30s), persists failure and supports retry. No external metadata services/models. Unknown fields empty, title can remain filename fallback; creation date never used as publication year. Original abstracts are not generated summaries. Backup includes candidates/field provenance with SQLite; restored unfinished jobs remain fenced/retry_wait before bounded safe recovery.
