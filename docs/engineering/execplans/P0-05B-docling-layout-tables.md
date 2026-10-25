# P0-05B / P1–P4 Docling布局与表格候选接入

用户明确批准官方Layout Heron revision8f39ad3c0b4c58e9c2d2c84a38465abf757272d8和TableFormer fast revision2199320848bb9a8a519d22e4b528185a4f9a6f64（约317MB）及项目内Docling/PyTorch依赖。候选实施授权，不是最终选型/科研/发布批准；现有OCR授权不需重问。

需求v1.1 §§3.2–3.5、4.1–4.2、5.3–5.4、6.2–6.3、7.2、9。目标：原生授权目录配置→离线隔离worker候选→复杂页/表格显式增强解析；结构化表格保留行列、表头/单位/实验条件与原始文本/位置/指纹，页面文本与Chunk仍能追溯原件。未校准坐标不生成高亮，不把模型表结构当人工确认。

实施前固定文件/公开许可，下载后核对仓库LFS SHA（经镜像取得，直接官方HF TLS失败并保留来源限制）及小配置Git blob；只写本项目.tools，保存模型登记。选最小可选Docling/PyTorch依赖，不拉取未授权其他模型；HF/Transformers离线、显式本地路径、关闭OCR/图片/公式/远程增强等隐式模型。使用已有固定受监管worker，不增常驻服务/前端文件路径或Key。

拟改：engine/pyproject.toml、uv.lock、parsing/docling.py及worker/process/pipeline、SQLite增量表格/结构存储迁移（先保留旧schema快照）、IPC目录授权和严格端点；Rust固定命令、bridge/设置/文献详情/表格核对及Research来源；packaging可选运行时；tests/integration和真实BERT/DPR表格试验；契约/资源许可/报告/PLANS。先查实际API/锁兼容，不修改既有解析模型/向量后端最终决策。

失败与资源：限定页数、像素、输出、CPU/墙钟和内存预算，取消/失租终止确切worker，新ParseRun完成事务后才替换旧文本。失败保留旧解析/原PDF、诊断与错误。若复杂表格或定位不可信，保留缺口/不确定状态；不静默平铺表格掩盖列错位。

验收：固定资源/哈希及来源限制；真实已许可BERT/DPR含表页解析与结构；原件不变/版本ID/表格ID/行列字段可回溯；表格核对UI/引用、重启恢复/备份/取消/坏输出、边界注入；全量Python、TS/Rust/冻结/浏览器/原生启动。科学表格正确率、双平台/低内存/千篇容量仍分别BLOCKED/NOT EXECUTED，不以结构化JSON通过替代。

实际实施：parsing/docling.py / tables.py、schema11、worker/process/pipeline、受控配置端点及Rust命令、ModelSettings/DocumentDetails/TableCandidates/EvidenceCard已接入。完整表格与复核审计纳入备份，引用关联实际单元格偏移；跨页分区不合法的内容保留原对象、拒绝伪页码并标partial。没有自动质量路由或单页增强；仍为显式候选。

截至本次增量，源环境与初次冻结BERT/DPR分别产生8/7个表格候选，均partial，已观察多列合并。工程回归105项Python通过、显式Rust候选6项通过；最终源码一致性冻结/浏览器全流程/原生包均已PASS，详情及范围限制写入continuous报告。并发冻结加载触发120秒上限的真实失败保留，需在最终产物单独复测；不能据此作时延承诺。原始模型及打包失败/修复日志均保留。
