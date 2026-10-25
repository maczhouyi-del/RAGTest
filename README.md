# RAGSystem 2.0 — 本地开发预览

本项目依据v1.1方案开发，目标Windows11x64与macOS。当前实测平台为macOS26.2、Apple M4 arm64、16GB；Windows/8GB/干净安装与人工科研金标仍待验收。用户授权连续开发并延期非阻断补测，现已接入P1–P4核心本地工作流，**完整系统和P0–P4正式验收尚未全部完成**。2026-10-25用户新增明确授权，将源码保存在指定GitHub仓库`maczhouyi-del/RAGTest`；不上传论文、模型权重、数据库、运行日志或凭据，不调用付费云API，不触及旧RAGSystem数据。

GitHub仅提供源码。克隆后需在目标平台准备开发工具并按下文构建，不包含可直接安装的发行包。公开测试PDF未入库，来源、文件名和SHA见`tests/fixtures/public/manifest.json`；运行相关集成测试前需自行取得对应文件并校验。模型需另行取得并核对授权、固定revision和哈希。历史报告引用的本机evidence、依赖实测清单及应用产物均未上传，因此相应本地证据链接在克隆副本中不可用。

当前MVP首页为**问答**，只有问答、文献、设置三个一级入口。导入后自动保存/解析；配置E5后使用FTS5 BM25 + sqlite-vec向量的RRF混合检索。Research和复杂审查代码保留，暂不作为一级入口。实现审查、阶段证据与缺口见[本轮报告](docs/engineering/reports/MVP-2026-10-25.md)和[增量契约](contracts/mvp-v0.3.md)。

历史完整工作台模块（部分入口已在MVP隐藏）：

- 文献：多选PDF导入、SHA原件去重、多项目关联、人工元数据与CAS冲突检查、DOI候选提醒；人工确认不同文件版本归并、项目关联继承、带冲突保护的撤销；手工停用/撤稿标记与恢复、不可覆盖审计，旧证据/报告显示失效来源。
- 阅读：无需解析即可阅读、翻页/跳页/缩放；按版本和真实页码保存批注及全部修订。解析诊断显示空白/失败/待OCR页；显式配置已批准OCR资源后，可在隔离worker中重解析低文本页，保留页质量和候选指纹。来源暂用可信页级定位，没有虚构高亮框。
- 表格：显式配置Heron / TableFormer fast后增强解析，保存结构/表头/行列跨度与单元格到页文本映射；表格分页核对、独立人工修订、PDF页对照、问答/Research引用关联；词级输入改善样本列合并，仍需人工核对。
- 按页解析：可选择只更新指定页，保留未改动页的引用与审查；可关闭的质量信号路由会按页尝试已配置OCR/布局候选，记录失败、拒绝与回退原因。阈值未经科研金标校准。
- 检索：中英关键词/完整短语；用户选择固定E5本地候选后建立sqlite-vec或LanceDB候选索引，支持精确语义和RRF混合检索。向量持久复用，新增内容增量编码；构建失败保留旧代。
- 问答：冻结范围、原文摘录模式、可选本地生成草稿、精确引用核验、独立模型支持/可比性/人工状态、拒答与原文跳转。历史对话和阅读笔记不充当科学证据。可关闭的本地相关性复核排序使用同一获批Qwen候选，保留排序/理由/模型指纹，不代表科学支持。
- Research：冻结论文版本/解析批次，逐篇逐Chunk处理，保存每篇覆盖与检查点，取消/失败后继续；单篇失败继续其他文献；九类字段候选、数值/单位/实验条件人工修订留痕、证据复核、报告版本和创建新Markdown文件导出。历史游标可访问近期30项之外的记录；选定计划按篇及每20条观察分页，报告正文按需加载，逐条模型指纹不因恢复/人工编辑覆盖。
- 恢复：持久任务、重试/取消；原生目录授权创建备份/全新恢复副本、清单和SHA/SQLite校验、明确切换工作区。原件和SQLite原向量纳入备份，派生索引可复建；不覆盖旧资料。

当前限制是**真实缺口**：词级输入修正了样本中的整行合并问题，但两篇仍有跨页映射缺口，只能作待审候选。自动质量路由与单页增强已接入；路由阈值未通过科研金标校准。精确区域高亮未校准，继续可信页级降级。当前可选相关性复核排序不是经过增益验证的专用Reranker。新版GUI已分页，大计划/报告生成的完整规模与内存仍待测。候选Qwen在真实试验中出现无关陈述、错误自审和抽取错误，不能用于未经人工核对的科研结论。正式容量、时延、科研质量及安装分发结论均未通过。详见[本轮报告](docs/engineering/reports/continuous-2026-10-25.md)和[延期与功能缺口](docs/engineering/deferred-tests.md)。

## 启动本机预览

Mac开发预览产物：`apps/desktop/src-tauri/target/debug/bundle/macos/RAGSystem.app`。包含候选推理运行时、**不包含模型权重**；无发行签名/公证或干净安装结论。双击打开即可；普通浏览器预览不能访问本地文件。资料目录由系统local_data_dir下的`RAGSystem/`派生，debug可用绝对`RAGSYSTEM_DEV_DATA_ROOT`指定新测试目录。不要指向旧项目数据。

首次使用：导入PDF→自动保存/解析→设置中选择E5目录建立本地索引→问答中选择原文摘录或本地Qwen→输入问题→点击引用打开对应PDF页及证据摘录。原件SHA去重，不虚构区域高亮。未配置E5时可先用关键词检索；退出时未衔接的准备步骤可在文献页“准备问答 / 更新索引”恢复。

