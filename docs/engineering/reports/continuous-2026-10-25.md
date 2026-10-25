# RAGSystem 2.0 连续开发报告（2026-10-25）

Task ID / 阶段：P0-05C，兼及P2索引内容身份、P3/P4冻结范围；依据用户持续开发授权及ADR-009。**这是本地功能增量，不是完整系统完成或正式门禁通过。**

范围和实际变更文件：`engine/ragsystem/parsing/`新增词级适配/质量路由/发布模块，调整Docling/worker/Parser/表格；schema12迁移与Database、Jobs/Backups恢复、Library诊断、Workbench范围检查、IPC；Rust固定命令与传输测试、React详情/桥；集成测试、真实试验/浏览器工具、契约/计划/报告。逐文件SHA及相对上一轮的变更见[源码快照](../evidence/continuous-2026-10-25/source-snapshot.json)、[变更CSV](../evidence/continuous-2026-10-25/source-changes.csv)。旧迁移1–11、原始设计/AGENTS、npm/Cargo/uv锁及Python依赖定义须保持不变。

需求与契约对应章节：v1.1 §§3.2–3.5、4.1–4.2、5.3–5.4、6.2、7、9；[增量契约v0.3](../../../contracts/quality-routing-pages-v0.3.md)、[布局表格v0.2](../../../contracts/layout-tables-v0.2.md)、[ExecPlan](../execplans/P0-05C-quality-routing-pages.md)。ADR-008/009分别保留Mac目标和延期测试的开发顺序例外；无主技术架构变更、模型最终选型或验收标准变更。

已执行命令、平台、退出码、日志位置：macOS26.2 / Apple M4 arm64 / 16GB，Python3.12.13、Rust1.99.1、Node22.22.1。`run_logged.py`记录完整argv、UTC起止、退出码、平台与输出，见[命令索引](../evidence/continuous-2026-10-25/commands-index.json)。每次新冻结保留独立构建目录；失败日志保留。未使用Git/GitHub/远端、付费API或上传文献/源码，没有操作旧项目数据或批量删除。

功能测试：**PASS，仅已执行的Mac工程子集，最终命令分别记录于下表**。真实 Windows 安装测试：**BLOCKED / 未执行**。科研质量测试：**BLOCKED，缺人工金标**。8GB/干净Mac/准确区域高亮/完整OS沙箱/规模性能/发行审查：**NOT EXECUTED / BLOCKED**，见[延期表](../deferred-tests.md)。

## 实际成果

1. 增加本项目词级PDFium适配，向固定TableFormer提供真实glyph-derived word cells，保留原有行文本，不修改第三方安装源码/权重。预处理版本进入指纹，旧Docling配置需要重新校验。公开BERT第7页三张表从2/2/2列改善为5/5/3列；仅为相同样本/权重对照，不报告整体准确率。
2. 自动模式显式可选。先探测原生文本，再按页尝试已配置OCR或布局候选；记录信号、理由、资源不足、运行失败、拒绝采用和回退。低OCR置信度/Docling文本明显减少/空输出不静默采用；取消/失租终止而非降级吞错。阈值未经金标校准，接受结果仍为待审候选。
3. API可选择1–40个不重复原PDF页码；GUI可选择指定单页，提供原生文本/OCR/布局/自动四条路径。单页需要已有基础解析；不连续页Docling范围保持原始页号。每次真实worker尝试保留完整有界输出及状态审计。
4. schema12保存当前页和表格发布指针、revision及未定位对象计数。只撤回受影响页Chunk，其他页/单元格ID/人工复核保持；改变页相交或归属未知的旧表格退出当前发布，历史对象与审查不删除。表格/单元格预算对组合发布同样生效；偏移、预算、并发失败全部回滚。
5. 队列冻结解析配置和发布revision，重试不能悄悄覆盖新解析；同幂等键模式/页集合不符拒绝。空页也有发布指针，参与问答/Research冻结范围；提交结果再次检查当前ParseRun集合，防止处理期间页更新后发布旧范围结论。
6. 全局未定位对象不能可靠归属某页，选择性更新保守保留缺口至全篇重解析。整体partial依据所有当前页及缺口计算。恢复副本与独占工作区重启将运行中尝试/ParseRun标为失败，保留此前发布、原件和审查。

## 测试证据与产物

之前中间版本和失败记录继续保留，不能充当最终版本验收。

| 最终版本命令标签 | 结果与边界 |
|---|---|
| source-final-scope-regression | 127 PASS / 1 SKIP，退出0，53.81秒；全部批准候选实际参与，未传二进制路径的生命周期项单独补测 |
| final-frozen-lifecycle | 3 PASS，退出0，19.72秒；最终二进制鉴权/握手/退出，补足上项冻结用例 |
| scope-publication-race | 36 PASS，退出0，7.45秒；含提交前范围变化拒绝与问答/Research恢复 |
| rust-clippy、desktop-build、macos-final-app、macos-coverage-warning-final | 退出0；最终.app含第二次冻结及覆盖提示修正，无发行签名/公证结论 |
| final-native-coverage-fixed | PASS，退出0；最终真实WebView/Rust启动schema12，确切测试侧车PID 43581/43611均回收；未测原生文件选择/干净安装。此前final-native-macos是提示修正前的独立记录 |
| rust-final-six-candidates | 6 PASS / 0忽略，退出0，运行153.66秒；真实最终侧车经Rust校验向量候选/OCR/布局、单页自动路由、复核保持、鉴权与EOF。默认cargo test会忽略3项依赖批准资源的试验，本次显式执行 |
| final-browser-quality-pages | PASS，退出0；最终侧车+提示修正前UI的全流程，指定第6页增强、第8页自动路由、未改动第7页表格复核及备份恢复保持；模拟Tauri桥，非完整原生对话框/Windows验收 |
| final-browser-coverage-fixed | PASS，退出0；最终UI与最终侧车重跑全流程，额外核对真实partial布局错误页数可见，单页增强/自动路由、原问答/Research/历史/生命周期及恢复后同表格ID/复核修订保持。截图与JSON独立保存在browser-coverage-fixed；仍为模拟Tauri桥 |
| frozen-source-consistency / application-manifest | PASS；74项构建输入SHA、侧车SHA及.app内侧车一致，模型文件未随包分发 |

