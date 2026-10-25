# RAGSystem 2.0 连续开发报告（2026-10-24）

Task ID / 阶段：P0-05B、P1-02–05、P2-01–02、P3/P4本地工作台与OCR/布局表格候选；P5仅本地开发打包。**当前不是全部系统完成或阶段验收签字。** 用户要求连续开发、延期非阻断补测；新模型下载仍按具体授权执行。

范围和实际变更文件：文献/任务/备份恢复、身份归并/批注/生命周期、检索/模型、问答/Research/历史分页、受监管worker、Rust/React与schema5–11，以及任务计划/契约/依赖许可。逐文件SHA和相对P1-01基线的变更见[源码快照](../evidence/continuous-2026-10-24/source-snapshot.json)、[变更CSV](../evidence/continuous-2026-10-24/source-changes.csv)。没有Git初始化/提交/远端、GitHub上传、付费API、用户论文外发或旧项目数据迁移/删除；运行数据只写新测试工作区与本工程。

需求与契约对应章节：v1.1 §§3–8、9–10；[恢复/身份v0.2](../../../contracts/recovery-v0.2.md)、[检索v0.2](../../../contracts/search-v0.2.md)、[工作台v0.2](../../../contracts/workbench-v0.2.md)、[OCRv0.2](../../../contracts/ocr-v0.2.md)、[历史/生命周期v0.2](../../../contracts/history-lifecycle-v0.2.md)、原SourceAnchor/EvidenceSpan草案。ADR-008是用户增加Mac目标，ADR-009是用户允许独立功能继续开发；均不是性能/科研/平台验收通过。

已执行命令、平台、退出码、日志位置：macOS26.2 Apple M4 arm64/16GB，Python3.12.13/Rust1.99.1/Node22.22.1。全部run_logged记录含argv、UTC起止、平台、退出码和stdout，见[命令索引](../evidence/continuous-2026-10-24/commands-index.json)及同目录原始JSON。失败日志/截图保留，没有以成功覆盖失败记录。

功能测试：**PASS，仅本轮实际执行的Mac工程子集**。真实 Windows 安装测试：**BLOCKED / 未执行**。科研质量测试：**BLOCKED，缺人工金标且真实候选已有错误**。OS完整隔离/规模/发行：**NOT EXECUTED/BLOCKED**；[延期表](../deferred-tests.md)保留触发条件。

## 实际完成

