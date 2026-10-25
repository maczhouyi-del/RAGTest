# P0 环境版本许可与测试资源登记

检查日期：2026-10-24（Asia/Shanghai）。下方原表是P0-00历史快照；后续开发资源见本节更新。原始记录`evidence/P0-00-2026-10-24/`保留，不改写成当前依赖状态。

后续已确认：本机macOS26.2 arm64、16GB；用户另一台Windows电脑也是16GB，尚无本会话执行通道。Python3.12.13复用已有uv运行时，项目Rust1.99.1、Node22.22.1/npm10.9.4；依赖锁在engine/uv.lock、desktop/package-lock.json及Cargo.lock。实际许可元数据/文本与缺项见`../legal/`，不是再分发批准。

两篇公开PDF已下载并校验，manifest在`tests/fixtures/public/manifest.json`，实际16+13页、64+55Chunk；未成人工金标。用户允许的intfloat/multilingual-e5-small固定revision ONNX/tokenizer已下载SHA验证，本地384维推理已执行；模型不随默认app打包，最终选型OPEN。用户暂无个人PDF；代表性/扫描/旋转/实验表格、基线+10新增和100/1000篇档仍不足。8GB未取消，Windows干净安装/人工科研质量仍BLOCKED。

## P0-00 历史快照

## 当前开发环境

| 资源 | 已确认事实 | 适用边界/下一步 |
|---|---|---|
| 目录 | `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem` 可读写 | 不是名为 RAGSystem2 的目录；不擅自更名 |
| OS/架构 | macOS 26.2 / arm64 | 不能替代 Windows11 x64 |
| Git | 2.50.1；当前目录及父目录不属于 Git 工作树（退出128） | 没有可审计提交/分支历史；未 init、commit、配置 remote |
| Python | 3.9.6，系统 CommandLineTools 解释器 | 仅启动包审查使用，不选作产品运行时 |
| Node / npm | 22.22.1 / 10.9.4 | 本机版本不等于已批准发行依赖 |
| Rust / Cargo | 当前 PATH 未找到 | 未安装；下一轮构建前需具体安装授权/可用环境 |
| PyYAML / jsonschema | PyYAML 可导入；jsonschema 不可导入 | YAML 已解析，JSON Schema 语义检查被跳过；不自动安装 |
| 应用/语料/模型 | 无 apps/engine/packaging/tests 应用目录，无锁文件，无本地 PDF/权重 | 不存在可运行产品或真实 Benchmark |
| Win11 8/16GB | 未提供设备/VM 信息与访问方式 | G01—G03/09 BLOCKED；不访问外部设备、不新建 VM |

仅查询与任务有关的版本/平台/路径，没有枚举凭据或个人其他目录。设备内存/CPU 型号/Defender/WebView2、磁盘空间、干净镜像证明均待 Windows 操作人员填写，不能从本机推断。

## 依赖和模型许可准入表

| 对象 | 已定方向 | 准确版本/哈希/许可证与再分发 | 当前准入 |
|---|---|---|---|
| Tauri / React / Rust | Tauri2 + React + Rust 生命周期与授权 | 待锁定 crate/npm 版本、lock、NOTICE、Windows 工具链 | OPEN，未安装 |
| Python + 打包器 | 独立 Sidecar，无系统 Python 依赖 | Python 版本、PyInstaller/其他方案、DLL、运行时许可证待核 | OPEN，未安装 |
| SQLite WAL / FTS5 | 业务真值与关键词底座 | 产品实际 SQLite build/FTS5/扩展能力待核 | OPEN，未构建 |
| sqlite-vec / LanceDB | 两个本地候选，exact KNN 对比 | 版本、包/wheel 哈希、平台、许可/NOTICE 待核；官方文档版本不等于锁定版本 | OPEN，未安装 |
| PDFium / Python wrapper / PDF.js | 提取与阅读候选 | 具体版本/原生 DLL/字体及第三方许可逐项审查 | OPEN，未安装 |
| Docling/OCR | 条件增强，不默认触发下载 | 代码与 OCR/Layout 权重许可分别核对；下载/联网受控 | OPEN，未安装/下载 |
| Embedding / tokenizer / ONNX | 本地轻量多语言候选方向 | 尚未选具体模型；模型卡、revision、权重/tokenizer SHA、预处理/距离/归一化与授权待填 | OPEN，未下载 |
| Reranker / LLM | 可选后续 | 本轮无模型/API 调用；不提前定供应商 | NOT STARTED |

后续许可清单应包含：对象、版本/revision、官方来源、artifact SHA256、许可证文本与版本、NOTICE、用途、允许范围、再分发/修改/归属义务、传递依赖、审查人/日期、批准状态。当前不凭主项目代码许可批准全部权重或 DLL。

## 可公开复现的真实论文候选清单

本轮只核对公开元数据/许可网页，未下载 PDF、未取实际文件 SHA、未读取或运行解析。以下是“可获取样本清单”，不是已入库 corpus/金标；PDF 具体文件版权/附图例外仍应在实际获取时复核。官方 ACL 页面页脚列明 2016 年起材料使用 CC BY 4.0；保留作者/题名/出处、许可链接及变更说明。不要把论文作为模型权重许可依据。

| 样本 | 官方元数据与 PDF 入口 | 许可依据 | 计划用途/缺失项 |
|---|---|---|---|
| S01：BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding，Devlin 等，2019 | [元数据](https://aclanthology.org/N19-1423/)；[PDF](https://aclanthology.org/N19-1423.pdf) | 同页 ACL 2016+ CC BY4.0 声明；[许可](https://creativecommons.org/licenses/by/4.0/) | 英文数字论文候选；版面/表格逐页确认、文件 SHA、实际页数、金标待填；下载/解析 NOT EXECUTED |
| S02：Dense Passage Retrieval for Open-Domain Question Answering，Karpukhin 等，2020 | [元数据](https://aclanthology.org/2020.emnlp-main.550/)；[PDF](https://aclanthology.org/2020.emnlp-main.550.pdf) | 同页 ACL 2016+ CC BY4.0 声明；[许可](https://creativecommons.org/licenses/by/4.0/) | 检索主题英文论文候选；版面/表格逐页确认、文件 SHA、实际页数、金标待填；下载/解析 NOT EXECUTED |

两个候选不代表材料科学或中文科研分布。仍缺中文、扫描/混合、复杂实验表格、旋转/CropBox、异常页，以及合法的基线+10新增、30–50篇基础、100–200篇模型对比和真实约1000篇目标库。不要把出版页码范围当 PDF 页数，不预填定位框或答案。人工可从上述官方入口获取后，在 `corpus-manifest.template.csv` 派生文件填写实际 SHA 与许可；本轮不自动下载。

## 设备与金标交接待办

用户指定 Windows 构建环境/8GB及16GB干净验收环境、操作人员和访问方式；记录非管理员、中文用户名/空格路径、无系统开发运行依赖、WebView2与Defender。科研负责人明确领域/中英比例、可使用资料、标注人与复核人、可接受页/区域误差及表格绑定质量标准；先批准评测方法和合格线，再跑正式评测。数字目标当前仅沿用 v1.1 建议值，没有自行冻结百分比 KPI。
