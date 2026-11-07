# 当前源码完整验证、清理审查与 main 同步

Task ID / 阶段：VERIFY-CLEAN-SYNC，2026-11-06，macOS 26.2 ARM64。

2026-11-07 最终结果：**本机 Python 398 PASS / Rust 10 PASS / 浏览器 46 断言 PASS**，均无失败和跳过；新 VERIFY-CLEAN-SYNC-FINAL 侧车及 102 项源码哈希核对通过。源码 `fcdaead` 的远端 macOS / Windows source CI 均全部通过；OSV 明确 FAIL（6 个锁依赖、8 条公告记录）。历史构建实际删除仍为 0，待按清单手动处理。

用户本次明确授权完整测试、代码/构建清理及直接提交推送 GitHub main。覆盖 SECTION-AWARE 当时禁止提交推送的限制；不创建 PR、不强推、不发布 Release。本轮开始于 9d301b3，20 项既有未提交变更均为本会话的章节/段落改造，保留后纳入验收和提交。GitHub 当前 main 已独立确认为同一 9d301b3；本地 origin/main 落后只是 fetch 失败后的旧 tracking ref。

## 实际代码清理

审查 Python AST 的顶层函数和私有方法引用，结合 TS 未使用检查、Ruff 和 Rust Clippy，未发现足以认定可删除的整模块。动态 IPC/worker/打包入口、LegacyWorkspace、历史回归工具仍有用途；未以“当前主 UI 不显示”判断死代码。

在 `engine/ragsystem/chunking/structure.py::_native` 中去掉一个不会被消费的 abstract 类型分支：inline 摘要走专用路径，原先提前计算的 kind 不会被读取。类型计算移入真正使用它的非 inline 分支，避免无效计算；不改变任何 Chunk 内容、边界、章节规则或偏移。已有 41 项结构测试随完整集验证，不为这项等价整理增加照抄实现的测试。

本次新增执行计划、报告、验证索引和手动清理清单，PLANS 更新当前授权/状态。上一任务完整实现文件清单见 `SECTION-AWARE-CHUNKING-IMPLEMENTATION.md`。没有删除业务模块、测试、失败日志、旧迁移、模型、PDF 或用户数据；锁文件没有修改。

## 完整验证结果

所有计数来自本轮实际执行，未引用上一轮通过数替代测试。原始输出保留在本机忽略目录 `docs/engineering/evidence/VERIFY-CLEAN-SYNC/`；可提交的命令、时间、退出码和日志哈希见 `VERIFY-CLEAN-SYNC-validation.json`。

| 验证 | 实际结果 | 命令要点 |
|---|---|---|
| Python 单元/集成全量 | **395 PASS / 0 FAIL / 0 SKIP**，exit 0，133.63 s | `engine/.venv/bin/python -m pytest -c engine/pyproject.toml -q` |
| Rust 全量及 ignored 候选 | **10 PASS / 0 FAIL / 0 ignored**，exit 0 | `.tools/cargo/bin/cargo test --locked --offline --manifest-path apps/desktop/src-tauri/Cargo.toml -- --include-ignored --test-threads=1` |
| Ruff | PASS，exit 0 | `ruff check --config engine/pyproject.toml engine/ragsystem tests tools/compare_section_chunking.py` |
| Rust Clippy | PASS，exit 0 | `cargo clippy --locked --offline --manifest-path apps/desktop/src-tauri/Cargo.toml --all-targets -- -D warnings` |
| TypeScript/Vite | PASS，exit 0 | `npm --prefix apps/desktop run build -- --emptyOutDir=false` |
| 浏览器功能验收 | **46 断言 PASS**，exit 0 | `node tools/browser_smoke.cjs`，CHAT_MANAGEMENT=1，实际源码引擎 |
| 新冻结侧车 | PASS，exit 0，102 项源码及二进制哈希一致 | build-label=VERIFY-CLEAN-SYNC，全部已有候选运行时 |
| npm 依赖审计 | PASS，**0 vulnerabilities**，exit 0 | lock-only、moderate 阈值、显式系统 HTTPS proxy |
| OSV 全锁依赖审计 | **BLOCKED**，exit 2 | 648 个锁组件；直连及系统代理均 URLError |
| 科研质量门禁 | **BLOCKED**，exit 2，0 已标注案例 | 已有 evaluate_scientific_quality.py + 空金标模板 |
| 真正 Windows 干净安装 | **NOT EXECUTED** | 当前本机为 macOS；远端 CI 不代替实机安装 |