1. 多选PDF≤32，每份独立幂等导入/任务/项目关联/失败；SHA去重。多项目、人工元数据CAS、DOI候选提醒；人工归并不同文件版本、项目关联继承、冲突保护撤销。原件、版本、来源ID保留。
2. 未解析PDF可阅读、翻页/跳页/缩放、页级来源跳转；按真实版本/页保存批注和不可覆盖修订，批注不入证据池。≥1600px证据问答/研究提供范围、结果、PDF三栏；窄屏回退抽屉，PDF实绘验证不重叠。坐标未校准，无虚构bbox。
3. 原生目录授权创建备份/全新恢复副本，核对manifest/SHA/SQLite/FK/schema，保留原向量并重建派生索引。先验证新侧车再切换工作区，失败保留旧库；复制的任务租约隔离，取消/受支持重试、独占工作区锁和重启恢复留痕。
4. 中英关键词/完整短语；固定E5候选配置、sqlite-vec/LanceDB新索引世代、持久内容向量增量复用、失败保留旧代、精确向量/RRF、项目/可见性过滤。标签/年份预选版本由SQLite在召回前及慢查询后复核，变化拒绝过时结果。问答按逻辑论文最多3片段、总计最多8片段；多个PDF版本共用论文配额，不能充当全库覆盖。
5. 每轮冻结项目/PDF版本/SHA/论文身份/解析批次；摘录模式明确不生成结论。Qwen草稿选择预编号来源，发布前逐codepoint验证quote/关联/PDF SHA；模型支持、科学可比性和人工状态独立，证据不足拒答，过期来源不继续当当前有效证据。
6. Research先建计划再运行，逐篇逐Chunk检查点、取消/失败续跑、单篇失败继续其他篇；完整/部分/未解析/待OCR/失败/未处理分开计数。一篇逻辑论文只能选择一个PDF版本；冻结后归并导致身份变化则阻止相应旧身份继续处理并警告。
7. 九类研究字段、数值/单位/实验行ID/对象/样本量/指标/划分/条件与可比性人工修订有CAS及before/after审计。每次模型调用前记录指纹，即使失败也保留；每条观察保留抽取模型，恢复换配置与人工编辑不覆盖来源。报告修订不可覆盖，包含覆盖/缺失/人工/来源/可比性和页码/来源ID，Markdown不可信内容转义，无自动跨研究排名。
8. 新GUI历史列表为稳定时间+ID游标，可访问30项之外记录；单轮详情按需读，Research按篇和每20条观察分页，只取对应证据，报告正文另取。字段出现在其他分页时明确提示，不误报未提取。旧近期端点保留兼容。
9. 手工停用/人工撤稿标记及恢复，在同一短事务同步所有版本可见性和不可覆盖审计；新检索/新范围立即排除，重复导入不激活。原件仍可只读核对，恢复只恢复停用前可见版本。停用期间撤销归并被拒绝。旧证据显示当前状态；旧报告body保留，读取/导出另附当前停用、撤稿、解析或身份变化警告。标记由本机用户维护，未经出版方核实。
10. 用户明确批准的OCR候选已落地：tessdata_fast4.1.0实际commit `65727574dfcd264acbb0c3e07860e4e9e9b22185`，固定eng/chi_sim经官方Git blob/大小/SHA校验，完整Apache-2.0 LICENSE保留。项目内tesserocr2.12.0实际加载Tesseract5.5.3/Leptonica1.87.0。原生目录授权→后台隔离probe→显式低文本页OCR重解析；页数/像素/字符/CPU/墙钟有界，100ms取消/失租检查终止确切子进程，迟到结果不能发布。新解析提交后才撤下旧Chunk；OCR引文明确需核对字符/数值/单位，仍page_only。
11. 可关闭的keyword_review/hybrid_review策略复用已批准Qwen，对最多6条、每条500字符作有界相关性复核；每个输入ID必须恰出现一次、0–5整数分数，保留原/新排序、理由、模型指纹。沿用后台可取消问答任务，失败显式留痕。它不是已验证增益的专用Reranker，默认关闭。
12. 新增明确批准的Heron / TableFormer fast与项目内Docling/PyTorch/OpenCV候选。固定文件大小/SHA及小文件Git blob核对，直接官方HF TLS失败，元数据与权重经hf-mirror取得，未声称独立验证镜像元数据。关闭隐式OCR/图片/公式/远程/插件与其他模型，Python socket额外禁止联网；在同一受监管worker框架运行。40页/像素/字符/结构/时间有界，失败保留旧解析和原件。
13. schema11保存有序版面块及原始模型对象、表/单元格UUID、行列范围/跨度/表头、原始结构与实际页文本codepoint范围；逐格精确子串校验后事务发布。跨页文本仅接受完整、不重叠charspan分区；无法映射时保留原对象/缺口并标partial，未知页表格不虚构页号。页级SourceAnchor不变，无未经校准高亮。引用按实际quote偏移关联单元格；表格10行分页、独立CAS人工复核/修订历史、PDF页对照已接入，表格/复核纳入备份；重解析后旧表仍留存但不作为当前来源。
14. 生成worker私有有界管道、超时/崩溃/取消回收、父死/EOF监护、1MiB stderr日志；加载期间也能取消，未发布配置或被替换实例显式关闭。没有新增常驻网络服务、Docker/WSL/独立数据库或复杂Agent架构。

## 实际验证与产物

| 检查与日志标签 | 结果/边界 |
|---|---|
| final-105-python-candidates：显式E5/OCR/Docling/最终冻结路径，pytest | **105 passed，退出0**（50.18秒）。含真实模型/适配器/PDF、迁移/备份恢复、权限/引用/隔离/取消、历史游标/模型指纹、生命周期/并发撤销发布和OCR边界；Fixture只算工程协议 |
| rust-six-candidate-regressions：cargo test -- --include-ignored --test-threads=1 --nocapture | **6 passed，退出0**（独立helper修复后的上一冻结版），含真实冻结侧车鉴权/EOF、两向量候选、OCR和Docling/表格复核经真实Rust HTTP传输、路径/原件保护。默认cargo test会跳过依赖已批准资源的3项 |
| final-native-clippy / final-python-lint / TS-Vite | **PASS，退出0**；按锁配置运行，未格式化受保护validate_kit |
| browser-mutex-matched-final（Docling接入前的历史结果） | **PASS**，真实冻结引擎/PDF/E5/Qwen/OCR配置、标签年份筛选、相关性复核、人工证据、64/64摘录研究/修订/报告导出、36计划历史访问、人工撤稿/恢复及保留原件、备份恢复/切换、1900px三栏/1000px抽屉。**模拟Tauri桥，未测原生对话框或Windows** |
| frozen-ocr-final-candidate | **PASS**，实际冻结包识别本地栅格化BERT第1页；4089字符，MeanTextConf=94，约2.01秒；FTS命中/原PDF哈希/页级anchor/诊断通过。94不是94%准确率，单页时长不是SLA |
| macos-layout-reader-layer-fixed-bundle / native-macos-layer-fixed-final | **PASS**，Mac debug .app构建，真实WebView/Rust启动schema11并退出回收，已知侧车PID无残留；不等于完整原生导入/干净安装 |
| 真实GGUF Research原始试验 | BERT64/64片段、99条模型草稿，约221.39秒；见generation-real-56ea58e1-273f-4be0-b85b-bff22902f715.json。不是正确提取99条事实；曾有错误回答、自审和结构失败，全部保留 |
| 真实相关性复核原始试验 | generation-real-07043d63-433b-48f8-9253-be8b951eb240.json，排序+问答约10.18秒，工程completed，但理由把task-specific/fine-tuning当预训练任务，且各候选同分；**没有提升或科学支持证明** |
| full-browser-activation-readiness-fixed | **PASS，退出0**，最终真实冻结引擎，表格8候选/人工不确定修订/PDF第7页正常打开关闭；原问答/Research/历史/生命周期、备份恢复/切换后表格ID与修订保留。模拟Tauri桥，未测原生文件选择 |
| docling-final-frozen-isolated | **PASS，退出0**，最终冻结版处理两篇真实PDF；8/7表、88/113格，均partial，存在列合并，非科学验收 |
| final-sidecar-docling-rust-transport | **1 passed，退出0**，最终冻结版经实际Rust传输配置/解析/读取表格/独立复核，其他5项有意过滤；6项全量是前述独立记录 |
| 静态validate_kit/源码保护核对 | 命令/结果见最终证据；仅结构/hash审计，不替代应用或科研质量 |

