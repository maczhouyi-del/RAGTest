# BUILD-CLEANUP-01 历史构建清理

- Task ID / 阶段：BUILD-CLEANUP-01，本地维护；2026-11-01。
- 授权：用户在明确获知批量删除限制与具体清单后，补充“此次你可以清理”。仅作为本次清单58个历史目录的删除例外，不扩大至其他路径或后续任务。
- 范围和实际变更文件：删除 `.tools/build/` 下清单列出的58个旧构建目录、662个文件；完整绝对路径见 evidence/BUILD-CLEANUP-2026-11-01/deleted-paths.json。无生产源码修改、依赖升级、用户库操作、提交/推送。
- 需求与契约：本次用户历史构建清理请求；保留最新CHAT-02三个目录，不改变应用契约和schema20。
- 已执行命令、平台、退出码、日志位置：macOS arm64；du/df/ps只读盘点；Python标准库tarfile归档、逐文件SHA256比对、对固定58路径shutil.rmtree删除、23个保留文件SHA256复核；准备和执行均exit0。进程过滤无匹配时rg为exit1，表示未发现应用/编译进程，并非删除失败。详细快照 prepared.json、result.json。
- 功能测试：清理范围、备份、保留文件与源码差异一致性 PASS；应用回归 NOT EXECUTED（无生产代码变动，沿用CHAT-02结果）。
- 真实 Windows 安装测试：NOT EXECUTED。
- 科研质量测试：NOT EXECUTED。

## 结果

实际可用空间增加约 **22.69 GiB**，由 15.60 GiB 增至 38.29 GiB；这是执行前后文件系统读数，可能受同时运行的其他程序影响。

314份历史manifest/spec/诊断/交叉引用/TOC已备份到 `historical-build-diagnostics.tar.gz`（约34.5 MiB），归档成员内容与原文件逐项SHA256一致；SHA256 `d5184d765c925fdd70d3017e34ae83b88a885f480bb26b6c951494f5c485da72`。历史报告不改写，已删除旧二进制的历史产物路径将不再可打开，诊断备份用于保留审计记录。

保留并核验23个文件哈希：

- `.tools/build/macos-chat02-final-20261101T144616691467Z/`
- `.tools/build/CHAT-02-sidecar/`
- `.tools/build/sidecar-20261101T143731118685Z/`

当前Rust target、前端dist、源码/既有未提交修改、模型、用户PDF/数据库/索引及原验收证据未被删除。清理前后git tracked diff哈希一致，随后仅添加本维护报告与PLANS记录。

- 关键发现/未解决的问题：当前target约6.6 GiB属于现有编译缓存，本次不清；无清理失败。
- 与方案不同的设计及ADR：无架构变化、无新ADR；临时构建诊断先备份后删除，避免丢失失败记录。
- 下一步及是否需要人工批准：本次清理完成，无剩余必需步骤；未改变其他任务的删除限制和发布门禁。
