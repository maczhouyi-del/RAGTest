# P0 本地实现、双平台准备与门禁审查

- Task ID / 阶段：P0-01—10局部实施与P0-00资源更新 / P0。
- 评审日期：2026-10-24；执行人：Codex；批准人/验收签字：尚无。
- 建议：**BLOCKED。全系统未完成，未进入P1—P5，不能自动宣布GO。**
- 功能测试：**PASS（仅本报告列出的本机测试范围）**。
- 真实Windows安装测试：**BLOCKED / NOT EXECUTED**。
- 科研质量测试：**BLOCKED（无人工金标）**。
- Git：当前没有Git仓库/commit；没有init、remote、push、GitHub或发布操作。当前工程仍为`/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem`，未改名或操作旧项目。

## 1. 授权与实际范围

P0-00历史规划交付后，用户明确要求“继续开发全部功能”，随后要求Windows/macOS兼容，并确认当前Mac和另一台Windows电脑均16GB。该授权允许继续实现，不能代替阶段验收。用户暂无个人PDF/科研金标；公开许可样本用于基础工程试验。用户另行明确批准下载官方intfloat/multilingual-e5-small固定revision候选做本地试验，未预定最终模型。

当前会话只能执行Mac命令，不能访问另一台Windows电脑。Mac实测OS26.2、arm64、RAM17179869184bytes；另一台电脑OS build/CPU/干净环境尚未核对。8GB原要求未被取消，仍未测。无付费API/云推理调用，无用户PDF/源码/凭据上传；联网仅公开文档、依赖/工具链、两篇公开论文和该次批准模型获取。没有删除/迁移旧数据，也未安装Skill/插件。

已读取根AGENTS/README/PLANS、v1.1原文/提取文本/图、阶段任务与契约、00-plan-only及后续P0任务指令。新增实施依据是后续用户指令；旧文档“仅规划/未授权”按历史保留并更新当前状态。

## 2. 实际成果和文件

| 范围和实际变更文件 | 用户可观察结果 / 需求与契约对应 |
|---|---|
| `engine/pyproject.toml`、`uv.lock`、`.python-version`；`apps/desktop/package*.json`、TS/Vite配置；RustCargo/lock/toolchain；`.gitignore` | 固定本地开发依赖，Python3.12.13、Rust1.99.1、Node22.22.1；v1.1 §§2.4、8、9；未引入Docker/PG/Redis |
| `engine/ragsystem/storage/`三版migration、`jobs/`、`ingestion/`、`ipc/grants.py` | SQLite WAL/FK/FULL，checksum校验/升级前备份；SHA不可变原件、幂等冲突/租约fencing/任务恢复；§§3、7，实体/Job草案的P0实现子集 |
| `ipc/server.py`、`__main__.py`，Rust `src/sidecar.rs`、`src/lib.rs`、capability/CSP | stdin会话凭据、随机127.0.0.1端口、token/Host/Origin/正文限额、固定Tauri命令、原生文件授权、生命周期；§§2.3、8.3/8.6；ADR-003实验路线 |
| `parsing/`、`chunking/`、`retrieval/source_search.py` | PDFium隔离子进程、逐页状态、无损codepoint offset、版本/页/SHA来源校验、范围先过滤FTS、页级降级；§§4.1/4.2、6.2；不声称表格/科学符号提取正确 |
| `indexing/`、`models/local_onnx.py`、`vector_adapters/` | 全指纹空间、持久float32原向量/Chunk关联、严格增量、sqlite-vec/LanceDB exact候选、真实批准模型仅本地CPU推理；§§3.1—3.3/3.6、4.4 |
| `storage/backup.py`与集成故障测试 | OnlineBackup、被引用原件hash manifest、新目录恢复、FK/integrity、原向量重建；§§3.5、7、8.4；无跨存储原子快照声明 |
| `apps/desktop/src/`和`src-tauri/` | 原件列表/导入/解析、持久任务/取消/重启、FTS来源和PDF.js页预览、真实未配置提示；§5的P0最小子集；默认GUI未接向量/LLM |
| `packaging/`、`tools/collect-windows-evidence.ps1`、`tests/desktop-e2e/P0-platform-acceptance.md` | Mac冻结Sidecar和debug app，Windows本地构建/人工验收准备；§§2.4、8.1、9.4。Windows脚本未运行 |
| `tests/unit/`、`tests/integration/`、`tests/fixtures/public/`、`tools/smoke_*`/`browser_smoke.cjs`/`benchmark_local_candidates.py` | 反例/真实进程/真实PDF/真实模型与浏览器、原生启动分开取证 |
| `contracts/implementation-v0.1.md`、ADR-008、本轮ExecPlans、PLANS/README/任务板/资源/待决表、`docs/legal/`、`THIRD_PARTY_NOTICES.md` | 当前实际协议/差异、双平台授权、证据与许可，不自动批准最终选型 |

