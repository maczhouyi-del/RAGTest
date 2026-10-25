# P0-05C：词级表格输入、质量路由与按页重解析

日期2026-10-25（Asia/Shanghai）。用户已授权连续开发全部功能，原ADR-009补测延期适用；仅使用已批准的E5/Qwen/OCR/Heron/TableFormer资源，不增模型/服务，不最终选择解析器或修改正式验收标准。

依据v1.1 §§3.2–3.5、4.1–4.2、5.3–5.4、6.2、7、9；承接P0-05B。问题：已安装Docling PDFium适配器无word_cells，TableFormer退回整行输入导致列合并。当前仅全篇显式增强；质量路由和单页更新缺失。

实现意图：增加本项目词级PDFium适配（不修改第三方安装源码）；固定预处理指纹，真实BERT/DPR同权重前后对照。新增可关闭的自动候选路由：原生文本/乱码/多栏及表格布局信号→已有OCR/Docling，保留每次尝试/原因/失败/拒绝降级，不把工程阈值当已校准科研标准。新增按页解析，保留未改动页元素/Chunk/表格ID与复核，受影响页才替换。

拟改文件：parsing/pdfium_words.py、docling_backend.py、routing.py、pipeline.py、worker.py、docling.py、tables.py；storage/migrations/0012_parse_publications.sql与database.py；jobs/repository.py恢复对账、storage/backup.py恢复对账、workflows/workbench.py冻结范围、library/repository.py诊断、ipc/server.py；Rust固定parse命令、bridge.ts、DocumentDetails.tsx；相关集成/故障/真实PDF/冻结/浏览器工具；layout-tables子契约、PLANS与本轮报告。

SQLite增加当前页/表格发布指针及revision、解析尝试审计；旧schema升级前OnlineBackup，原始ParseRun/元素不改写。任务入队冻结当前发布revision，启动/发布再核对；短事务切换受影响页，可见性/lease/原件SHA仍必查。空页也必须有页指针，不靠Chunk数推断覆盖。撤稿/归档不泄露旧页；旧表格候选与审查保留，修改页不继承人工确认。

自动路由仅用户选择时启用，原有默认快路径兼容。增强失败或内容映射退化需有明确尝试/页警告；取消/失租不得作为可忽略失败吞掉。未定位对象保留诊断，禁止虚构来源坐标。单页需要已发布基础解析，首次可先全篇快解析。

拟命令：锁定venv Ruff/pytest、真实两篇模型对照、npm build、cargo fmt/clippy/test；源码固定后可选运行时PyInstaller冻结，实际冻结解析/浏览器/原生启动，所有run_logged证据保存continuous-2026-10-25。禁止批量删除或清理旧构建。

验收：数值词不再整行合并（仅样本工程对照，不报告通用正确率）；原件SHA不变，偏移逐格精确，未处理页ID/审查保持，更新页旧引用失效；不连续页/超界/空页/任务重放/取消/失租/并发发布/备份恢复/升级快照；自动路由无资源/增强失败/拒绝结果均显式记录。Windows/8GB/科研金标/准确高亮/千篇性能仍BLOCKED或NOT EXECUTED。

实施补充：全局未定位计数保守保留至全篇重解析；200表/10000格预算约束组合发布；私有attempt保留未被采用的完整有界输出。最新结果见continuous-2026-10-25报告与同名evidence目录。
