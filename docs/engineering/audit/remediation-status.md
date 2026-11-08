# RAGTest整改台账（2026-11-08）

基线00f8f6bc；独立分支codex/audit-remediation-20261108。状态：待核查、已确认、已修复待验证、已验证、不适用、阻塞。既有清理改动与输入材料不混入任务提交。

逐项结论以当前源码与本轮执行为准；下列初始证据均是审查输入，不能当作本轮运行验证。原始日志位于本机忽略evidence/AUDIT-REMEDIATE-20261108。

## RAG-AUD-01 单个待恢复原件异常可以阻断整个引擎启动

- 状态：已验证（本机源码集成/真实侧车子进程；新冻结/目标平台待最终候选复测）。
- 适用性：当前基线仍适用；属于发行阻断，已完成本机修复。
- 审查定位：`engine/ragsystem/ipc/server.py`, `engine/ragsystem/ingestion/import_pdf.py`
- 审查根因：lifespan 在 yield 前直接调用 importer.recover_published_imports()。恢复循环对每条记录只有 finally 释放 Grants，没有隔离该记录的授权、读取或恢复异常。
- 修复与业务测试：在临时工作区构造“已发布但未提交”的导入，破坏其中一份原件，保留另一份正常文献；重启应可读取正常文献，坏任务出现准确错误，且不得删除原件或自动把损坏内容当作成功。
- 本轮命令：run_logged A-red-corrected：7 FAIL/7 PASS；A-green：19 PASS；A-integration：25 PASS/1 SKIP。首轮A-red中的9个导入错误是测试实现问题，已修正并保留日志。
- 业务断言：坏头/有效PDF替换的启动与手动恢复被隔离，正常对象完成；共同run重核哈希；真实源码侧车启动可读正常文献；DB错误仍传播。配置claim/执行/fail写入故障后下一任务受理，失效租约不继续发布。
- 跳过：集成命令未设置新冻结侧车，冻结专项未执行；不借基线旧二进制覆盖新源码验证。
- 修改：ingestion/import_pdf.py、jobs/repository.py、ipc/server.py、tests/integration/test_audit_recovery.py；本地提交45f3c50。
- 边界：持久DB故障仍会阻断服务/状态写入；fail写入失败时保留租约与attempt，恢复后按既有过期机制处理。未吞掉全局DB错误。

## RAG-AUD-02 恢复导入没有把重新读取的文件哈希绑定到原任务预期哈希

- 状态：已验证（本机源码集成/真实侧车子进程；新冻结/目标平台待最终候选复测）。
- 适用性：当前基线仍适用；属于发行阻断，已完成本机修复。
- 审查定位：`engine/ragsystem/ingestion/import_pdf.py`, `engine/ragsystem/ingestion/import_pdf.py`
- 审查根因：recover_published_imports/resume 以 payload 中的 digest 找到 papers/<digest>.pdf，再用 Grants.issue 计算当前文件哈希；随后 run 使用 grant.sha256 发布和入库，没有先比较 grant.sha256 与原任务 payload.sha256。
- 修复与业务测试：在原件发布后注入崩溃，将 A 路径内容替换为有效 PDF B，分别调用启动恢复和手动 resume；不得产生 B 的文档版本，不得将 A 任务标记 completed。
- 本轮命令：run_logged A-red-corrected：7 FAIL/7 PASS；A-green：19 PASS；A-integration：25 PASS/1 SKIP。首轮A-red中的9个导入错误是测试实现问题，已修正并保留日志。
- 业务断言：坏头/有效PDF替换的启动与手动恢复被隔离，正常对象完成；共同run重核哈希；真实源码侧车启动可读正常文献；DB错误仍传播。配置claim/执行/fail写入故障后下一任务受理，失效租约不继续发布。
- 跳过：集成命令未设置新冻结侧车，冻结专项未执行；不借基线旧二进制覆盖新源码验证。
- 修改：ingestion/import_pdf.py、jobs/repository.py、ipc/server.py、tests/integration/test_audit_recovery.py；本地提交45f3c50。
- 边界：持久DB故障仍会阻断服务/状态写入；fail写入失败时保留租约与attempt，恢复后按既有过期机制处理。未吞掉全局DB错误。

