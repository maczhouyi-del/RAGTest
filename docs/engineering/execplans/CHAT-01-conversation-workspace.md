# CHAT-01 对话管理、逐轮证据栏、单API配置与滚动

用户2026-10-31明确授权四项完整实施与测试；按其顺序推进，不提交/推送/发布，不变更RAG算法、Embedding、RRF或核验规则。保留本轮前所有未提交修改；基线差异保存在本机 evidence/CHAT-01/before-existing.patch。

## 顺序、文件与验收

1. 检查：schema18，History已有更新时间游标；启动/刷新不保存Provider，GenerationConnections重挂载初始selected=null导致再次保存新UUID；主对话重复展示诊断且无稳定ID滚动。
2. 对话：新增0019迁移 archived_at；history.py/workbench.py/server.py、Rust lib.rs/bridge.ts/App.tsx及管理组件。归档/恢复/重命名持久；删除使用BEGIN IMMEDIATE检查任务状态/租约，活动任务明确拒绝，逐项清理本会话派生记录/终结任务；共享文献/索引/其他对话不动。项目作用域及分页保持。
3. 逐轮界面：MvpAsk/PipelineDiagnostics/样式与证据组件。聊天仅正文/必要状态，右侧绑定稳定run id，显示真实scope/trace/evidence/claims，分别滚动/窄屏自适应。
4. Provider：新增0020迁移，历史记录停用保留；唯一有效API数据库索引，保留确定的最新编辑项及旧配置、迁移备份，可显式恢复旧配置但撤销外发授权。ProviderRegistry/GenerationConnections/Rust/bridge保证编辑更新与并发防护；启动只读，不伪造认证。
5. 滚动：提交与打开历史仅按稳定轮次ID触发；早期历史保持视口，轮询不触发，不滚动窗口/右栏。
6. 验证：针对性pytest、完整pytest（批准本地模型/冻结侧车）、cargo test含候选、clippy、tsc/Vite、ruff、实际浏览器回归及新的本地开发app。命令用tools/run_logged.py保留退出码/时间/输出至evidence/CHAT-01；按实际CI配置执行可运行本机步骤，不声称Windows CI或科研金标PASS。

数据迁移风险：旧程序不兼容新schema，自动迁移前在线备份；绝不修改历史迁移。验证优先隔离测试数据与实际库只读副本，原用户对话不用于删除测试。当前已授权功能新增schema属于本任务范围，无需新增批准。无付费API/新模型下载；远程模型回归采用本机兼容端点工程测试，不能冒充云厂商实测。

最终报告列出四项实现、文件、迁移兼容、命令/通过失败跳过数、未解决项、界面前后变化；更新PLANS，交付新app并核对构建源码指纹。正式Windows/金标/千篇/发行门禁保持。

## 完成记录（2026-11-01）

上述六步完成。Python最终346通过/0失败/0跳过；Rust10通过；浏览器40项断言通过；TS/Vite、Ruff、Clippy、Mac实际新app重启核验通过。数据库schema20，原数据和257向量保留，8旧API记录整理为1有效+7可恢复历史。本机升级前的过期索引通过既有流程更新，复用257、新算0，旧文件保留。新增本机测试会话最终归档，未删除用户历史。

报告与限制见[CHAT-01报告](../reports/CHAT-01-2026-11-01.md)。依赖审计8条OSV记录仍FAIL，Windows/科研/规模/发行未验收。没有提交、推送、发布、安装新依赖或调用付费API。
