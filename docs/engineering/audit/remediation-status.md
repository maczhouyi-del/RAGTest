# RAGTest整改台账（2026-11-08）

基线00f8f6bc；独立分支codex/audit-remediation-20261108。状态：待核查、已确认、已修复待验证、已验证、不适用、阻塞。既有清理改动与输入材料不混入任务提交。

逐项结论以当前源码与本轮执行为准；下列初始证据均是审查输入，不能当作本轮运行验证。原始日志位于本机忽略evidence/AUDIT-REMEDIATE-20261108。

## RAG-AUD-01 单个待恢复原件异常可以阻断整个引擎启动

- 状态：已验证（本机源码集成/真实侧车子进程；M2完整冻结/Rust已复测；目标干净平台待验收）。
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

- 状态：已验证（本机源码集成/真实侧车子进程；M2完整冻结/Rust已复测；目标干净平台待验收）。
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

- 状态：已验证（本机源码集成/真实侧车子进程；M2完整冻结/Rust已复测；目标干净平台待验收）。
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

- 状态：已验证（后端专项及M2包内侧车浏览器重启任务取消）。
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

- 状态：阻塞（全锁审计与目标许可）。
- 适用性：当前代码仍适用；同基线复现，不把维护性公告和可利用漏洞混为一类。
- 审查定位：`.github/workflows/ci.yml`
- 审查根因：Actions run 42369976421：Windows 与 macOS 的 source job 成功，但 lock-audit job 128395893056 失败，整个工作流结论为 failure。读取到的日志报告 lock_integrity PASS、vulnerability_audit FAIL、license_review BLOCKED，存在 diskcache、glib 等公告命中。
- 修复与业务测试：同一提交的审计、源码测试和实际目标包 SBOM/许可清单一致；所有告警均有修复或审查结论。这里没有声称公告已具备可利用 PoC。
- 本轮命令：baseline-dependencies及final-dependencies均exit1，648组件、6包/8公告记录（含别名），锁完整性PASS，许可映射BLOCKED。npm两次执行HTTP400，属于审计执行失败，不能报告0漏洞。
- 精确目标映射：10条cargo tree --locked --offline探针，macARM/Winx64×5个Rust告警均exit0无反向依赖路径；完整证据target-dependency-mapping.json。首次Windows离线缺固定jiff-tzdb，补齐锁定开发依赖后重跑。未因此自动排除全锁风险。
- diskcache经llama-cpp可选运行时入包，llama.py:375默认self.cache=None、:646仅set_cache启用；应用local_generator.py没有set_cache/DiskCache调用。此为当前不可达路径证据，不等于对任意插件/未来修改的安全保证。
- 处置：docs/engineering/audit/dependency-triage-20261108.json逐包登记；上游DiskCache公告未给修复版本，存在本地可写缓存被反序列化的条件风险；proc-macro-error/zvariant为维护公告。未自动接受风险、删依赖审计或盲升不在当前目标树的Linux依赖。
- 状态：阻塞。需要目标实际SBOM/NOTICE完整映射与审查结论，或经兼容性验证的上游修复；不能把原始8条记录当8个独立可利用漏洞。无获批延期/豁免。

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

- 状态：已验证（源码业务计数、篡改回归及M2包内侧车浏览器）。
- 适用性/根因：已确认；History→public_evidence→anchor逐证据整PDF校验，完成后仍每秒拉全部历史。
- 修复：请求内以路径/预期SHA/设备/inode/大小/纳秒mtime/ctime复用校验；下一请求或实际打开仍重核，不建立跨请求可信缓存。非活动或不可见对话停止全量轮询，新提交重新启用。
- 红绿：C-evidence-red 2 FAIL；C-evidence-green 16 PASS；C-read-browser 47 PASS（包含完成后停止轮询）。同响应1/5轮各由3/15次原件读取降至1次，下一请求篡改仍失效。
- 基准：C-read-benchmark-final exit0；同临时库两公开PDF、1/30轮、每项5次热OS缓存P50/P95见read-benchmark-final.json。未实施清空系统缓存，冷物理IO未测，不能将热缓存结果称冷启动SLA。
- 修改：source_search.py、workbench.py、history.py、MvpAsk.tsx、test_audit_evidence_reads.py、browser_chat_management.cjs、benchmark_audit_reads.py。
- 本地提交：0b23d53。
- 剩余风险：活跃生成仍按既有接口读历史；此修改不等于引入轻量状态端点。Windows原生及最终候选需复测。

