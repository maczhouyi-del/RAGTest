# 审查整改与候选发行准备

授权：2026-11-08用户明确要求核实RAG-AUD-01至18、修复与验证，并准备可重复构建的候选安装包；仅独立分支本地提交，不push/Release/付费API/真实用户库操作。

基线：main/00f8f6bc，与报告一致；已有清理文档、PLANS改动和未跟踪audit输入全部保留。工作分支codex/audit-remediation-20261108。本次不将既有清理文档变更混入本地提交。

顺序：先基线和逐项台账；A恢复身份/坏对象隔离/配置槽释放；B任务取消、重启恢复和冻结准备范围、前端错误契约；C按测量优化查询/校验/Embedding及容量预检；D意图与评估；E供应链、资源、安装和平台验收。依赖审计从第一阶段开始。未执行项保持待核查，缺外部平台/标注等列阻塞，不自行延期。

A涉及ingestion/import_pdf.py、jobs/repository.py、ipc/server.py、对应新集成测试。风险：对象异常不能掩盖DB全局故障，恢复不能将B内容认作A，领取/失败持久化异常都必须释放一次槽位且不盗用运行租约。

命令：实际锁定环境engine/.venv的pytest/Ruff，npm build --emptyOutDir=false，现有Cargo锁定测试，run_logged保存平台/退出码/日志；临时工作区故障注入；dependency_gate仅发送公共包坐标，不发送源码/用户资料。完整模型/冻结/浏览器/安装按实际环境单列。不得把既有通过记录当作本轮执行。

候选范围沿用Windows11x64与macOS ARM64；明确应用/推理运行时/Embedding/可选GGUF/OCR/布局资源。REL独立登记签名、公证、许可、干净账户、首次资源配置、升级卸载等发行缺口。未完成实机/人工金标/千篇时不能称正式发行完成。

恢复入口：docs/engineering/audit/remediation-status.md；原始结果docs/engineering/evidence/AUDIT-REMEDIATE-20261108/。每个修复单元记录红绿测试和代码差异，最后更新台账、本地提交及工程报告。
