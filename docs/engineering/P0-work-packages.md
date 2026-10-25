# P0 独立工程包与验收计划

日期：2026-10-24。状态：PROPOSED；只有 P0-00 本轮审查已获授权。以下文件与测试命令均为未来计划，不表示已经存在或执行。负责人统一为 Codex 实施、用户批准；Windows 操作/科研标注负责人须由用户指定。每包各自建立 ExecPlan、报告和 `docs/engineering/evidence/P0-xx/`，任务退出由用户复核。

## 范围与依赖

P0-00 → P0-01 与 P0-02；02 → 03 → 04 → 05 → 06；01/04/05/06 → 07；08 从 02 开始贯穿，06 后补完整后端恢复；01—08 → 09 → 10。该图表示工程依赖，不授权并行 Agent 或同时开工。当前不创建远程仓库或 CI；本地可复现脚本是本轮用户约束下的建议执行替代，非取消源文 §10.4 的长期自动化目标。

## 任务与文件

| ID / 需求 | 输入/前置 | 预计新增或修改的具体路径 | 独立退出证据 |
|---|---|---|---|
| P0-00 / §§2–4、7–11 | 原方案、启动包、用户授权 | `execplans/P0-00.md`、本表、资源登记、审查报告、ADR-001—007、PLANS 和任务状态 | 文档与原始检查证据；缺资源明确 BLOCKED；用户确认后续范围 |
| P0-01 / §§2.3–2.4、8.1 | 00、IPC 决议、Win 构建/验收资源 | `apps/desktop/package.json`、`src/App.tsx`、`src-tauri/{Cargo.toml,tauri.conf.json,src/sidecar.rs,src/ipc.rs,capabilities/default.json}`、`engine/ragsystem/ipc/{server.py,auth.py,protocol.py}`、`packaging/{sidecar.spec,build-windows.ps1}` | G01/G03/G11/G13：真实安装启动退出/鉴权/单实例；完整文件见 ExecPlan |
| P0-02 / §§3、7、8.4 | 00、身份/Job 子契约、真实 PDF | `engine/ragsystem/storage/{database.py,migrations.py,files.py,documents.py}`、`storage/migrations/0001_initial.sql`、`jobs/{repository.py,state_machine.py,recovery.py}`、`ingestion/import_pdf.py`、对应契约 | G04/G10：不可变 SHA、幂等、短事务/租约/迁移故障恢复；完整文件见 ExecPlan |
| P0-03 / §§4.1–4.2、9.2 | 02、PDF/解析器许可与金标、ADR-007 | `engine/ragsystem/parsing/{pdfium_extractor.py,quality.py,router.py,artifacts.py}`、条件启用 `docling_adapter.py`、`ocr_adapter.py`；实体字典 ParseRun/Page 状态 | G05：真实逐页提取/路由/失败记录；增强调用未授权即阻塞，不静默省略 |
| P0-04 / §§4.2、6.2 | 03、ADR-002、人工标注 | `engine/ragsystem/chunking/{splitter.py,mapping.py}`、`parsing/coordinates.py`、`domain/source_anchor.py`；`contracts/source-anchor.schema.json`、OpenAPI SourceAnchor 子集 | G06：版本/页/区域正确，旋转/CropBox 实测；不可靠 page-only |
| P0-05 / §§3.1–3.2、4.4 | 04、批准的模型/权重许可与哈希 | `engine/ragsystem/indexing/{spaces.py,embeddings.py,incremental.py,publication.py}`、`storage/embedding_records.py`、`models/registry.py`；实体字典向量关联 | G07/G09：重启/重复/新增 10 篇仅重算变化内容；新空间隔离 |
| P0-06 / §§3.3、3.6、9.5 | 05、同一冻结向量/查询/过滤/机器 | `engine/ragsystem/vector_adapters/{base.py,sqlite_vec.py,lancedb.py}`、`tools/benchmark_exact.py`、`tests/integration/test_vector_contract.py`、`docs/evaluation/results/P0-06/`、ADR-001 | G08/G09：两候选相同条件原始结果、过滤内 exact、恢复和许可；保留失败候选 |
| P0-07 / §5、§10.4 | 01/04/05/06、源文范围差异经确认 | `apps/desktop/src/features/{library/LibraryView.tsx,reader/PdfReader.tsx,diagnostics/IndexStatus.tsx,search/SearchPanel.tsx}`、`src-tauri/src/file_grants.rs`、`engine/ragsystem/retrieval/source_search.py` | G06/G09/G11：真实后端命中→授权 PDF 原版本/页/区域；不实现 P3 Claim 或 P4 Research |
| P0-08 / §§3.5、7、8 | 从 02 开始；06 后双候选补齐 | `engine/ragsystem/storage/{backup.py,manifest.py,reconcile.py}`、`jobs/recovery.py`、`src-tauri/src/file_grants.rs`、`tests/integration/test_backup_restore.py`、`tests/security/test_file_grants.py` | G10/G11：快照/Manifest/故障恢复与授权；无批量删除，隔离孤儿文件 |
| P0-09 / §9 | 01—08、8/16GB 干净 Win11、真实分层语料 | `packaging/collect-windows-evidence.ps1`、`tests/desktop-e2e/P0-windows-matrix.md`、`tools/report_benchmark.py`、`docs/evaluation/results/P0-09/` | G01—G13 分类汇总；P0 组件时延、P2 混合目标分开；不足规模不得宣称千篇支持 |
| P0-10 / §§9–10 | 09、所有报告和失败原始记录 | `docs/engineering/reports/P0-gate-review.md`、PLANS、任务板、待决簿、已审批 ADR | G14：GO/CONDITIONAL GO/NO-GO/BLOCKED 建议与人工批准；未批准不进入 P1 |