- `publication-tests`初次：15 PASS / 1 FAIL，失败为迁移测试夹具的无列名INSERT字段顺序错误，已改为显式字段；`publication-tests-fixed`16 PASS。
- `source-regression-publications`：103 PASS / 1 FAIL / 1 SKIP，旧取消测试假设第二次lease调用即进入worker，新增审计事务打破假设。改为真实worker已创建后的check回调取消，仍要求LEASE_LOST、子进程终止及旧来源保持；未放宽产品检查。
- `publication-words-and-budget`：21 PASS；覆盖真实原生PDF、页集合/幂等、发布竞争回滚、旧引用/未改动ID、空页、恢复/升级快照、无资源/失败/拒绝/失租、累计结构预算及严格HTTP。故障输出明确为合成夹具，不作为真实模型或科研金标。
- `scope-publication-race`：36 PASS，新增“检索后仅未命中页变化，提交仍拒绝SCOPE_STALE”及相关问答/Research恢复回归。
- `real-source-routing-pages`：真实源码HTTP→受监管worker，BERT/DPR分别8/7表，单次已配置转换约10.34/9.42秒；不连续6/8页增强、自动路由两次实际采用布局候选、未更新第7页复核与ID保持。
- `real-frozen-routing-pages`：第一份schema12冻结包，相同两篇8/7表，约10.39/9.55秒；选择页、自动路由与未改动复核一致。这一包随后只因补充工作台提交范围检查而重建；最终版本单独验证，不混报SHA。
- `full-regression-final`：第一份schema12冻结包，127 PASS，包含全部显式批准候选与冻结生命周期。新增工作台检查后另行复测，见最终记录。
- TS/Vite、Ruff、Rust clippy、Mac开发.app构建均有退出0记录。静态kit首次系统Python缺jsonschema只检查文件/语法；随后用项目venv重跑含schema验证，无警告。静态检查不代替应用测试。

样本是许可登记中的BERT/DPR两篇公开论文，共29页；没有私人科研语料或人工科研金标。Docling源码全篇输出为BERT8表342格、DPR7表301格，两篇均partial；完整单元格和原始对象见本轮`docling-source-*.json`。另有从许可BERT页面栅格化的工程OCR图像测试，不能替代自然中文扫描质量测试。每格偏移仍逐一核对精确子串，公共定位仍page_only、bbox_norm=null。

## 问题、限制及后续

真实试验仍有跨页/未定位对象，不能把表格候选数量或列数改善当作科学准确率；词边界是预处理启发式。路由仅靠文本/几何信号，可能过度选择双栏论文页或漏掉复杂表格；85%字符覆盖不能证明内容忠实。置信阈值/中文/科学符号/裁切旋转/低质量扫描需独立金标。配置与尝试状态明确可见，不自动更换模型。

冻结模型冷载仍较慢：本轮第一冻结包配置Docling约98.66秒，随后单篇约10秒；不是P95/SLA。打包时未选的远程服务/代码chunker/ONNX量化可选模块有缺依赖警告；没有为未启用功能擅自新增依赖，实际固定候选链路单独验证。硬内存限额和完整OS沙箱仍没有通过。

完整尝试JSON会增加本地磁盘占用，保留策略及大规模诊断/恢复性能尚未验收；本轮没有自动清理历史。Ruff统一了7份已有测试的格式，未删除测试/失败日志或放宽标准。首次自动真实试验的变量覆盖错误已修正，失败尝试与worker stderr保留在本工程测试目录。

截图复核发现旧UI只按待OCR列表计数，Docling已有页错误仍可能显示“0页需要检查”；底层partial与错误未丢失。修为按全部解析错误/质量警告统计并列出待核对页；新增真实浏览器断言，避免掩盖覆盖缺口。提示修正前的成功截图/JSON仍保留，最终截图独立存入`browser-coverage-fixed/`。

最终Sidecar：443,706,256字节，SHA256 `4661a02c598cbbfe81ba833b3f63bcb6c0c88c23000f001b7413058de3b7bdcf`，构建目录`.tools/build/sidecar-20261025T022507477782Z/`。Mac开发.app：489,062,339字节（约466.41MiB），入口SHA256 `73208ea53efcf00bc756ce97d92b98c66bff6426a761e6a8c6be0036d37a918e`，逐文件清单见[应用清单](../evidence/continuous-2026-10-25/application-manifest.json)。包含原批准候选运行时，不含权重；没有新增依赖或修改锁文件。

相对上一轮最终源码快照：30项修改、10项新增、0项移除；23项受保护原始设计/指令/旧迁移/锁文件及依赖定义保持原SHA。完整目录结构、变更文件和实际命令以同目录快照/CSV/命令索引为准。该审计不等同于正式平台或科研验收。

下一步及是否需要人工批准：已授权本地功能继续按依赖推进，不需要重复批准当前候选或常规操作；优先补齐版面映射/准确定位与可观测的失败恢复。正式Windows/科研质量/发行结论之前必须补齐对应门禁。新增模型、付费API、外发、发布及旧项目数据操作不在自动授权范围。P0–P4保持IN PROGRESS，P5不发布。