## RAG-AUD-03 模型配置任务领取失败时泄漏唯一重型工作槽

- 状态：已验证（本机源码集成/真实侧车子进程；新冻结/目标平台待最终候选复测）。
- 适用性：当前基线仍适用；属于发行阻断，已完成本机修复。
- 审查定位：`engine/ragsystem/ipc/server.py`
- 审查根因：run_docling_configuration、run_ocr_configuration、run_generator 都在 try/finally 之前调用 jobs.claim(...)；slot.release() 位于之后的 finally。领取任务发生异常时不会进入该 finally。
- 修复与业务测试：分别在 claim、业务执行、jobs.fail 中注入异常，验证槽位只释放一次，下一项重任务能受理，原任务保留可诊断终态。
- 本轮命令：run_logged A-red-corrected：7 FAIL/7 PASS；A-green：19 PASS；A-integration：25 PASS/1 SKIP。首轮A-red中的9个导入错误是测试实现问题，已修正并保留日志。
- 业务断言：坏头/有效PDF替换的启动与手动恢复被隔离，正常对象完成；共同run重核哈希；真实源码侧车启动可读正常文献；DB错误仍传播。配置claim/执行/fail写入故障后下一任务受理，失效租约不继续发布。
- 跳过：集成命令未设置新冻结侧车，冻结专项未执行；不借基线旧二进制覆盖新源码验证。
- 修改：ingestion/import_pdf.py、jobs/repository.py、ipc/server.py、tests/integration/test_audit_recovery.py；本地提交45f3c50。
- 边界：持久DB故障仍会阻断服务/状态写入；fail写入失败时保留租约与attempt，恢复后按既有过期机制处理。未吞掉全局DB错误。

## RAG-AUD-04 重启后的 retry_wait 任务缺少可达终结路径，并阻止切换恢复副本

- 状态：已验证（后端专项）；UI按钮路径已改，浏览器回归待最终候选。
- 适用性：已确认；基线没有修复。
- 审查定位：`engine/ragsystem/jobs/repository.py`, `apps/desktop/src/components/MvpLibrary.tsx`, `engine/ragsystem/storage/backup_service.py`
- 审查根因：recover_owned_workspace 将部分 running/queued 任务改为 retry_wait。MVP 队列只允许取消 queued/running，重试仅覆盖 import/parse_page/metadata_extract。restored_path 则将任意 queued/running/retry_wait 视为阻止工作区切换的条件。
- 修复与业务测试：对 import/parse/index/prepare/answer/config/backup 分别在 queued 和 running 时重启；每种任务都必须有可达的继续或终止操作，终结后恢复副本可激活。
- 本轮测试：B-red 6 FAIL；B-green 18 PASS/1 SKIP（未提供E5资源变量）；B-recovery-matrix 9 PASS/0 FAIL/0 SKIP。
- 断言：1000范围快照/小载荷、重读/幂等冲突/事务回滚/旧载荷兼容/篡改检测；claim屏障前取消回答不残留queued；所有任务类型queued/running重启后可取消，旧租约不可发布，恢复副本可激活；实际执行者未退出仍拒绝切换。
- 修改：workflows/preparation.py、ipc/mvp.py、ipc/server.py、jobs/repository.py、MvpLibrary.tsx、bridge.ts、test_audit_task_contracts.py、contracts/task-recovery-v0.6.md；本地提交ae72044。
- 验证边界：1000版本为合成入队/范围契约，不是1000篇PDF解析吞吐；不移除工作槽保护。复用现有scope_snapshots，无schema变更。

## RAG-AUD-05 准备接口声明支持 1000 个版本，内部任务在 419 个 UUID 时即超限