上表未带前缀的 `execplans/`、资源表、审查报告位于 `docs/engineering/`。所有非 P0-00 应用路径当前均未创建。具体文件名可在各任务开工前按已批准契约细化，不借此扩张业务范围。

## 检查命令与真实资源

未来 Python 测试统一先在 `engine/pyproject.toml` 锁定 pytest 及配置，确保项目包可导入。下表 `PY` 表示批准后创建的 `engine/.venv/Scripts/python.exe`（Windows）或 `engine/.venv/bin/python`（macOS 辅助测试）；不是当前可运行脚本。单元/集成故障反例可使用合成数据，但科研、容量与 Windows 结果必须用相应真实输入。

| ID | 拟运行命令/步骤（本轮未执行，00 除外） | PDF/Windows 要求与停止条件 |
|---|---|---|
| 00 | `python3 tools/validate_kit.py`；原始 Manifest/源文件/文档引用核对 | 当前 macOS 仅做静态审查；设备/金标缺失登记阻塞 |
| 01 | `PY -m pytest tests/unit/test_ipc_auth.py tests/integration/test_sidecar_lifecycle.py`；`cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --locked`；`pwsh -File packaging/build-windows.ps1` | 无 PDF；干净 Win11 x64 普通用户、中文/空格路径；缺设备不判通过 |
| 02 | `PY -m pytest tests/unit/test_job_state_machine.py tests/unit/test_content_identity.py tests/integration/test_import_atomicity.py tests/integration/test_job_recovery.py tests/integration/test_migration_recovery.py` | 一份真实许可 PDF及不同字节版本；Win 文件锁/改名/断电；原件异常即停 |
| 03 | `PY -m pytest tests/scientific/test_pdf_quality.py` | 先最小合法样本，再扩 30–50 篇；普通/双栏/表格/扫描/混合/坏页；真实 Windows 打包运行；无金标不定阈值 |
| 04 | `PY -m pytest tests/unit/test_coordinates.py tests/scientific/test_source_anchor.py` | 旋转 0/90/180/270、CropBox、双栏/表格/OCR；Win 阅读器缩放对照；错版本/伪框即停 |
| 05 | `PY -m pytest tests/integration/test_embedding_persistence.py tests/integration/test_incremental_embedding.py` | 冻结基线+10 篇真实新增 PDF、批准本地模型；Win8/16GB；许可未审或旧向量全算即停 |
| 06 | `PY -m pytest tests/integration/test_vector_contract.py`；`PY tools/benchmark_exact.py --help` 后按预注册参数分别运行 A/B | 同机同向量/距离/过滤/查询；每次原始日志；候选不可运行保留失败，无法公平比较即 BLOCKED |
| 07 | `npm --prefix apps/desktop run typecheck`；`tests/desktop-e2e/P0-07-source-jump.md` 人工用例（待创建） | 真实检索→真实 PDF；Win125%/150%、范围授权、fallback；UI mock 不算验收 |
| 08 | `PY -m pytest tests/integration/test_backup_restore.py tests/integration/test_failure_recovery.py tests/security/test_file_grants.py` | Win隔离测试根+真实 PDF/持久向量；跨存储快照、满盘、崩溃、越权；不对旧库故障注入 |
| 09 | `pwsh -File packaging/collect-windows-evidence.ps1`；`PY tools/report_benchmark.py --help` 后按实际数据运行；人工安装矩阵 | 8/16GB Win11；实际100/1000篇，3000仅扩展建议；语料不足如实 BLOCKED/NOT EXECUTED |
| 10 | 复核 G01—G14→逐项引用实际报告→用户签字 | 所有关键 gate 有证据；未执行/失败不能变为 GO |

`--help` 只是核对未来工具入口，不是性能或验收结果。每轮在冻结脚本后填写准确命令、参数、退出码、设备、输入 SHA、运行时间和日志；不得从本表推断已有 pytest/npm/Rust 工程或已测结果。

## 裁定顺序

先解决 P0-01 的路径、IPC、依赖/设备条件，再 P0-02 真值/故障恢复；解析→来源→向量→GUI 按依赖推进。对用户已有资料的删除、迁移、云发送和模型下载保持独立授权。各包失败先修复已批准范围，无法修复列最小阻塞，不跨阶段补做后续功能。
