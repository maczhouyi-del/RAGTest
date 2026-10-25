# P1-05 / P3–P4 历史访问与文献生命周期

授权依据：用户连续开发全部功能，不重复逐项暂停。需求v1.1 §§4.5、5.3、6.2、7.3、8.4。只在当前工程数据库增量迁移，不访问旧项目，不删除文件。

用户结果：近30项以外的问答和研究可按游标继续访问；研究只加载选定计划的有限篇目/证据，报告正文按需加载。撤稿/停用由用户显式操作并记录原因/修订，立即退出新检索/新范围，旧证据/报告显示失效状态；允许恢复但不默默抹去撤稿历史。普通阅读仍可核对保留的原件，不提供物理删除。

影响文件：storage/migrations/0010_document_lifecycle.sql、database.py；library/lifecycle.py、repository.py；workflows/workbench.py/history.py、ipc/server.py；Rust固定命令与bridge.ts、ResearchWorkbench.tsx、LifecycleSettings.tsx/App.tsx；integration历史/生命周期/恢复测试；contracts/history-lifecycle-v0.2.md；README/PLANS/本轮报告。OCR真实/冻结/原生候选验证继续，不与历史功能混作科研质量。

设计：SQLite仍唯一权威，生命周期CAS/审计与版本visibility在短事务同步；恢复只恢复停用前可见版本。向量缓存保留，所有检索仍以当前可见SQLite关联过滤。迁移前保留v9备份。历史采用(created_at,id)稳定排序/游标，验证scope项目，列表仅必要元数据；详细问答独立取，Research篇目与Evidence按页取，旧API保留兼容但新UI使用分页。旧报告body不可改，读取/导出另附当前失效来源提示。

验证：同时间戳游标/插入不重不漏、项目隔离、非法游标/大小、历史详情、研究按页范围/计数/报告加载；真实PDF撤稿后所有检索/问答发布失败、原件hash和审计保留、CAS冲突、恢复与向量复用；TS/Rust/冻结引擎与浏览器流程。Windows/千篇规模与科研金标另列BLOCKED，功能测试失败先修复后继续。

本地实现和回归已执行：schema9→10升级快照、同时间戳/并发新增历史遍历、单篇观察分页、手工生命周期/恢复/历史报告警告、并发撤销发布通过；浏览器36计划历史与人工撤稿/恢复、保留PDF核对通过。最终结果统一见continuous报告，不自批正式阶段。