- 状态：已验证（本机源码集成）。
- 适用性：已确认；基线没有修复。
- 审查定位：`engine/ragsystem/ipc/mvp.py`, `engine/ragsystem/ipc/mvp.py`, `engine/ragsystem/jobs/repository.py`, `engine/ragsystem/ipc/server.py`, `apps/desktop/src/components/MvpLibrary.tsx`
- 审查根因：PrepareRequest.version_ids 上限 1000；prepare_documents 将完整 versions 列表写入 job payload；Jobs.enqueue 的紧凑 UTF-8 JSON 上限 16384 字节。该 endpoint 的 HTTP 上限是 128 KiB，因此不是外层 16 KiB 请求限制先触发。
- 修复与业务测试：在临时库测试 1/418/419/1000 个不同有效版本，覆盖取消、重启、部分失败和幂等重提；明确区分接口接收、任务入队与处理完成。
- 本轮测试：B-red 6 FAIL；B-green 18 PASS/1 SKIP（未提供E5资源变量）；B-recovery-matrix 9 PASS/0 FAIL/0 SKIP。
- 断言：1000范围快照/小载荷、重读/幂等冲突/事务回滚/旧载荷兼容/篡改检测；claim屏障前取消回答不残留queued；所有任务类型queued/running重启后可取消，旧租约不可发布，恢复副本可激活；实际执行者未退出仍拒绝切换。
- 修改：workflows/preparation.py、ipc/mvp.py、ipc/server.py、jobs/repository.py、MvpLibrary.tsx、bridge.ts、test_audit_task_contracts.py、contracts/task-recovery-v0.6.md；本地提交ae72044。
- 验证边界：1000版本为合成入队/范围契约，不是1000篇PDF解析吞吐；不移除工作槽保护。复用现有scope_snapshots，无schema变更。

## RAG-AUD-06 当前提交的依赖审计门禁失败，尚未完成发布风险处置

- 状态：已确认；发行阻断未解决。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`.github/workflows/ci.yml`
- 审查根因：Actions run 42369976421：Windows 与 macOS 的 source job 成功，但 lock-audit job 128395893056 失败，整个工作流结论为 failure。读取到的日志报告 lock_integrity PASS、vulnerability_audit FAIL、license_review BLOCKED，存在 diskcache、glib 等公告命中。
- 修复与业务测试：同一提交的审计、源码测试和实际目标包 SBOM/许可清单一致；所有告警均有修复或审查结论。这里没有声称公告已具备可利用 PoC。
- 当前调用链/证据：tools/dependency_gate.py → lock清单648组件 → OSV在线坐标审计。baseline-dependencies exit1，6依赖8公告记录，锁完整性PASS、许可映射BLOCKED。macOS cargo tree --target aarch64-apple-darwin -i glib exit0无依赖路径；Windows离线映射缺jiff-tzdb而exit101，已尝试锁定在线补齐。单个平台无路径不构成全锁豁免。
- 修改文件/本地提交：无。
- 剩余工作：需按目标产物SBOM映射、合并别名、评估升级兼容性/可达性；未关闭审计、未批准风险豁免。 未自行批准延期。

## RAG-AUD-07 领取前取消问答，只终止 job，可能留下永久 queued 的回答

- 状态：已验证（本机源码集成）。
- 适用性：已确认；基线没有修复。
- 审查定位：`engine/ragsystem/ipc/server.py`, `engine/ragsystem/jobs/repository.py`, `engine/ragsystem/workflows/workbench.py`, `apps/desktop/src/components/MvpAsk.tsx`
- 审查根因：取消路由仅调用 Jobs.cancel；该方法只更新 jobs/job_attempts/events。run_answer 在 claim 返回 None 后直接返回。前端根据 answer_runs 的 queued/running 字段设置 pending，而不是从已取消 job 反推终态。
- 修复与业务测试：用同步屏障暂停 worker 在 claim 前，取消再放行；断言 job 和 answer_run 均为 cancelled、无模型调用、前端能再次发送。
- 本轮测试：B-red 6 FAIL；B-green 18 PASS/1 SKIP（未提供E5资源变量）；B-recovery-matrix 9 PASS/0 FAIL/0 SKIP。
- 断言：1000范围快照/小载荷、重读/幂等冲突/事务回滚/旧载荷兼容/篡改检测；claim屏障前取消回答不残留queued；所有任务类型queued/running重启后可取消，旧租约不可发布，恢复副本可激活；实际执行者未退出仍拒绝切换。
- 修改：workflows/preparation.py、ipc/mvp.py、ipc/server.py、jobs/repository.py、MvpLibrary.tsx、bridge.ts、test_audit_task_contracts.py、contracts/task-recovery-v0.6.md；本地提交ae72044。
- 验证边界：1000版本为合成入队/范围契约，不是1000篇PDF解析吞吐；不移除工作槽保护。复用现有scope_snapshots，无schema变更。

