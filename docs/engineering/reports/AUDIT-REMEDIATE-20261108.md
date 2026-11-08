# AUDIT-REMEDIATE-20261108：本地整改与工程候选交付记录

- Task ID/阶段：AUDIT-REMEDIATE-20261108，审查整改A–E及候选构建；正式发行NO-GO。
- 日期/执行：2026-11-08，Codex执行；没有人工发行批准人。
- 基线：main/00f8f6bc5b06889269454000f66e289b0c491f08，与报告一致。当前源码是事实来源，没有reset/clean/stash或回退到旧版。
- 分支：codex/audit-remediation-20261108；仅本地任务提交，无push/PR/Release/安装包上传。
- 需求/契约：本次用户整改A–E/发行要求；AGENTS §5、v1.1 §§3/4/6/7/9/10；SOURCE_PRIORITY；新增task-recovery-v0.6/query-budget-v0.7。架构、SQLite和原有来源/模型空间/发布机制保留，无新增架构ADR。
- 环境：macOS26.2 ARM64，16GiB/10逻辑CPU，锁定Python3.12.13与仓库TS/Rust环境。Windows真实机器、非管理员干净账户、8GiB及独立人工科研标注均未具备。
- 用户原有PLANS清理记录、BUILD-CLEANUP文档及未跟踪审查输入完整保留，不混入任务提交；PLANS只单独暂存本任务段落。

## 1. 逐项结论

15项完成本机业务整改验证；06/17/18仍阻塞，不能把全部发行任务标为完成。未发现全局不适用项，没有自行批准延期或豁免。详细根因、函数链、红绿测试、文件和边界见audit/remediation-status.md。

| 问题 | 当前结论/业务变化 |
|---|---|
| 01/02 | 已验证：坏恢复原件按任务隔离，原任务SHA/大小绑定；正常任务继续，全局DB异常不吞掉 |
| 03 | 已验证：claim/业务/fail写入异常都释放工作槽一次，后续任务可受理 |
| 04/07 | 已验证：所有恢复任务有取消路径，queued回答随job终止，旧租约禁止发布；活执行者仍阻止切换副本；浏览器实点retry_wait取消 |
| 05 | 已验证：复用scope_snapshots冻结最多1000版本；job只存ID+SHA，含幂等/篡改/回滚/旧载荷/部分失败及取消测试 |
| 06 | 阻塞：全锁在线审计FAIL，6包/8公告记录含别名及维护公告；精确目标映射不自动构成全锁风险豁免；许可证审查未闭环 |
| 08 | 已验证：单响应同PDF只校验一次，下一请求重验；完成/隐藏对话不继续全历史轮询，篡改仍被识别 |
| 09 | 已验证：有界批量元数据/job查询，更新仅目标版本；项目、DOI和字段优先级保留 |
| 10/11 | 已验证：只处理本次成功导入的可确认staging；故障残留/未知文件保留；备份容量和空闲空间在大复制前拒绝 |
| 12 | 已验证：批读/短事务持久化与关联，推理在事务外；缓存复用、无效批回滚、取消和索引发布隔离不变 |
| 13 | 已验证：术语/引号中的systematic review/all papers不被误当全库覆盖；真正穷尽请求仍不能TopK冒充 |
| 14 | 已验证：Lance只投影ID/距离、256行流式TopK；范围前过滤/缺ID/同分稳定顺序和两种距离保留 |
| 15 | 已验证：probe错误与refresh/onSaved错误分别保留，busy始终复位；成功/失败组合及卸载浏览器无未处理异常 |
| 16 | 已验证：真实锁定tokenizer的511/512/513边界；查询与文档错误分开，当前问题优先、历史预算移除有记录，既有索引不变 |
| 17 | 工具补充已验证/真实质量BLOCKED：Precision未知标签不计分、人工回答相关性、全调用Token/费用记账；0个人工裁定样本，阈值pending |
| 18 | 部分已验证/发行BLOCKED：完整冻结、Rust、包内侧车浏览器和Mac app/DMG有本轮证据；完整模型CI、干净安装GUI、Windows/签名/许可未验收 |