## RAG-AUD-09 文献列表N+1

- 状态：已验证（SQL计数及元数据/项目集成）。
- 适用性/根因：已确认；每版本分别查候选、job、DOI，更新前后全列表。
- 修复：候选/job按256版本有界批量，DOI一次映射；元数据更新仅查目标版本。保留全局可见DOI候选及字段优先级。
- 红绿：C-library-red 1 FAIL（50条102 SELECT）；C-library-green-corrected 1 PASS（5 SELECT）；C-library-metadata 20 PASS。首个green指定了不存在文件，exit4，不计作业务失败/通过。
- 同机热缓存5样本：1000合成版本2002→11 SELECT，P50 9.23→5.15ms，P95 12.02→5.20ms；1版本4→5 SELECT。记录不含真实千篇PDF/解析/向量，不能声明千篇整体验收。
- 修改：library/repository.py、test_audit_library_queries.py、benchmark_audit_reads.py；提交0b23d53，日志同本任务evidence目录。
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

- 状态：已验证（有界事务/回滚/缓存/租约检查及M2完整回归）。
- 根因：逐get/persist/link独立连接与FULL同步事务；基线可复现。
- 修复：128摘要批读、最多16（默认8）向量批持久化，128关联短事务；推理在事务外，推理后重查取消/租约，缓存仍按完整空间指纹。索引最终校验/原子发布未改。
- 红绿：C-batch-red 2 FAIL；C-batch-green 8 PASS；D-query-green-corrected包含取消补测共53 PASS。
- 同机同公开PDF/合成向量：323新增编码数不变，首次事务647→45，复用324→4、重编码0；单次首次591.48→65.46ms，不是模型性能/SLA。
- 修改：indexing/embeddings.py、incremental.py、test_audit_embedding_batches.py、benchmark_audit_vectors.py；提交2f8ae9f。无schema/历史迁移修改。
- 风险：已经提交的合法缓存可在取消后复用；不发布不完整索引。真实千篇吞吐未验收。

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

- 状态：已验证（精确范围/同分及合成内存测量；真实容量未验收）。
- 根因：全部范围记录含vector物化为Python；ids整表Arrow；基线仍适用。
- 修复：ids仅投影ID分批读取；精确距离仅投影ID/_distance、256行分批，heap保留TopK，仍先范围过滤且全量检查缺失ID。精确同分按ID排序，未用先TopK后过滤。
- 红绿：C-lance-red 2 FAIL；C-lance-green 12 PASS。含3000合成向量的cosine/l2、同分、空范围、候选不足与既有适配器契约。
- 同环境独立进程5000×384合成向量/3333授权/Top10：Python峰值42,734,040→1,083,427字节，进程峰值RSS489,127,936→366,002,176字节，单次251.09→32.80ms。冷/真实文献容量未测；原生精确扫描与授权ID集合仍O(N)，不宣称常数内存ANN。
- 修改：vector_adapters/lancedb.py、test_audit_lance_streaming.py、benchmark_audit_vectors.py。计量日志C-vector-benchmark；提交2f8ae9f。

## RAG-AUD-15 模型连接测试的刷新失败会跳过 busy 复位

- 状态：已验证（异步流5项及React浏览器故障/卸载交互）。。
- 适用性：当前调用链确认，需整改。
- 审查定位：`apps/desktop/src/components/GenerationConnections.tsx`
- 审查根因：probe 的 finally 为 await refresh(); await onSaved?.(); setBusy(false)。任意一次 await 拒绝都会在清除 busy 前退出；调用点使用 void probe(item)，该新异常还可能成为未处理 rejection。
- 修复与业务测试：分别模拟 probe 成功/失败后 refresh 拒绝、onSaved 拒绝和组件卸载；按钮必须恢复，错误类别明确，无未处理 Promise rejection。
- 本轮结果：B-probe-red：5 FAIL；B-probe-green：5 PASS。旧probe控制流提取为可执行TS单元后复现；另在final-browser-source-transport及final-browser-bundled分别53项通过，覆盖成功/失败×refresh/onSaved拒绝、卸载后无未处理异常。TypeScript构建PASS。
- 修改：GenerationConnections.tsx、probeConnection.ts、tests/frontend/probeConnection.test.ts；本地提交f136937。
- 边界：意图规则为有界确定性规则，不等于真实RAG效果验收；TS流测试不替代原生或浏览器交互。

