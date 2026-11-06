# 当前源码完整验证、清理审查与 main 同步

Task ID / 阶段：VERIFY-CLEAN-SYNC，2026-11-06，macOS 26.2 ARM64。

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

## 状态与剩余事项

功能测试：**PASS**。真实 Windows 安装：**NOT EXECUTED**。科研质量：**BLOCKED**。OSV 安全审计：**BLOCKED**。批量构建清理：**待用户按清单手动处理**。本轮不做 Release/发行承诺，无架构 ADR 变更，原 schema21 和既有 0001–0020 保持。
