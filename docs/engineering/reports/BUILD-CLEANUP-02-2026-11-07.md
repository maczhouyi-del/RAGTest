# BUILD-CLEANUP-02 历史构建产物清理（2026-11-07）

- Task ID / 阶段：BUILD-CLEANUP-02，本地维护。
- 授权：用户在明确获知批量删除限制与待清理清单后表示“此次你可以进行清理”，作为本次固定历史构建目录的删除例外，不改变未来任务限制。
- 范围和实际变更文件：删除 .tools/build 下17个历史构建目录、176个文件；更新本报告、执行计划、PLANS及旧待清理清单状态。无产品源码、契约、schema或依赖变更。
- 需求与契约对应：本次用户清理指令；保留已验证最终产物、当前运行应用、回退侧车及所有用户数据。
- 已执行命令、平台、退出码、日志位置：macOS26.2 ARM64；du/df/ps/lsof盘点；固定清单辅助脚本prepare/execute均exit0，tarfile诊断归档逐成员SHA256核对；evidence/BUILD-CLEANUP-2026-11-07/prepared.json、result.json、deletion-progress.json。准备时发现Finder元数据.DS_Store，保持原位后重新核验；没有因此扩大删除清单。
- 功能测试：清理范围、归档与保留文件哈希、应用进程、源码差异一致性 PASS；完整应用回归本次NOT EXECUTED（纯构建维护，无业务代码变更）。
- 真实 Windows 安装测试：NOT EXECUTED。
- 科研质量测试：NOT EXECUTED。

## 实际结果

删除文件逻辑大小 12.306 GiB，分配块合计 12.375 GiB。文件系统可用空间由 16.147 GiB 增至 28.523 GiB，实测增加 **12.376 GiB**；该差值也可能包含同期其他进程的空间变化。

89份manifest/spec/TOC/告警/交叉引用等诊断已保存并逐成员核验。归档：`/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/docs/engineering/evidence/BUILD-CLEANUP-2026-11-07/historical-build-diagnostics.tar.gz`；SHA256 `d7b1102822735b6310d0a1ce8d21260ae7772cbe880e4729d39b0631966976d9`。原验收日志及既有诊断副本继续保留。

保留5个目录的25个文件，删除前后SHA256全部一致：

- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/CHAT-02-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/macos-chat02-final-20261101T144616691467Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/SECTION-AWARE-verified-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/VERIFY-CLEAN-SYNC-FINAL-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261107T113342216806Z`

正在运行的App和侧车PID 91481/91487/91488均保留，未停止或重启；模型、PDF、数据库、向量、Rust target、前端dist、源码和密钥均未列入删除范围。

## 已删除的固定目录

- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/CODE-CLEANUP-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/SECTION-AWARE-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/SECTION-AWARE-v2-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/SECTION-AWARE-v3-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261101T143731118685Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261102T072258087103Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261105T115036194529Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261105T120004669614Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T032257247225Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T032731396803Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T032854876253Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/VERIFY-CLEAN-SYNC-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T123833037975Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/VERIFY-CLEAN-SYNC-WIN-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T180047547117Z`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/VERIFY-CLEAN-SYNC-COLD-sidecar`
- `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261107T034118884125Z`

- 关键发现/未解决的问题：无清理失败。原清单11目录及后续6个过渡构建均已清除；历史报告中的旧二进制路径不再可打开，诊断归档可用于审计。既有依赖安全、Windows实机和科研门禁不受此次清理结果影响。
- 与方案不同的设计及ADR：无架构变更，无新ADR。
- 下一步及是否需要人工批准：本次清理已完成，无剩余清理步骤；此次授权不扩展为未来批量删除许可。此维护轮未提交/推送。