## RAG-AUD-08 历史证据重复读取

- 状态：已验证（源码业务计数、篡改回归和浏览器；最终冻结待复测）。
- 适用性/根因：已确认；History→public_evidence→anchor逐证据整PDF校验，完成后仍每秒拉全部历史。
- 修复：请求内以路径/预期SHA/设备/inode/大小/纳秒mtime/ctime复用校验；下一请求或实际打开仍重核，不建立跨请求可信缓存。非活动或不可见对话停止全量轮询，新提交重新启用。
- 红绿：C-evidence-red 2 FAIL；C-evidence-green 16 PASS；C-read-browser 47 PASS（包含完成后停止轮询）。同响应1/5轮各由3/15次原件读取降至1次，下一请求篡改仍失效。
- 基准：C-read-benchmark-final exit0；同临时库两公开PDF、1/30轮、每项5次热OS缓存P50/P95见read-benchmark-final.json。未实施清空系统缓存，冷物理IO未测，不能将热缓存结果称冷启动SLA。
- 修改：source_search.py、workbench.py、history.py、MvpAsk.tsx、test_audit_evidence_reads.py、browser_chat_management.cjs、benchmark_audit_reads.py。
- 剩余风险：活跃生成仍按既有接口读历史；此修改不等于引入轻量状态端点。Windows原生及最终候选需复测。

## RAG-AUD-09 文献列表N+1

- 状态：已验证（SQL计数及元数据/项目集成）。
- 适用性/根因：已确认；每版本分别查候选、job、DOI，更新前后全列表。
- 修复：候选/job按256版本有界批量，DOI一次映射；元数据更新仅查目标版本。保留全局可见DOI候选及字段优先级。
- 红绿：C-library-red 1 FAIL（50条102 SELECT）；C-library-green-corrected 1 PASS（5 SELECT）；C-library-metadata 20 PASS。首个green指定了不存在文件，exit4，不计作业务失败/通过。
- 同机热缓存5样本：1000合成版本2002→11 SELECT，P50 9.23→5.15ms，P95 12.02→5.20ms；1版本4→5 SELECT。记录不含真实千篇PDF/解析/向量，不能声明千篇整体验收。
- 修改：library/repository.py、test_audit_library_queries.py、benchmark_audit_reads.py；日志同本任务evidence目录。
- 剩余风险：列表仍为全量快照，未改变公开分页/应用状态契约；容量上限需真实语料验收。

## RAG-AUD-10 成功导入和重复导入仍永久保留新建 staging 文件

- 状态：已验证（本机存储故障集成）。
- 适用性：当前代码确认并已复现。
- 审查定位：`engine/ragsystem/ingestion/import_pdf.py`
- 审查根因：每次 run 都新建 job_id+随机值的 .part；通过 os.link 发布，不论目标已存在还是本次任务成功，finally 只关闭授权文件句柄，没有对本任务 staging 对象做成功后的处理。
- 修复与业务测试：连续导入同一文件 10 次，确认文档去重且实际分配块数有界；在复制、发布、提交各阶段崩溃后仍可恢复，活跃任务临时对象不得被删除。
- 本轮命令：C-storage-red 5 FAIL；C-storage-green 26 PASS/0 FAIL/0 SKIP。
- 业务断言：重复导入十次只保留原件和未知归属文件；崩溃残留保持；清理失败有event留痕且已提交文档保持成功；备份数据库/总量/可用空间不满足时禁止进入复制，原有备份/恢复故障回归保持。
- 修改：ingestion/import_pdf.py、storage/backup.py、bridge.ts、test_audit_storage_capacity.py；本地提交d2e8097。
- 边界：不清理未知或历史staging，只处理本次成功任务的唯一创建路径并核对inode；容量预估不保证磁盘不会随后耗尽，复制后完整性及故障隔离继续执行。未做真实千篇容量声明。