## RAG-AUD-16 问题字符上限与向量 Token 上限未形成一致契约，错误提示误指向文档

- 状态：已验证（锁定真实tokenizer边界、溢出保持原索引及M2完整回归）。
- 根因：字符传输上限不等于512Token；query/passage共用文档错误码，历史拼接可能溢出。
- 修复：QUERY_CONTEXT_LIMIT独立提示；完整当前问题优先，指代时按最旧顺序移除历史问题，记录实际retrieval_query、query_token_limit和dropped_history_turns。保留文档拒绝静默截断和完整空间指纹。
- 红绿：D-query-red 2 FAIL/5 PASS；首次green 49 PASS/1 FAIL，暴露检索配置缺失时丢失诊断，已修复；corrected 53 PASS。真实E5 query/passage 511/512允许，513拒绝，无溢出推理调用。
- 修改：local_onnx.py、hybrid.py、workbench.py、bridge.ts、test_audit_query_budget.py、contracts/query-budget-v0.7.md；提交2f8ae9f，无schema变更。
- 风险：字符上限仍是传输保护；Token限制只用于向量/混合，不限制关键词模式。不改变已有索引或自动转云。

## RAG-AUD-17 评估工具存在，但真实人工金标和已批准质量验收尚未闭环

- 状态：阻塞（真实效果验收）；评估工具补充已由最终460项回归验证。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`docs/evaluation/goldset-protocol.md`, `engine/ragsystem/retrieval/evaluation.py`
- 审查根因：评估文档明确无真实金标，并在后续更新中记录 0 个人工裁定样本、阈值 pending；文档明确说明 gold/prediction 是待填写的空模板。已有 Recall@5/10、MRR、NDCG@10、时延计算和离线科学质量评分工具，不能误报为“没有评估机制”。
- 修复与业务测试：提供可重跑的冻结数据清单、独立评审记录、分组指标、失败样例和完整运行指纹；模型自评分不得当成人工真值；阈值须预先批准，不因本次失败而临时降低。
- 当前调用链/证据：goldset-protocol记录缺独立人工标注/批准阈值；retrieval.evaluation已有Recall/MRR/NDCG与latency，tools科学评估器存在。未获取本轮独立人工金标。
- 修改：retrieval/evaluation.py、tools/evaluate_scientific_quality.py、goldset-protocol.md、test_audit_evaluation.py；本地提交2f8ae9f。
- 剩余工作：不能用合成测试/模型自审证明真实准确率；已补Precision@5/10未知标签保护、独立人工answer_relevance及分角色完整调用Token/费用记账和重跑说明；D-evaluation-red 2 FAIL，green 13 PASS/1 SKIP（缺E5环境，最终完整环境复测），真实评分需授权语料与独立标注。 未自行批准延期。

## RAG-AUD-18 源码 CI 与完整冻结侧车、浏览器集成、原生安装验收之间仍有断层

- 状态：阻塞（本机工程链路已验证，干净原生发行未验收）。
- 适用性：当前代码仍适用，未发现其他提交已修复；基线与报告相同。
- 审查定位：`.github/workflows/ci.yml`, `packaging/build_sidecar.py`, `packaging/build_sidecar.py`, `tools/browser_mvp.cjs`
- 审查根因：CI 包括 Ruff/Pytest/TS build/Rust tests/clippy/npm audit；build_sidecar 不带 include-* 标志，默认排除向量、生成、OCR、Docling 可选运行时。tools 中有连接冻结引擎的浏览器脚本，但当前 CI 未运行这些脚本；desktop-e2e 目录本身是验收文档。
- 修复与业务测试：同一提交、同一源指纹的完整侧车和应用在目标干净账户运行；覆盖导入→解析→索引→问答→引用→取消/重启→备份恢复，并单列模型缺失、平台跳过、签名/安装未验证项。
- 当前调用链/证据：ci.yml仅源码/模型无关侧车，未执行browser工具或完整可选运行时包；本机M2完整冻结、包内侧车浏览器53及app/DMG已生成，但不替代安装后原生验证。
- 修改：packaging/build_candidate.py、tools/browser_smoke.cjs/browser_chat_management.cjs、candidate_preflight/upgrade_failure测试、ci.yml；本地提交46cf179。
- 剩余工作：Windows11目标机、发行签名/公证授权及产物许可未齐；普通用户资源取得、干净原生安装链路仍阻塞。源码CI仅新增TS故障单元，未执行远程CI、不谎称完整运行时已进CI门禁，不标已验收。 未自行批准延期。