设置支持显式添加OpenAI兼容API/本地服务或可选Magpie，先“获取模型列表”再选模型。API密钥仅本次引擎会话内存，重启后需重输；API或网关每次生成都需勾选允许发送问题与检索片段，不自动转云。Magpie须用户自行启动，网关可能转发云；不读取订阅凭据。更换生成模型不会重新Embedding。接口须支持Chat Completions的JSON对象响应。

旧库如因长Chunk无法建立新索引，可在文献详情展开“高级解析与表格核对”，取消“只更新指定页”，选择“仅提取原生文本”重新解析，再更新索引；旧引用可能因解析变化失效。旧索引若缺少完整性清单需要更新；新增溢出拒绝策略纳入E5指纹，旧指纹空间保留，新规则首次构建可能重算，后续复用。设置页提供备份/全新恢复副本及本地资料目录显示，高级设置保留其他候选后端/解析/资料生命周期。

已授权并下载的本地候选仅在本项目`.tools/models/`：

- Embedding目录：`intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3`。设置页选择候选后端并选择此目录构建；未做最终后端/模型选择。
- 生成目录：`qwen2.5-1.5b-instruct-gguf-91cad51170dc346986eccefdc2dd33a9da36ead9`。设置页选择并校验GGUF目录；仅本地CPU候选试验，不自动下载、不上传论文、不访问云模型。受监管子进程通过私有管道通信，超时/崩溃/取消保留任务与诊断。

- OCR目录：`tessdata-fast-65727574dfcd264acbb0c3e07860e4e9e9b22185`。设置页选择包含eng/chi_sim的目录校验，然后在文献详情显式“使用离线OCR重解析低文本页”。OCR文本须对照原图，语言权重不随app打包。

- 布局/表格目录：`docling-heron-tableformer-fast-candidates`。选择这个共同根目录校验，再在文献详情运行增强解析；单次增强最多40页，可指定页。预处理指纹改变后需在设置重新校验旧配置。

原始资源许可、revision与SHA在`docs/legal/`。其他模型须另行获得具体下载授权。

## 本地构建与验证

开发机使用已锁定Python3.12.13、Rust1.99.1、Node22.22.1及npm锁；Python依赖用uv，当前Mac工具链在项目`.tools/`，不改shell配置。无需Docker/WSL或独立数据库。先读`AGENTS.md`、`PLANS.md`和相关ExecPlan。

```sh
uv sync --frozen --all-extras --project engine
npm --prefix apps/desktop install --ignore-scripts --no-audit --no-fund
engine/.venv/bin/python packaging/build_sidecar.py --include-vector-lab --include-generation-lab --include-ocr-lab --include-docling-lab
export CARGO_HOME="$PWD/.tools/cargo"
export RUSTUP_HOME="$PWD/.tools/rustup"
export PATH="$CARGO_HOME/bin:$PATH"
npm --prefix apps/desktop run tauri -- dev
```

`--include-vector-lab`包含两候选后端和本地Embedding运行时，`--include-generation-lab`包含本地生成运行时，`--include-docling-lab`包含可选Docling/PyTorch布局与表格运行时；`--include-ocr-lab`包含离线OCR运行时；权重始终单独管理。省略标志会构建不含对应候选能力的最小Sidecar。`sh packaging/build-macos.sh`构建本地debug app；Windows须在目标电脑执行`pwsh -File packaging/build-windows.ps1`，不能复用Mac的venv/node_modules/target。Windows本地构建和独立干净安装是两类验收。

```sh
RAGSYSTEM_MODEL_DIR="$PWD/.tools/models/intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3" \
RAGSYSTEM_OCR_MODEL_DIR="$PWD/.tools/models/tessdata-fast-65727574dfcd264acbb0c3e07860e4e9e9b22185" \
RAGSYSTEM_DOCLING_MODEL_DIR="$PWD/.tools/models/docling-heron-tableformer-fast-candidates" \
RAGSYSTEM_FROZEN_SIDECAR="$PWD/apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin" \
engine/.venv/bin/python -m pytest -c engine/pyproject.toml -q
cargo test --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
```

当前源码与冻结版本的回归记录见本轮报告，TS/Vite构建通过；真实GGUF另有原始试验日志，工程处理完成不能当科研质量合格。浏览器端到端使用真实冻结引擎和模拟Tauri桥；原生WebView/Rust启动回收另测，不能代替真实原生对话框/Windows安装。详细最新结果见报告。

SQLite schema12；每次本工程旧schema升级前自动保留OnlineBackup，事务失败回滚，旧程序拒绝高版本。跨工作区恢复不覆盖原库；本工程迁移机制不授权访问旧RAGSystem库。

## 文档

`specs/`保留原v1.1 DOCX、提取文本和来源优先序；`contracts/`保存原草案与已实现子契约；`docs/engineering/execplans/`、`reports/`及本机保留的`evidence/`记录任务、命令、结果及未通过门禁；`docs/legal/`和`THIRD_PARTY_NOTICES.md`是许可清单草案，完整二进制再分发审查仍待做。原始MANIFEST与历史报告保留，早期无Git记录的变更用本地source-snapshot审计；后续指定仓库源码同步见GH-01计划，历史报告描述的是各自执行时的状态。

OCR完整候选能力当前只在本机macOS26.2 arm64实测；tesserocr轮子平台标签macOS15 arm64，不能推断旧Mac/Intel支持。真实Rust传输回归显式包含三个候选试验后为6项通过（默认cargo test会跳过依赖模型的3项）；Windows仍未执行。最终可复现命令与产物hash统一见本轮报告。