## RAG-AUD-11 备份完整复制后才检查可接受容量，超限任务产生无效大副本

- 状态：已验证（本机存储故障集成）。
- 适用性：当前代码确认并已复现。
- 审查定位：`engine/ragsystem/storage/backup.py`, `engine/ragsystem/storage/backup.py`, `engine/ragsystem/storage/backup_service.py`
- 审查根因：_create 先复制 SQLite 和所有原件；inspect 才限制总量 8 GiB、SQLite 文件 512 MiB。BackupService 创建后再 inspect，失败会保留/隔离副本。
- 修复与业务测试：构造越过数据库/总量上限的测试元数据或稀疏测试文件，验证在大规模复制前拒绝；测试复制中磁盘满、取消、隔离保留和正常恢复。
- 本轮命令：C-storage-red 5 FAIL；C-storage-green 26 PASS/0 FAIL/0 SKIP。
- 业务断言：重复导入十次只保留原件和未知归属文件；崩溃残留保持；清理失败有event留痕且已提交文档保持成功；备份数据库/总量/可用空间不满足时禁止进入复制，原有备份/恢复故障回归保持。
- 修改：ingestion/import_pdf.py、storage/backup.py、bridge.ts、test_audit_storage_capacity.py；本地提交d2e8097。
- 边界：不清理未知或历史staging，只处理本次成功任务的唯一创建路径并核对inode；容量预估不保证磁盘不会随后耗尽，复制后完整性及故障隔离继续执行。未做真实千篇容量声明。

## RAG-AUD-12 Embedding 虽然批量推理，缓存和关联仍逐条事务写入

- 状态：已确认；待修复与测量。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`engine/ragsystem/indexing/incremental.py`, `engine/ragsystem/storage/database.py`
- 审查根因：增量索引逐项 get/persist/link；这些方法独立打开连接或提交事务。Database 使用 synchronous=FULL，因此“按批编码”不等于“按批持久化”。
- 修复与业务测试：比较事务数、编码数、写入数和总耗时；缓存命中不得重新编码；在批次中取消/崩溃后不得发布半成品索引。
- 当前调用链/证据：embed_visible逐摘要cache.get、逐向量persist、逐Chunk link；Embeddings方法独立db.transaction，Database synchronous=FULL。
- 修改文件/本地提交：无。
- 剩余工作：待有界批次读写、取消/租约边界及事务数/缓存命中实测；最终新代校验发布必须保持。 未自行批准延期。

## RAG-AUD-13 按子串拦截 systematic review，误拒单篇论文的正常问题

- 状态：已验证（本机意图路由集成）。
- 适用性：当前调用链确认，需整改。
- 审查定位：`engine/ragsystem/workflows/workbench.py`
- 审查根因：create_answer 在意图拆分前，只要 question.casefold() 包含“所有论文/全库/all papers/every paper/systematic review”等任一片段，就抛出 RESEARCH_REQUIRED。
- 修复与业务测试：新增单篇术语问答、引用中出现 all papers、真正要求逐篇穷尽的中英文对照用例；前两类可正常检索，后一类仍进入或提示逐篇研究。
- 本轮结果：D-intent-red：4 FAIL/5 PASS；D-intent-green：36 PASS/0 FAIL/0 SKIP。正常术语/引号问法入队，真正逐篇穷尽请求仍拒绝Top-K冒充全库。
- 修改：retrieval/research_intent.py、workflows/workbench.py、test_audit_intent.py；本地提交f136937。
- 边界：意图规则为有界确定性规则，不等于真实RAG效果验收；TS流测试不替代原生或浏览器交互。