Mac应用：`apps/desktop/src-tauri/target/debug/bundle/macos/RAGSystem.app`，**487,991,875字节/465.39MiB**；入口SHA256 `42d868e0f0526660163088a3d9efa8f57256949c8b55c2c5eb950e35eded55de`，逐文件见[应用清单](../evidence/continuous-2026-10-24/application-manifest.json)。开发包未做发行签名/公证、未对外发布。

最终Sidecar：**443,680,288字节**，SHA256 `bcbafeb1d10c7af0061e3c2d53d60710b2fbe6674a08f19572a9b4898ba801ee`；独立构建`.tools/build/sidecar-20261024T151655782205Z/`。含两向量/ONNX/tokenizer/llama.cpp/tesserocr/Docling/PyTorch候选运行时，**无任何模型权重**。

样本为BERT/DPR两篇CC-BY4.0，29页/119Chunk，另有从BERT原页200dpi灰度转换的测试图像型PDF；原件未改写，转换、页码、原/派生SHA记录齐全。没有私人科研语料、自然扫描中文/表格/科学符号金标或100/1000篇容量结论。

## 许可、失败与修复

- 固定E5与Qwen权重及许可证登记保留。Qwen固定GGUF SHA `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`，1,117,320,736字节；初次官方TLS失败后经hf-mirror重定向官方CDN取得并实校。仅本地候选，不分发权重。
- OCR两权重SHA/官方Git blob/完整LICENSE在docs/legal/ocr-model-register.json及相邻模型目录；tesserocr绑定MIT原文已保留，11个原生二进制hash/链接见ocr-native-inventory-macos.json。Mac轮子为macOS15 arm64标签，其他Mac与Windows不可据此宣称通过。
- dependency-inventory-20261024T150911846052Z.json：96项Python/93npm/458Cargo；精确版本/来源/hash在各锁。完整native NOTICE、Windows DLL、签名/再分发审查仍BLOCKED。
- 引文改写/JSON截断/不支持的callback/过大grammar导致原生异常：保留失败，修为受控编号/紧凑结构、严格再验证、子进程隔离，不放宽引文准入。模型语义问题仍存在。
- 首轮OCR真实链路发现原诊断接口误用quality列，修为quality_status投影，增加真实HTTP/解析回归。试验脚本字段/anchor断言错误按既有契约修正，未修改标准。
- 冻结候选冷载及短keep-alive复用曾造成轮询重置/超时。Rust使用新连接、30秒传输超时及明确ENGINE_TIMEOUT，无写操作自动重放；最终原生候选实测状态请求约5.53/5.02秒。**这是仍存在的冷载阻塞问题，不是性能通过**；向量重操作隔离/性能预算仍需后续验证。
- 浏览器测试切换时连接失败以及额外并发导致503日志均保留。修测试传输为新连接，并与真实Rust Bridge的串行互斥行为一致；**未放大引擎并发上限8、未加写重试或忽略HTTP失败**，最终完整流程通过。原生Rust单独验证，不拿模拟桥替代。

## 未解决问题、差异与下一步