完整文件SHA和相对P0-00快照的差异见本轮证据目录`source-snapshot.json`。原始`MANIFEST.sha256`未重写，不是新版本校验表；原需求DOCX/提取文本/图和原`tools/validate_kit.py`保持原hash。生成的失败日志、旧构建目录/staging保留，没有用清理规避删除限制。

## 3. 已执行命令、平台、退出码、日志位置

以下均在macOS26.2 arm64执行；原始JSON含UTC时间、完整argv、cwd、退出码和合并输出。目录统一为`docs/engineering/evidence/P0-implementation-2026-10-24/`。`commands-index.json`汇总所有成功/失败记录，不删除红灯。

| 检查/实际命令（项目根目录） | 退出码与结果 | 原始日志 |
|---|---|---|
| `engine/.venv/bin/python -m pytest -c engine/pyproject.toml`，显式提供RAGSYSTEM_FROZEN_SIDECAR和RAGSYSTEM_MODEL_DIR | 0；**42 passed，5.78s**，无skip，含真实2篇PDF/本地模型、两个候选和冻结Sidecar | `20261024T061739795617Z-python-final-all-real.json` |
| 项目Rust环境 `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --locked` | 0；2 passed，含真实冻结sidecar健康/401/EOF | `20261024T061939098672Z-rust-final-tests.json` |
| `cargo fmt`、`cargo clippy --locked --all-targets -- -D warnings`（同manifest） | 0；fmt/clippy通过 | `20261024T061728857178Z-rust-format.json`；`20261024T062159072662Z-rust-clippy-final.json` |
| `npm --prefix apps/desktop run tauri -- build --debug --bundles app` | 0；TypeScript/Vite与Tauri原生app构建通过，app约59.74MiB | `20261024T061739795537Z-mac-native-app-build.json` |
| `engine/.venv/bin/python packaging/build_sidecar.py` | 0；Macarm64冻结二进制23530736bytes | `20261024T061703778680Z-frozen-sidecar-final.json`及sidecar manifest |
| `engine/.venv/bin/python tools/smoke_native_macos.py` | 0；真实WebView触发Rust→随包Sidecar，中文/空格测试目录；父进程终止后2个sidecar进程均退出 | `20261024T062021938989Z-native-macos-smoke.json`、`native-macos-40b8df9b-12f8-4b3c-831b-309bb3966ab1.json` |
| bundled Node执行`tools/browser_smoke.cjs`，RAGSYSTEM_PLAYWRIGHT_DIR指向已装Playwright | 0；真实冻结引擎导入/解析/FTS/SHA校验PDF画布。**Tauri传输层模拟**，不是原生文件对话框或Windows验收 | `browser-smoke.json`、`browser-*-preview.png`与末次命令日志 |
| `tools/smoke_public_corpus.py` | 0；2篇/29页/119Chunk，原件去重、来源、备份恢复完整性 | `20261024T055552728390Z-public-pdf-smoke.json`、`public-corpus-smoke.json` |
| `tools/benchmark_local_candidates.py` | 0；批准模型384维，持久/增量/重启/两个exact候选/oracle/重建/恢复 | `20261024T060651170600Z-real-model-vector-ab.json`及`real-vector-ab-c59af7c4-e486-4ad1-b41c-400b560f08e5/` |
| `tools/download_approved_model.py` | 0；固定revision五个文件大小/hash校验 | `approved-model-download.json`及下载命令日志 |
| `tools/dependency_inventory.py` | 0；59个Python安装分发、93条npm lock包、458条Cargo lock包的元数据与可见许可文本 | `20261024T061938420645Z-license-inventory.json`；`docs/legal/dependency-inventory-20261024T061939040492Z.json` |
| ruff检查实际新代码，显式`--config engine/pyproject.toml`；`sh -n packaging/build-macos.sh`；`tools/validate_kit.py` | 0；lint/语法/静态文档结构通过；不作为应用或科研验收 | `*-source-style-check.json`、`*-final-kit-check.json`；sh语法仅本机执行输出 |
| Windows构建/安装、8GB、干净Mac/Intel/最低OS、人工金标、100/1000篇 | **NOT EXECUTED / BLOCKED** | 无PASS记录；人工用例表待填 |