## 2. 实际修改范围与兼容性

- 恢复/任务：ingestion/import_pdf.py、jobs/repository.py、ipc/server.py、ipc/mvp.py、workflows/preparation.py；相应test_audit_recovery/task_contracts/storage_capacity。
- 读写/检索：library/repository.py、retrieval/source_search.py、hybrid.py、research_intent.py、indexing/embeddings.py、incremental.py、vector_adapters/lancedb.py、workflows/history.py、workbench.py、models/local_onnx.py；新增evidence_reads/library_queries/embedding_batches/lance_streaming/query_budget/intent业务测试与两项同机基准工具。
- 前端：MvpAsk.tsx、MvpLibrary.tsx、GenerationConnections.tsx、bridge.ts、probeConnection.ts；TS异步流5例、浏览器新增恢复/故障/停止轮询断言，现有归档/复制/来源/滚动均回归。
- 评估：retrieval/evaluation.py、evaluate_scientific_quality.py、goldset-protocol.md及test_audit_evaluation.py；未修改待审批阈值。
- 发行/工程：build_candidate.py、candidate_preflight/upgrade_failure测试、browser_smoke/chat_management、CI新增TS故障流单元、execplan/台账/发布清单/本报告。
- schema仍21，无历史迁移更改，无真实用户库测试迁移。任务大范围快照复用既有表；旧job载荷兼容。Temporary v20故障升级回滚/备份恢复和旧程序拒开更高schema已测。
- UI变化主要是结束后停止全量证据轮询、恢复任务可取消、准确的查询过长提示和连接测试恢复可操作；没有改写回答正文或把模型自检当科学证明。

## 3. 命令与实际结果

原始记录在docs/engineering/evidence/AUDIT-REMEDIATE-20261108（本机忽略目录），每条含完整argv、平台、时间和退出码。可提交摘要索引audit/remediation-executions-20261108.json；失败日志没有删除。环境变量仅指向已获批的本地E5、tessdata、Docling和合成扫描页；不使用历史API Key。

| 验证 | 实际命令/日志label | 退出/数量/边界 |
|---|---|---|
| 基线Python | python -m pytest -c engine/pyproject.toml -q / baseline-python | 0，398 PASS/0 FAIL/0 SKIP，125.33s |
| 最终包内侧车Python | 同命令，RAGSYSTEM_FROZEN_SIDECAR指向app内引擎 / candidate-python | 0，460 PASS/0 FAIL/0 SKIP，131.33s；比基线多62项 |
| Rust/真实完整冻结 | cargo test --locked --offline --manifest-path apps/desktop/src-tauri/Cargo.toml -- --include-ignored --test-threads=1 / final-rust | 0，10 PASS/0 FAIL/0 ignored，含E5/OCR/Docling、授权/恢复/来源/会话 |
| 静态Rust | cargo clippy --locked --offline --manifest-path apps/desktop/src-tauri/Cargo.toml --all-targets -- -D warnings | 0，PASS |
| TS/Vite | npm --prefix apps/desktop run build -- --emptyOutDir=false / final-typescript、candidate-macos-build | 0，typecheck与build PASS |
| Ruff | python -m ruff check --config engine/pyproject.toml engine/ragsystem tests packaging/build_candidate.py tools/benchmark_audit_reads.py tools/benchmark_audit_vectors.py tools/evaluate_scientific_quality.py | 0，PASS；使用实际CI锁定规则，未修改配置 |
| TS故障单元 | node --experimental-strip-types --test tests/frontend/probeConnection.test.ts / final-probe-unit | 0，5 PASS/0 FAIL/0 SKIP |
| 源码浏览器 | node tools/browser_smoke.cjs，CHAT_MANAGEMENT=1、SOURCE_ENGINE=1 / final-browser-source-transport | 0，53断言PASS，模拟Tauri/本地协议fixture |
| 包内侧车浏览器 | 同脚本，BROWSER_SIDECAR指向app内引擎 / final-browser-bundled | 0，53断言PASS；不是原生WebView/安装认证 |
| 无开发环境变量侧车 | 同脚本 / candidate-bundled-no-dev | 0，53断言PASS；侧车清除PYTHONPATH/PYTHONHOME/VIRTUAL_ENV等、系统PATH、独立cwd；测试控制器仍需开发工具，不能冒称干净OS |
| 完整冻结 | build_sidecar.py含全部四项include标志 / final-freeze | 0，443883520字节，103项源码/锁/入口SHA核对；模型不入包 |
| 本地候选 | build_candidate.py / candidate-macos-build | 0，release模式Mac app+DMG，--no-sign；不安装/发布 |
| 镜像 | hdiutil verify <实际DMG> / candidate-dmg-integrity | 0，CRC VALID；不是发行签名验证 |
| 迁移故障 | pytest test_audit_upgrade_failure +backup_failures/health/import_atomicity / candidate-upgrade-fault | 0，17 PASS；仅临时库 |
| 依赖 | dependency_gate.py --online / baseline-dependencies、final-dependencies | 1，FAIL；648锁组件，6包/8公告记录，锁完整性PASS、许可BLOCKED |
| npm审计 | npm audit --package-lock-only --audit-level=moderate --registry=https://registry.npmjs.org，正常与代理各一次 | 1，HTTP400执行失败；不是0漏洞 |
| 科研离线 | evaluate_scientific_quality.py --gold <空模板> --predictions <空模板> --manifest <任务新建空清单> --thresholds <原pending阈值> / final-scientific-blocked | 2，BLOCKED/0样本；没有生成虚构金标 |
| 远程CI/安装后GUI/Windows | 未执行 | NOT EXECUTED/BLOCKED，未push/触发发布 |