## RAG-AUD-14 LanceDB 路径将全部范围内向量物化为 Python 记录再截取 Top-K

- 状态：已确认；待修复与测量。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`engine/ragsystem/vector_adapters/lancedb.py`
- 审查根因：search 使用 limit(len(eligible)).to_list() 后进行本地排序/截取；ids 路径先 to_arrow 再取 embedding_id 列。两者可能传回远超最终 K 的数据，包括不需要的向量列。
- 修复与业务测试：对同一授权范围比较旧实现与精确参考结果，覆盖同分、空范围、过滤后候选不足；记录返回中间数据量和峰值 RSS，验证无越范围召回。
- 当前调用链/证据：LanceDB.search_exact使用prefilter=True后limit(len(eligible)).to_list再排序截K；ids使用整表to_arrow取ID列。
- 修改文件/本地提交：无。
- 剩余工作：范围过滤正确，不能用先TopK后过滤替代；待投影、有界结果/同分精确参照与RSS测量。 未自行批准延期。

## RAG-AUD-15 模型连接测试的刷新失败会跳过 busy 复位

- 状态：已修复待验证（异步流5项单元已通过，React组件交互未完成）。
- 适用性：当前调用链确认，需整改。
- 审查定位：`apps/desktop/src/components/GenerationConnections.tsx`
- 审查根因：probe 的 finally 为 await refresh(); await onSaved?.(); setBusy(false)。任意一次 await 拒绝都会在清除 busy 前退出；调用点使用 void probe(item)，该新异常还可能成为未处理 rejection。
- 修复与业务测试：分别模拟 probe 成功/失败后 refresh 拒绝、onSaved 拒绝和组件卸载；按钮必须恢复，错误类别明确，无未处理 Promise rejection。
- 本轮结果：B-probe-red：5 FAIL；B-probe-green：5 PASS。旧probe控制流提取为可执行TS单元后复现；未将该单元测试冒充DOM卸载测试。TypeScript typecheck PASS。
- 修改：GenerationConnections.tsx、probeConnection.ts、tests/frontend/probeConnection.test.ts；本地提交f136937。
- 边界：意图规则为有界确定性规则，不等于真实RAG效果验收；TS流测试不替代原生或浏览器交互。

## RAG-AUD-16 问题字符上限与向量 Token 上限未形成一致契约，错误提示误指向文档

- 状态：已确认；待修复与Tokenizer边界运行验证。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`engine/ragsystem/ipc/server.py`, `engine/ragsystem/workflows/workbench.py`, `engine/ragsystem/models/local_onnx.py`, `apps/desktop/src/bridge.ts`
- 审查根因：搜索接受最多 20000 字符，问答界面最多 4000 字符；指代查询还拼接历史问题。E5 的输入上限为 512 Tokens，溢出拒绝。前端 EMBEDDING_CONTEXT_LIMIT 文案却建议“重新解析为较短片段”，未区分查询文本和文档 Chunk。
- 修复与业务测试：用固定模型 tokenizer 生成 511/512/513 Token 和历史追加边界样例，分别覆盖查询与 passage；验证错误文案、历史裁剪记录以及失败不改变已有索引。
- 当前调用链/证据：SearchRequest允许20000字符，MvpAsk允许4000；Workbench.retrieval_context拼历史；LocalE5.encode使用512Token，query/passage共用EMBEDDING_CONTEXT_LIMIT；bridge该码仍提示重解析文档。
- 修改文件/本地提交：无。
- 剩余工作：待用锁定Tokenizer做511/512/513边界、当前问题优先与历史预算、独立QUERY_CONTEXT_LIMIT和诊断记录；本轮尚未修改，不能算通过。 未自行批准延期。

## RAG-AUD-17 评估工具存在，但真实人工金标和已批准质量验收尚未闭环