## REL发行登记（均不自行延期）

| 编号 | 范围 | 状态 | 当前证据/缺口 |
|---|---|---|---|
| REL-001 | Windows11x64主目标与macOS ARM64候选、资源/网络矩阵 | 已验证（范围登记） | release/candidate-20261108.md；没有改变平台或添加服务 |
| REL-002 | 同源完整包与无开发环境链路 | 部分已验证/阻塞 | M2完整侧车、Rust10、包内侧车浏览器53；没有干净账户原生GUI安装证据 |
| REL-003 | 发行签名/公证/逐目标许可 | 阻塞 | Mac只有linker ad-hoc、无Team/资源密封；不调用账户；NOTICE/许可审查未闭环 |
| REL-004 | 备份升级恢复、卸载保留 | 部分已验证/阻塞 | 旧库升级/失败回滚/备份副本恢复/新schema拒开已测；Windows安装升级/卸载未测 |
| REL-005 | 普通用户资源取得/首次初始化 | 阻塞 | 已有设置页明确选择本地目录与缺资源提示；尚无经许可审查的用户资源包/下载恢复GUI，不宣称已满足首装普通用户体验 |
| REL-006 | Windows固定WebView2及原生DLL | 阻塞 | 新候选构建入口要求预置完整哈希清单，拒绝隐式latest下载；无授权运行时资源/目标机实测 |

构建入口packaging/build_candidate.py；已生成Mac app/DMG，版本仍0.1.0工程快照，非正式发行。详细产物SHA、范围、构建与恢复入口见release/candidate-20261108.md、candidate-20261108.json及reports/AUDIT-REMEDIATE-20261108.md。

## 基线执行

已运行当前环境可执行的Python全量、Ruff、TS构建及依赖审计。完整冻结测试使用已存在且指纹匹配的FINAL侧车；不下载模型。

基线实际：Python398 PASS/0 FAIL/0 SKIP（125.33秒）；Ruff/TS PASS；dependency_gate exit1，648锁组件、6依赖8公告记录；许可映射BLOCKED。无付费API/用户库访问。

## 当前修复单元及恢复顺序

- 45f3c50：01/02/03。
- ae72044：04/05/07后端及UI入口、兼容协议。
- d2e8097：10/11。
- f136937：13/15（15组件故障交互已补齐）。
- 未完成项保持开放：06、17、18；04及15 UI专项已完成。没有不适用项，也没有获批延期项。
- 恢复执行：先读本台账与execplans/AUDIT-REMEDIATE-20261108.md，核对分支/dirty文档；先核对M2完整测试及发行报告→06目标SBOM/依赖处置→17独立人工金标/批准阈值→18/REL普通用户资源与干净双平台安装矩阵继续。不得使用清理旧产物或调整skip掩盖缺口。

## 最终本机检查点

candidate-python：460 PASS/0 FAIL/0 SKIP（包内M2侧车，131.33秒）；final-rust：10 PASS/0 ignored；TS/Vite、Ruff、Clippy通过；TS故障流5 PASS；源码/包内/去开发变量包内浏览器各53 PASS。103项冻结源码/锁/入口哈希一致，Mac app/DMG已生成并CRC验证，未作发行签名/公证/原生GUI安装。正式发行NO-GO。

06/17/18及REL阻塞保留；没有不适用项或获批延期。其余15项在上述本机边界内已验证，不代表Windows或真实科研容量验收。完整产物与恢复入口见reports/AUDIT-REMEDIATE-20261108.md和release/candidate-20261108.md。
