# P0 验收矩阵与 GO/NO-GO 规则

**当前状态：P0完整验收BLOCKED；已有Mac局部测试，结果与缺口见[本轮报告](../engineering/reports/P0-implementation-2026-10-24.md)。下表为原始门槛，初始状态列保留历史基线，不是当前执行结果。** 依据 v1.1 §§2.4、3.6、4、7–9、10。用户新增macOS目标见ADR-008，未取消Windows/8GB要求。

用户最新允许延期不阻断开发的测试并继续功能，执行顺序见ADR-009与[延期登记](../engineering/deferred-tests.md)。允许独立P1本地开发；本表仍是最终门禁，延期不等同PASS、不取消正式平台/科研/发布验收。

## 先冻结可运行的环境

测试人员应记录设备品牌/CPU/OS Build/RAM/磁盘剩余、Defender/WebView2 状态、管理员与普通账户、用户名/数据根路径、Python/Rust/Node 是否预装、安装包及 Sidecar SHA256、依赖版本、模型权重 SHA/许可、数据集 Manifest。

| ID | 测试门槛 / 可观察结果 | 必需证据 | 初始状态 | 严重性 |
|---|---|---|---|---|
| G01 | Windows 11 x64 无 Docker/WSL/系统 Python/Node/DB，仅单安装程序完成安装启动卸载（保留数据） | 真正干净 Windows 安装截图/日志、安装器 SHA、进程/端口快照 | NOT EXECUTED | **BLOCKING** |
| G02 | 8GB 与 16GB 机器正常导入、检索、查看来源、重启、恢复 | 双机 OS/硬件/用例原始记录 | NOT EXECUTED | **BLOCKING** |
| G03 | 非管理员 + 中文/空格路径 + 中文用户名（包含侧车/SQLite/模型/PDF 路径） | 路径、任务结果、运行日志/退出码 | NOT EXECUTED | **BLOCKING** |
| G04 | PDF 版本不可变，SHA256 去重、重复导入不重复构建旧索引 | 数据库/文件一致性断言、增量计数 | NOT EXECUTED | **BLOCKING** |
| G05 | 对普通/多栏/表格/扫描/混合/异常 PDF 逐页处理；错误与未解析页不可伪装完成 | Gold Set、解析状态/失败页面、人工核对差异 | NOT EXECUTED | **BLOCKING** |
| G06 | `doc_version/page/source_region` 来源真实存在；坐标不可靠时降级，不假造高亮 | 不同旋转/缩放/PDF 类型人工标注证据及自动测试 | NOT EXECUTED | **BLOCKING** |
| G07 | EmbeddingSpace 版本隔离、旧向量持久复用、重启及新增 10 篇不全量重算 | 模型指纹、Chunk 数/向量数/调用计数、前后快照 | NOT EXECUTED | **BLOCKING** |
| G08 | sqlite-vec vs LanceDB 使用相同向量/距离/过滤/硬件的真实 Windows A/B 试验 | 两份原始 Benchmark + 复现实验说明与 ADR | NOT EXECUTED | **BLOCKING** |
| G09 | 精确 KNN、过滤范围、索引发布/删除正确；无越权文献和不可见/孤儿向量命中 | 基准精确求解结果、范围隔离/删除/对账测试 | NOT EXECUTED | **BLOCKING** |
| G10 | SQLite/向量/文件备份 Manifest 真实可恢复；磁盘满/崩溃/损坏无静默原件丢失 | 故障注入日志、前后文件 SHA/DB integrity check | NOT EXECUTED | **BLOCKING** |
| G11 | 本地 IPC 身份校验，文件访问授权；API Key 不在前端、日志、命令参数；对恶意 PDF 有资源上限 | 攻击/越权测试、日志脱敏、端口监听检查 | NOT EXECUTED | **BLOCKING** |
| G12 | 100/1000/3000 篇建议档规模测试及 16GB CPU 的 FTS/KNN 延迟预算对照 | 真实语料特征、测试脚本、P50/P95 分项指标 | NOT EXECUTED | **MEASUREMENT** |
| G13 | 设计/包依赖、模型和解析库的许可证、来源、运行时 DLL 与再分发条件核对 | 版本锁、SBOM 草稿、NOTICE、权重授权表 | NOT EXECUTED | **BLOCKING** |
| G14 | P0 任务、失败/未测说明及用户验收齐备；未偷跑 P1–P5 | 审查签字、任务报告、Git diff、已知限制 | NOT EXECUTED | **BLOCKING** |

## 关键解释（防止错误通过）

- G01–G03 必须通过**真正无开发依赖 Windows 环境**验证；Windows GitHub Actions runner 只能算辅助证据。
- G05–G06 的解析/定位评估需人工标记的可信金标；单纯有字符串并不代表表格数据归属正确。
- G08 是“完成公平对比并留下结论边界”，不是必须让两个引擎都通过；一个失败可能成为拒绝该候选的证据，但若无法比较则不能假称已选择。
- G12 包含三个建议档：真实库无足够论文时须按缺少样本报告 BLOCKED/NOT EXECUTED；不得填入合成数字冒充科研规模。*1000 篇规模支持*只有该档真实完成后才能对外声称。
- P0 尚不提供完整 P2 混合检索，所以 v1.1 的 `混合检索 P95 ≤ 1s` 应在 P2 复核；P0 仅记录组件耗时与暂定预算。
- G10 的“无静默丢失”不承诺零字节异常后完全自动恢复：不可恢复错误必须报错、阻断发布并保留文件/审计信息；任何原件缺失视为阻断。
- 所有未知质量门槛（金标数量/定位准确率、扫描/表格提取正确率）应先冻结测量方法和业务接受界限，后测，不能“测完再调整分数线”。

## 推荐完整故障注入步骤（每一步保存证据）

1. 创建测试库和 PDF Manifest，登记原件 SHA、SQLite backup ID、向量空间/索引指纹。
2. 分别于文件复制、parse_page、Embedding、向量 upsert、索引可见性发布、备份过程中注入中断/磁盘空间不足。
3. 重启后检查每个 Job 的 `status/lease/attempt_count/error_code` 和入库/可见性一致性。
4. 检查文件 SHA 与 DB FK；用独立样本重新查询并验证来源仍存在；必要时由持久 Embedding 重建索引。
5. 在 LanceDB 候选上检验跨数据库恢复/备份，记录“SQLite 快照与 LanceDB 文件是否同一时点/世代”。
6. 记录丢失、重复向量、孤儿结果、错引、高亮错误、超时、安全拒绝与人工干预的精确数量。

## GO/NO-GO 判定

- `GO`：所有 BLOCKING 项均有相应真实环境/数据下 PASS 证据；MEASUREMENT 项结果与批准的范围和风险一致；批准人签字。
- `CONDITIONAL GO`：仅限非关键残余项，列出限制、补测截止和允许工作范围；不允许把 Windows/来源/持久化/安全核心项豁免。
- `NO-GO`：核心项真实 FAIL，或出现数据丢失、虚假坐标/引用、未授权访问/外发，停止扩张并提交根因报告。
- `BLOCKED`：缺少关键设备、测试文献、权重许可、发布依赖或人工确认时，暂不能给出 GO 结论。

> 决定需由项目负责人/测试负责人审阅；Codex 只能形成**建议**，不能给自己通过门禁。