- 状态：阻塞（真实效果验收）；评估工具补齐仍待实施。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`docs/evaluation/goldset-protocol.md`, `engine/ragsystem/retrieval/evaluation.py`
- 审查根因：评估文档明确无真实金标，并在后续更新中记录 0 个人工裁定样本、阈值 pending；文档明确说明 gold/prediction 是待填写的空模板。已有 Recall@5/10、MRR、NDCG@10、时延计算和离线科学质量评分工具，不能误报为“没有评估机制”。
- 修复与业务测试：提供可重跑的冻结数据清单、独立评审记录、分组指标、失败样例和完整运行指纹；模型自评分不得当成人工真值；阈值须预先批准，不因本次失败而临时降低。
- 当前调用链/证据：goldset-protocol记录缺独立人工标注/批准阈值；retrieval.evaluation已有Recall/MRR/NDCG与latency，tools科学评估器存在。未获取本轮独立人工金标。
- 修改文件/本地提交：无。
- 剩余工作：不能用合成测试/模型自审证明真实准确率；待补Precision@K、语义评价及全调用成本字段和重跑说明，真实评分需授权语料与独立标注。 未自行批准延期。

## RAG-AUD-18 源码 CI 与完整冻结侧车、浏览器集成、原生安装验收之间仍有断层

- 状态：已确认；发行门禁未完成。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`.github/workflows/ci.yml`, `packaging/build_sidecar.py`, `packaging/build_sidecar.py`, `tools/browser_mvp.cjs`
- 审查根因：CI 包括 Ruff/Pytest/TS build/Rust tests/clippy/npm audit；build_sidecar 不带 include-* 标志，默认排除向量、生成、OCR、Docling 可选运行时。tools 中有连接冻结引擎的浏览器脚本，但当前 CI 未运行这些脚本；desktop-e2e 目录本身是验收文档。
- 修复与业务测试：同一提交、同一源指纹的完整侧车和应用在目标干净账户运行；覆盖导入→解析→索引→问答→引用→取消/重启→备份恢复，并单列模型缺失、平台跳过、签名/安装未验证项。
- 当前调用链/证据：ci.yml仅源码/模型无关侧车，未执行browser工具或完整可选运行时包；本机M1完整冻结及浏览器正在补本轮证据，但不替代安装后原生验证。
- 修改文件/本地提交：无。
- 剩余工作：Windows11目标机、证书/公证账户及产物许可未齐；候选构建/资源首次初始化/原生安装链路仍待实施，不标已验收。 未自行批准延期。

## REL发行登记

| 编号 | 范围 | 状态 | 所需证据 |
|---|---|---|---|
| REL-001 | Windows11x64与macOS ARM64候选范围、运行时/模型区分 | 待核查 | 明确功能与资源矩阵 |
| REL-002 | 无开发环境的完整安装后主链路 | 待核查 | 同源指纹产物及干净账户操作记录 |
| REL-003 | 签名/公证/许可证再分发 | 阻塞 | 当前无新证书/账户授权；需逐资源许可清单 |
| REL-004 | 首次资源检查/离线/缺资源/卸载与升级恢复 | 待核查 | 可运行流程与故障回归 |

## 基线执行

正在运行当前环境可执行的Python全量、Ruff、TS构建及依赖审计。完整冻结测试使用已存在且指纹匹配的FINAL侧车；不下载模型。

基线实际：Python398 PASS/0 FAIL/0 SKIP（125.33秒）；Ruff/TS PASS；dependency_gate exit1，648锁组件、6依赖8公告记录；许可映射BLOCKED。无付费API/用户库访问。

## 当前修复单元及恢复顺序

- 45f3c50：01/02/03。
- ae72044：04/05/07后端及UI入口、兼容协议。
- d2e8097：10/11。
- f136937：13/15（15组件故障交互仍待专项）。
- 未完成项保持开放：06、12、14、16、17、18；04及15补UI故障交互证据。没有不适用项，也没有获批延期项。
- 恢复执行：先读本台账与execplans/AUDIT-REMEDIATE-20261108.md，核对分支/dirty文档；按08/09/12/14性能业务计数测试→16 Token预算→06精确依赖处置→17评估格式→18/REL候选构建及原生矩阵继续。不得使用清理旧产物或调整skip掩盖缺口。