完整 Python 显式配置已批准的 E5、tessdata-fast、Docling、现有扫描 PDF 及本轮新冻结侧车；Rust 使用同一新侧车，经 Rust transport 实际运行索引、OCR、Docling、会话与模型持久化等候选。模型未下载、无付费 API。唯一 Python warning 是既有 Starlette/httpx 弃用提示，不为测试通过安装替代依赖。

浏览器覆盖：真实公开 PDF/E5 索引、来源 PDF 渲染、问题/回答复制、轮次证据隔离、归档恢复重命名删除、运行中拒绝删除、保存/重启单 API 配置、输入目录完整列表、提问即滚动、历史翻页不抢滚动、响应式区域有界。Tauri transport 和生成服务是协议 fixture，不能冒充原生文件对话框、真实云回答或 Windows 安装验收。

TS 构建显式设置 emptyOutDir=false，避免构建命令隐式清空旧 dist；新冻结构建采用独立目录。Python/Rust 回归中的清理仅属于现有隔离测试生命周期，不操作用户工作区。

## 网络及依赖门禁

本机 Git/curl 使用 LibreSSL，连接 GitHub 发生 SSL_ERROR_SYSCALL；HTTP/1.1、现有系统代理及 TLS1.2 探测未解决。GitHub 连接器和 gh 的 API 通路可读仓库，已核对账号为 maczhouyi-del、仓库为 maczhouyi-del/RAGTest，存在 push 权限。没有关闭证书验证或改写全局代理/认证配置。

npm 首次审计因 TLS 连接失败，显式传入系统 HTTPS proxy 后返回 0 漏洞。OSV 直连和一次仅调整网络 opener 的临时代理 harness 均失败；扫描/范围判定逻辑未改，失败记录保留。旧报告的 OSV FAIL 不能自动转 PASS，本轮无法确认它是否解除，依赖安全/发行门禁仍未通过。没有为了清理而未经评估升级所有依赖或压制审计结果。

## 历史构建产物：待手动清理

用户提供的 AGENTS.md 明确要求：**“禁止批量删除文件或目录，也不得通过循环、脚本或连续逐文件删除规避此限制。”** 以及 **“需要批量删除时，仅停止删除及依赖该删除的步骤，说明具体路径并请用户手动处理；继续其他已授权工作。”** 本次普通清理请求未明确撤销这一限制。

已盘点 **11 个历史目录，约 8.318 GiB**，实际删除 **0**；不是已回收空间。已保存 20 份关键构建诊断副本及哈希；未删除失败日志。请用户手动处理 `BUILD-CLEANUP-PENDING-2026-11-06.md` 中列出的具体绝对路径，不要删除整个 .tools/build。

保留最新 VERIFY-CLEAN-SYNC 侧车及工作目录、上一份 SECTION-AWARE verified 回退产物、最后开发 GUI/CHAT-02 侧车。模型、PDF、用户数据库、target 和 dist 不在清理候选中。清理未完成不阻塞已授权的源码验收和 GitHub 同步。

## 提交与同步方式

通过普通本地 commit 在 main 保存已审阅源码、测试、契约、报告。模型、PDF、数据库、原始日志、构建产物和凭据不进入 Git。

若 Git HTTPS 传输持续失败，使用 gh 调用 GitHub Git Data API 上传同一组 Git 对象：base tree 必须等于本地父提交；上传后 tree SHA、commit SHA 必须逐一等于本地值，才允许对 main 执行 force=false 更新；更新前后复核远端 head。不会以不同内容重造提交、强制覆盖远端或创建 PR。最终实际提交 SHA、远端核验和传输结果存于本机 evidence/VERIFY-CLEAN-SYNC/delivery.json，并由最终交付消息给出。

远端 Actions 触发后另行核对状态；本报告的本地 PASS 不表示全部跨平台/安全/科研门禁通过。

### 2026-11-07 远端复核及 Windows 测试修复

源码已提交并同步 main `8f2bf794ca535f786a64fbac40cf32d29993c740`，本地与远端 tree/commit SHA 一致。Actions 42220868088 的 macOS source 通过；lock-audit 失败，6 个锁依赖有 8 条公告记录（含别名），不是本次锁文件变更引入。diskcache、glib、proc-macro-error、zbus_names、zvariant、zvariant_derive 需要独立评估，未压制告警或据此宣称已确认运行时可利用。