红绿摘要：A正确红7 FAIL/7 PASS→green19 PASS；B任务红6 FAIL→18 PASS/1资源SKIP（最终全量已0 SKIP）；存储5 FAIL→26 PASS；意图4 FAIL/5 PASS→36 PASS；TS5 FAIL→5 PASS；证据2 FAIL→16 PASS；列表1 FAIL→计数1 PASS+元数据20 PASS；Embedding2 FAIL→8 PASS后新增取消例；Lance2 FAIL→12 PASS；Token2 FAIL/5 PASS→首次green49 PASS/1回归FAIL→修正53 PASS；评估2 FAIL→13 PASS/1资源SKIP（最终全量0 SKIP）。

明确保留的实施失误：首轮恢复测试错误导入、一次不存在测试文件(exit4)、新增浏览器初轮定位器多匹配/无界等待条件以及模拟桥缺cancel_job映射，均保留日志并修正。曾误用仓库根Ruff规则而报告55条（含既有/工具规则）；没有据此修改或放宽项目实际配置。最终项目规则检查通过。已完成的回答等待测试没有被后台轮询打断。

## 4. 同环境性能证据与科学边界

仅工程计数/合成向量，未把模型自评或两篇公开论文当金标。源基线从可信固定Git提交加载，与当前实现对同一临时数据比较；不执行论文内容中的指令。E5/OCR/Docling资源复用已有获批目录，付费API调用0、用户论文/数据库/密钥上传0。

| 操作 | 基线→当前 | 口径 |
|---|---|---|
| 同响应PDF验证读取 | 1/5轮3/15次→各1次 | 下一请求/实际打开重新校验，篡改仍拒绝 |
| 50合成版本列表 | 102→5 SELECT | 元数据/项目/DOI回归保持 |
| 1000合成版本列表 | 2002→11 SELECT；P50 9.23→5.15ms，P95 12.02→5.20ms | 5次热OS缓存；不是1000真实PDF |
| 1合成版本列表 | 4→5 SELECT | 不宣称所有小范围查询都减少SQL |
| BERT 786279字节/30轮 | P50 92.63→70.97ms；P95 94.37→71.49ms | 5次热缓存，无清系统缓存，冷物理IO未测 |
| DPR 403775字节/30轮 | P50 83.12→72.94ms；P95 87.38→77.66ms | 同上 |
| 323合成向量首次/复用 | 647→45 / 324→4事务；新编码数323不变、复用重编码0 | 真实公开PDF分块+合成编码器；不是模型推理速度 |
| Lance 5000×384/授权3333/Top10 | Python峰值42.73→1.08MB；进程峰值RSS489.13→366.00MB；单次251.09→32.80ms | 独立进程/同分精确结果；原生扫描和ID集合仍O(N) |