Mac测试环境变量：`RAGSYSTEM_MODEL_DIR=$PWD/.tools/models/intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3`，`RAGSYSTEM_FROZEN_SIDECAR=$PWD/apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin`。Rust使用项目`.tools/cargo`、`.tools/rustup`，不依赖系统PATH原本有Rust。

产物SHA256：

- Mac sidecar：`6c495a21ea0ec338f37903eb87c34ae1f53de3743d33359bc4dad4230d8b3542`。
- app内主程序：`7ebab29babbf7dc06fc8d3eeabaef0dd29e9736e782daa60917c137e427c7222`。`.app`是目录，不能把主程序hash说成整个app的hash。
- 模型ONNX：`ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`；tokenizer：`0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`。
- PDF/模型其余文件及依赖精确版本/hash：样本manifest、model-register、uv/npm/Cargo lock及license inventory。

## 4. 已测性能与质量边界

真实BERT16页64Chunk，DPR13页55Chunk；未修改公开原PDF。没有中文论文、真实扫描集、人工版面/表格/检索金标，不以合成空白/畸形PDF反例替代科研样本。非空提取仅标text_extracted_unreviewed；SourceAnchor降级page_only/bbox=null/confidence unknown。

批准模型在CPUExecutionProvider、2个intra-op线程、512token上限，query/passage前缀、masked mean+L2，384维。首次64个新向量；重复0；新增DPR55个新向量且复用64个旧内容；再次重复0；DB重开0；119条原向量持久化，备份恢复字节一致，两个索引重建不调用encoder。截断计数保留在结果中，不把截断片段视为完整证据。

同一冻结向量/查询/scope/metric/dimension、3条固定查询（含中文）、每条2次warm-up和5次测量，每后端15个计时；独立NumPy精确距离oracle的ID和距离均匹配（共30次）。组件为**适配器含验证与过滤**，不包含查询Embedding/LLM，不是完整混合检索或纯内核计时。

| Mac N=2组件实验 | P50 ms | P95 ms |
|---|---:|---:|
| sqlite-vec0.1.9 | 0.924 | 1.246 |
| LanceDB0.40.0 | 2.809 | 4.111 |

只说明该次小样本工程结果，不足以判定最终后端/模型、1000篇性能或`混合检索P95≤1s`目标。模型卡上的公开分数不是本系统测量。未测全进程峰值RSS、Windows同机A/B、千篇容量/中文科研召回；不报这些数值。默认安装包未包含候选向量实验依赖/模型资源，G08共同打包仍缺。

## 5. 失败、修复与恢复边界

失败原始命令保留。已修复：TS CSS类型声明；PDF.js6移除isEvalSupported参数，沿用CSP；PDFium页面不支持context manager改用closing；Rust缺图标导致的编译错误；浏览器定位器精确文本未包含子元素，改用实际父节点定位后真实流程通过；测试文件名写错导致pytest退出4，无测试执行，已改正并跑完整42项；lint与logger兼容系统Python3.9的UTC导入问题已修复。后者一次logger启动失败尚未生成日志，明确不当作成功命令。

