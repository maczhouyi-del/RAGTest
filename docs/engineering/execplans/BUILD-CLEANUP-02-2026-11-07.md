# BUILD-CLEANUP-02 本次授权的历史产物清理

用户在已获告知禁止批量删除规则、待清理清单后明确表示“此次你可以进行清理”，作为本次 .tools/build 历史构建的删除例外，不改变未来任务的限制。

范围：原清单11目录，及后续被FINAL替代的VERIFY-CLEAN-SYNC、WIN、COLD共6个输出/工作目录。只使用固定17路径清单；不删除整个build，不扩展到target、dist、模型、PDF、数据库或用户目录。

保留：正在运行的macos-chat02-final-20261101T144616691467Z、CHAT-02-sidecar、SECTION-AWARE-verified-sidecar、VERIFY-CLEAN-SYNC-FINAL-sidecar、sidecar-20261107T113342216806Z。

步骤：检查进程与打开文件、拒绝意外路径/符号链接；保存诊断归档并逐成员核验SHA256；冻结保留文件哈希与删除清单；删除固定历史目录；核验保留文件、运行进程、源码差异及释放空间。

涉及文件：PLANS.md、本计划、BUILD-CLEANUP-02-2026-11-07报告、旧待清理清单的状态说明；本机忽略的evidence/BUILD-CLEANUP-2026-11-07及辅助脚本。无产品源码、契约、schema、依赖或Git历史变动，不为纯产物清理重跑全量应用测试。

验收：17路径均不存在；诊断归档哈希一致；保留文件哈希无变化；运行中的应用未被停止；记录逻辑/分配空间与实际可用空间差值，不能将估算当回收值。真实Windows/科研测试本次不执行。

执行结果：PASS。固定17目录/176文件已删除，89份诊断归档逐成员SHA256一致，25个保留文件SHA256一致，三个原App/侧车进程保持；实际可用空间增加12.376GiB。源码差异哈希不变。详见BUILD-CLEANUP-02报告和本机prepared/result证据。