Windows source 最终 cancelled，Python 阶段出现失败和 setup error，不是通过。日志已确认超大响应测试的自动参数 ID 将 1 MiB payload 写入 PYTEST_CURRENT_TEST，触发 Windows 32767 字符环境变量限制，并产生超长 traceback。为四个响应边界样本设置简短稳定 ID，保留原始 payload、断言及全部测试；本机定向 12 passed。其他失败尚须在修复后的 Windows CI 取得完整信息，不能把这一次修复当作 Windows 全量通过。原始日志保存在本机 evidence/VERIFY-CLEAN-SYNC/github-windows-initial.log。

第二轮 main `2e789b9` / Actions 42265283048 得到完整 Windows Python 结果：372 passed / 6 failed / 17 skipped。明确失败为 backup_copy 隔离进入 manual_review、Job Object 退出码假设、三个侧车 readiness、父进程被杀后 worker 管道未关闭；参数 ID 错误已消失。保留 `github-windows-after-test-ids.log`。

后续修复：备份创建、只读核验、迁移前备份均显式关闭 SQLite connection，同时保留事务上下文；sqlite3 的事务上下文本身不会关闭连接，Windows 仍持有文件句柄时不能重命名目录。新增强引用保留连接的回归用例，使垃圾回收不能掩盖泄漏；备份/迁移定向 20 passed。进程测试采用 CPython multiprocessing 同款 Windows base executable + `__PYVENV_LAUNCHER__` 交接，保留 venv 包路径并让测试控制实际解释器 PID；父监督测试传递实际父 PID。Job Object 测试检查 30 秒子进程在关闭 job 后 5 秒内退出，不再假定必须非零退出码，并保证失败也回收子进程。readiness 失败只记录 HTTP 状态/异常类型和退出码，不记录凭据或文献。