依赖/权重下载部分官方端点TLS EOF，原失败日志保留；开发包改走公开镜像并锁hash，模型使用固定官方仓库下载文件hash校验。镜像首次信任不等于官方独立签名验证。未通过删除失败测试、降低验收线或改变业务需求获得绿灯。

故障测试覆盖不可变对象发布后实际进程中断、取消/过期租约不能发布、未来schema拒绝、备份篡改/恢复新目录、候选过滤/NaN/维度等反例。ENOSPC、真实磁盘填满、迁移中途故障、所有跨存储并发故障及任意恶意PDF安全尚未完整验证。Mac worker限制CPU/时间/页/文本/输出，未完成OS沙箱/硬内存上限/网络隔离；Windows父进程监测与权限分支尚未执行。

恢复不覆盖旧库；先核对manifest/hash/FK，恢复到新目录，向量从持久raw记录重建。保留未完成staging和原始证据，避免自动删除。取消会立即撤销发布权，计算可能持续至supervisor结束；UI不能承诺立即停止CPU。解析失败/旧ParseRun审计、自动队列重试与完整恢复UI仍需补齐。

## 6. 门禁与待决

| Gate | 当前审查结论（完整门槛） | 尚缺内容 |
|---|---|---|
| G01—G03 | BLOCKED | Windows安装器与无开发依赖/普通账户/中文/空格/8GB和16GB实机；新增Mac干净安装也未测 |
| G04 | BLOCKED，Mac去重/持久局部PASS | 更完整平台/增量规模与故障矩阵 |
| G05—G06 | BLOCKED | 代表性人工金标、表格/符号/扫描/混合/旋转裁切质量与bbox校准；当前仅页级 |
| G07 | BLOCKED，真实2篇增量/恢复局部PASS | 新增10篇/实际规模/平台复用 |
| G08 | BLOCKED，Mac相同条件局部PASS | Windows同一安装产物候选A/B与部署依赖/资源审查 |
| G09 | BLOCKED，适配器exact/filter反例局部PASS | 应用级索引世代/全生命周期对账、P2范围快照与规模试验 |
| G10 | BLOCKED，DB+原件+原向量恢复局部PASS | 全套并发/真实磁盘/Windows/GUI恢复；外部索引不声明同点快照 |
| G11 | BLOCKED，token/Origin/限额/fencing/父进程退出局部PASS | OS隔离与恶意PDF/Windows权限完整矩阵 |
| G12 | BLOCKED / NOT EXECUTED | 100/1000篇等真实语料、分项延迟与峰值内存，未填合成容量 |
| G13 | BLOCKED | inventory/NOTICE草稿已保存，但Windows DLL、实际bundle、全部再分发义务未完成 |
| G14 | BLOCKED | 本轮报告和失败证据已备齐，负责人未验收，不能自动进入P1 |

ADR-001—007仍PROPOSED/OPEN：两候选、PDFium快速路径、页级坐标、回环token、E5均为被测实验路线，没有最终方案签字。ADR-008记录用户增加macOS目标，不改变Tauri/Rust/Python/SQLite核心架构；最低OS、Intel与8GB范围调整未批准。实际协议/迁移与旧草案差异明确记录在`contracts/implementation-v0.1.md`；没有偷偷更改草案或科研要求。

## 7. 下一步及人工批准

1. 另一台16GB Windows电脑运行已准备的构建脚本，保存退出码/安装器SHA/日志，再在无开发依赖普通账户环境按平台用例验收；当前无需重复批准常规开发，但尚无执行通道/Windows原始结果。
2. 准备合法、领域有代表性的PDF与人工标注/复核，先冻结质量接受标准；补8GB、10新增、逐步30—50/100—200/1000篇，按原协议测量。当前没有样本，不擅自批量下载未核验论文或更换模型。
3. 补同包候选试验、OS/资源隔离、原生导入/来源完整E2E、完整故障/许可审查；修复后留证，再由负责人验收P0并决定P1。P0阶段批准尚未具备条件，不把一次确认当全部未测门槛豁免。

本轮交付是有证据边界的P0本地实现和补测包；“全部功能”请求仍有P1—P5未交付内容，不能声称全系统完成。