1000 UUID是入队/恢复契约试验，不是1000篇处理完成。没有真实千篇容量验收、冷缓存SLA、人工来源/数值/语义准确率结论。日志read-benchmark-final.json、vector-benchmark.json保留全部样本。

## 5. 本地提交、产物和审查

已落地的功能提交：45f3c50（01–03）、ae72044（04/05/07）、d2e8097（10/11）、f136937（13/15）、0b23d53（08/09）、2f8ae9f（12/14/16/17工具）。46cf179增加候选构建/预检、浏览器故障与迁移失败测试；后续文档提交保存本报告与清单；完整提交表用`git log 00f8f6bc..HEAD`核对。本轮没有合并/推送/改写历史。

核心产品源码已提交至2f8ae9fe26395b94be921ddc997768e2981f08c9；候选基于这份核心源码。此后新增仅工程工具/CI测试/文档，不改变包内引擎/前端/Rust。候选清单逐项保留103源码/锁哈希，构建入口Windows预检随后补强，不谎称Windows包已重新生成或测试。

实际DMG：`.tools/build/AUDIT-REMEDIATE-M2-candidate/target/aarch64-apple-darwin/release/bundle/dmg/RAGSystem_0.1.0_aarch64.dmg`，SHA256 `0e24cb88255d008354cc8695a3ada3c95c124350bba691800ce9de079427092f`。实际app及侧车哈希、依赖锁、资源版本指针、构建配置、验证状态见release/candidate-20261108.json。没有Windows安装包。

仍需人工审查的差异：对象恢复异常边界、事务与取消隔离、请求内SHA缓存、批量SQL/Embedding、Lance流式同分TopK、Token历史预算、新评估记账字段、候选资源/许可与安装配置。没有通过重构替换Embedding/RRF/引用真实性或模型支持性规则。

## 6. 阻塞、恢复入口与下一步

- 06：DiskCache公告无补丁版本，本应用没有启用其磁盘缓存；5项Rust告警在两个目标树无路径，但全锁门禁和实际二进制NOTICE仍待正式处置。不能自行风险接受。依据见dependency-triage-20261108.json及其上游链接。
- 17：需要授权真实语料、独立人工裁定与预先批准阈值。现有工具可运行且真实空输入正确BLOCKED，不能用合成题/模型自评分替代。
- 18/REL-002/003/004/006：Windows11x64/干净Mac账户、非管理员/中文空格/离线/Defender、完整安装主链路、升级卸载、目标运行时许可与发行签名/公证待验证；不调用签名账户或绕过Gatekeeper。
- REL-005：现有目录授权/哈希检查不等于普通用户资源取得流程。需要许可审查后的资源交付方式与首次初始化/中断恢复体验；本轮未静默下载资源或增加复杂下载基础设施。
- 恢复执行入口：audit/remediation-status.md、execplans/AUDIT-REMEDIATE-20261108.md、release/candidate-20261108.md。先核对branch/HEAD/dirty与本报告，继续06目标SBOM/依赖处置、17标注、REL资源与双平台原生矩阵；已有代码无需重做，不重复获取已给的开发授权。

功能测试：PASS（本机边界）。真实Windows安装：BLOCKED/NOT EXECUTED。科研质量：BLOCKED。安装包生成：PASS（Mac工程候选）。安装后桌面可用：NOT EXECUTED。正式发行：NO-GO/未批准。任务未全部完成；准确进度已保存，不承诺后台继续执行。