参考：[CPython Windows spawn 实现](https://github.com/python/cpython/blob/main/Lib/multiprocessing/popen_spawn_win32.py)、[Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。侧车 readiness 根因仍待后续 Windows 结果确认，未通过增加等待时间或跳过测试处理。

本机补测：新冻结 VERIFY-CLEAN-SYNC-WIN 侧车构建成功；使用该侧车及已批准 E5/OCR/Docling 资源，完整 Python **396 passed / 0 failed / 0 skipped**（126.60 秒），Ruff PASS。原始记录 `20261106T180502363718Z-python-windows-fixes.json`。CI 新增独立 Windows 生命周期前置回归，便于快速保留跨平台失败；成功后仍运行原全量套件，未删除或缩减验收。

### Windows 冷启动探测定位

`06acbd3` 的 Actions 42268823669：macOS source PASS，Windows 专项 14 passed / 3 failed / 1 skipped。备份隔离、Job Object 和父进程监督已通过；剩余三个失败均为握手后的健康检查 ReadTimeout，进程仍存活。`c946dff` 添加测试子进程限定长度、脱敏的启动线程栈；Actions 42334659360 在三个失败中均显示 `health → HybridSearch.status → sqlite_vec.load_extension → sqlite_vec.__init__ → numpy.typing → numpy._core.multiarray`，停在 NumPy 原生模块初始化。此证据定位触发链，不断言 NumPy 内部阻塞的具体底层原因。原始日志 `github-windows-startup-stacks.log` 保留。

修复 `engine/ragsystem/vector_adapters/sqlite_vec.py`：通过固定包名的 `find_spec` 定位已安装/已打包的 sqlite_vec 目录，直接加载与原包装器相同的 `vec0` 扩展，不执行会附带导入 NumPy 的包初始化。没有用户路径输入、没有替换向量后端、依赖锁或距离算法；加载权限仍在 finally 中关闭，缺少扩展仍明确不可用。

新增 `test_cold_extension_probe_in_http_worker_does_not_import_numpy`：在全新进程/工作线程实际加载扩展，禁止 NumPy 及 sqlite_vec Python 包导入，验证运行时可用且未隐式初始化 NumPy。既有精确距离、过滤、更新/删除、索引持久化与扩展授权关闭测试继续运行。定向 13 passed / 1 skipped（未提供冻结侧车），随后完整回归使用新 VERIFY-CLEAN-SYNC-COLD 侧车。浏览器 46 断言已复测通过，保留真实引擎/模拟 Tauri transport 的边界。

最新完整 Python **397 passed / 0 failed / 0 skipped**（143.78 秒）；Rust 含候选 **10 passed / 0 failed / 0 ignored**（183.25 秒）；浏览器 **46 PASS**。三个执行日志及新冻结构建记录已加入 validation.json，不覆盖历史失败证据。Rust 真实冻结侧车验证包括 sqlite-vec/E5 索引、OCR、Docling、会话持久化和来源校验，证明直接扩展定位在打包运行中有效。没有修改 RAG 排序、模型、引用核验或数据库 schema。

`5991567` / Actions 42335798435 的 Windows 专项进一步达到 16 passed / 1 failed / 1 skipped：三个启动握手/readiness 已全部跨过，唯一失败为提交批注时返回 429 WORKER_BUSY。解析在事务内发布 completed 后还需返回并执行后台 finally 释放工作槽；测试把可见完成误当作工作槽已释放，与已有 `contracts/mvp-v0.5.md` 的 WORKER_BUSY/retriable=true 契约不符。测试仅对该明确响应做最多 5 秒的客户端等待，其他错误立即失败，工作槽泄漏仍失败，并新增只保存一条批注的核对；没有修改服务器并发保护、引入应用自动重试或放宽答案/数据验收。临时 6 秒线程栈定时器已移除，避免长测试的 stderr 管道压力；失败状态码/退出码和有界脱敏 stderr 保留。新冻结侧车的生命周期与调度定向 **5 passed / 0 failed / 0 skipped**（14.45 秒）。

`01c8064` / Actions 42368420904 已正常同步，Windows 专项仍 16 passed / 1 failed / 1 skipped，但已通过批注保存，失败推进到空模型目录的索引任务未及时结束。LocalE5 在检查 manifest 前导入 NumPy/ONNX，导致无效资源也启动原生运行库；现将原有完整资源/哈希/维度验证前移到导入之前，校验规则和有效模型推理保持原样。新增禁止原生导入的缺失 manifest 回归；实际 E5 推理、源码侧车及调度定向 6 passed / 1 skipped（尚未提供新冻结侧车），Ruff PASS。原始日志 github-windows-index-invalid-model.log 保留。此修复不证明真实 Windows E5 首次原生加载已验收，该模型实机门禁仍待补。

`fcdaead` 修复后本机最终回归使用新 VERIFY-CLEAN-SYNC-FINAL 侧车：Python **398 passed / 0 failed / 0 skipped**（126.03 秒），Rust **10 passed / 0 failed / 0 ignored**（210.06 秒），102 项源码及二进制哈希全部一致。原始命令和日志哈希已加入 validation.json。Actions 42368722463 的 Windows 生命周期专项已通过、macOS source 全部通过；完整 Windows source 仍待最终结果。

最终远端结果：[Actions 42368722463](https://github.com/maczhouyi-del/RAGTest/actions/runs/42368722463)，验证源码提交 `fcdaead312eb61bdf4fd376277498d020c5e48af`。Windows source **PASS**：专项 17 passed / 1 skipped；全量 Python 381 passed / 17 skipped / 0 failed（534.32 秒）；Rust 7 passed / 3 ignored / 0 failed；TS 构建、冻结侧车、Ruff、Clippy、npm audit 0 漏洞均通过。macOS source **PASS**：Python 382 passed / 16 skipped / 0 failed；Rust 7 passed / 3 ignored / 0 failed，其余同样通过。跳过项为显式模型资源/可选运行时或平台专属测试，不当作通过；本机完整候选回归另为 398/10 全通过。Windows runner 为 Server 2025，仍不能替代干净 Windows 11 安装及模型实机验收。

原始最终日志 `github-windows-final.log`、`github-macos-final.log` 保存在本机忽略证据目录。独立 lock-audit 仍 FAIL，整个 workflow 结论因而为 failure，不能描述为“全部 CI 通过”。本次收尾提交仅更新报告、验证索引和 PLANS，产品源码与上述已验证提交一致。

## 状态与剩余事项

本机功能测试：**PASS**。macOS / Windows source CI：**PASS**。真实 Windows 安装：**NOT EXECUTED**。科研质量：**BLOCKED**。OSV 安全审计：**FAIL**。批量构建清理：**待用户按清单手动处理**。本轮不做 Release/发行承诺，无架构 ADR 变更，原 schema21 和既有 0001–0020 保持。