Docling资源已获用户新增明确批准，已下载/安装并完成源码与实际冻结HTTP试验。当前固定Heron revision `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`与TableFormer fast revision `2199320848bb9a8a519d22e4b528185a4f9a6f64`；两大权重171,658,996和145,453,276字节，均与仓库元数据LFS SHA匹配，模型登记保留镜像来源限制。Heron卡Apache-2.0，docling-models卡CDLA-Permissive-2.0/Apache-2.0但无逐文件许可映射，不自动认定TableFormer单文件最终分发许可。真实BERT/DPR分别8/7表候选，两个ParseRun均partial（各9页存在映射错误标记）；列合并/跨页映射缺口已观察到，不能自动作为准确数值矩阵。自动质量路由与单页增强仍未交付，不把功能缺口当作仅测试延期。

精确区域/表格高亮与自动科学比较未验收；大计划/报告生成和完整历史载荷的千篇/内存/性能实测未执行。OCR中文/自然扫描/低置信阈值与生成/相关性质量、真实Windows/8GB/干净Mac/Intel/低版本、OS完整隔离、安全与发行审查继续按延期表保留，不把功能缺口说成仅测试延期。

与方案不同的设计及ADR编号：ADR-008/009如上；主React/Tauri/Python/SQLite架构保持。schema5–11事务迁移前备份；特定scope HTTP端点128KiB、普通请求/握手16KiB，health api_revision=0.2-local，旧合法请求兼容。所有模型/后端/OCR/Docling均未最终选型，所有正式阶段门禁未由Agent签字通过。

下一步及是否需要人工批准：已批准候选和常规本地功能开发无需重复确认；没有新的待答模型授权。后续优先处理质量路由/单页增强和版面/表格映射，保留候选和正式门禁OPEN。Windows/金标等可按用户指令延期，但任何相应兼容/质量/发行声明前必须补验；仍无付费API、外发、发布或旧数据操作授权。

## Docling最终产物与增量回归

- `docling-final-frozen-isolated`：最终Sidecar实际HTTP链路PASS；BERT16页/8表/88格/63个可见Chunk、DPR13页/7表/113格/54个可见Chunk，处理约8.93/7.71秒，均partial。原始结果`docling-frozen-791c920b-d3dd-498b-983f-a94b372f7e65.json`。这是单次已加载候选的工程时长，不含全部冷启动，也不是SLA或科学正确率。
- `frozen-source-consistency.json`：69项引擎/迁移/入口/锁文件SHA与构建清单逐一一致，binary SHA一致。构建前后源码不同会拒绝替换上一个binary；不交付过时冻结包。
- `docling-additional-fault-checks`：6项PASS，含真实BERT/单元格、恢复/审查、取消/页数像素、坏hash、严格HTTP、跨页不虚构、事务中坏映射回滚保留旧anchor（部分为明确标注的工程故障fixture）。v10→11与原设置/升级前快照、固定resource-tracker参数注入拒绝另测，已包含105项全量。
- 首次Docling缺OpenCV已补齐明确extra；实际FK顺序失败修为先写页元素再写结构。失败日志保留。冻结Torch资源跟踪器曾被启动校验拒绝；修为仅识别完整固定stdlib tracker命令并直接调用main(fd)，不使用通用prefix exec，不放宽任意启动参数；真实修复后无该错误。
- 并发冻结模型校验触发120秒超时，旧配置/资料保留，日志`docling-frozen-fixed-helper-regression`为FAIL；最终独立复跑PASS，未提高上限或把失败隐藏。模型冷载/压力性能仍待测。
- 浏览器实际发现详情面板挡住PDF关闭按钮；保留`docling-table-original-page7-before-layer-fix.png`和失败命令。限定修正“文献详情+阅读器”层级，不影响工作台三栏；不使用force click绕过产品问题。最终`full-browser-activation-readiness-fixed`全流程复跑PASS（退出0）：表格页码/正常关闭、人工复核修订、恢复后同表格ID/状态/修订均保留；同时覆盖原有检索/问答/Research/历史/生命周期。模拟桥仍不是原生对话框验收。
- 布局表格完整候选另见[增量契约](../../../contracts/layout-tables-v0.2.md)和[ExecPlan](../execplans/P0-05B-docling-layout-tables.md)。

- 恢复测试曾在切换完成前向旧端口读取资料，保留ECONNREFUSED失败与截图；模拟桥修为与Rust一致的“新引擎就绪后退役旧引擎”，断言等待界面当前工作区标签更新。没有放宽产品身份、重试写请求或忽略传输错误。
- 最终Mac原生启动/退出回收PASS，入口SHA与当前465.39MiB应用一致，确切子进程无残留；未执行系统文件选择、完整原生E2E或Windows安装。

- `final-sidecar-docling-rust-transport`：最终Sidecar实际Rust传输1项PASS（66.60秒，其他5项有意过滤）；与前述6项全量和105项Python分别记录，不把本次1项说成6项重跑。最终原生包使用同一Sidecar SHA。
