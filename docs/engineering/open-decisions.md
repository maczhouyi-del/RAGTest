# P0 待决事项登记簿

所有项目初始OPEN；后续部分实验已执行，仍不自动升级为APPROVED。当前进展见文末，不凭小样本或模型卡指标作选型结论。

| ID | 要回答的问题 | 如何决定 | 当前状态 | 源文 |
|---|---|---|---|---|
| D01 | sqlite-vec 还是 LanceDB？ | 同数据同机 exact KNN、删除/过滤、备份/恢复、中文 Windows 打包及维护风险 | OPEN | §§3.3、3.6 |
| D02 | 何时从 PDFium 升级 Docling/OCR？ | 真实 PDF 逐页金标；质量信号、阈值、资源/体积/许可证，确认有效改进 | OPEN | §§4.1–4.2 |
| D03 | 本地 Embedding 模型/维度/距离/许可？ | 中文↔英文检索、CPU、模型大小、下载许可、完整模型指纹 | OPEN | §§3.1–3.2、4.4 |
| D04 | 本地 IPC 如何保证身份与文件授权？ | 命名管道 ACL vs 随机回环端口+短会话 token，安全与打包实测 | OPEN | §§2.3、8.3 |
| D05 | exact KNN 是否足够，是否需要 ANN？ | 真实 1000 文献的 P95 和 recall/过滤，必要时单独评估 ANN 召回损失 | OPEN | §§3.6、9.5 |
| D06 | `SourceAnchor` 坐标系怎样跨 PDFium/PDF.js 统一？ | 旋转、CropBox、双栏、表格、OCR 的逐页验证 | OPEN | §§4.2、6.2 |
| D07 | 真实 Gold Set、论文库和设备从哪里来？ | 数据授权与代表性、8/16GB Win11 测试、注释者和文献许可清单 | OPEN | §§9.2–9.4 |
| D08 | 是否单独打包 Docling/OCR 资源？ | 下载授权、离线能力、体积/速度和清洁安装限制 | OPEN | §§2.4、4.4、8.1 |
| D09 | 论文/版本与哈希去重唯一约束如何定？ | PDF SHA 去重、同一论文不同版本、多个项目、多 FileAsset 设计实验 | OPEN | §§3.1–3.4 |
| D10 | 源锚置信度定义与金标阈值？ | 逐页人工标注和 fallback，防止无效坐标导致虚假精确高亮 | OPEN | §§4.2、6.2、9.3 |

**补充说明（本包新引入的工程问题，不是 v1.1 已经决定的结果）：** D06 的规范化坐标方式、草拟 JSON schema、P0 Sidecar OpenAPI 请求字段、某些状态码与跨文件原子性处理方式都需要实现前审查批准。

审批记录格式：`ID / 决议 / 技术或金标证据位置 / 批准人 / 日期 / 替代文件及字段 / 旧方案回退点`。

## 2026-10-24 P0-00历史提案索引

所有D01—D10继续OPEN；以下均PROPOSED，**无用户批准、无实测选型结论**。不替代现有契约或需求。

| 事项 | 提案 | 尚缺证据/确认 |
|---|---|---|
| D01/D09后端及复用关联 | [ADR-001](../architecture/adr/ADR-001-vector-backend.md) | 同机A/B、恢复、锁版与唯一约束 |
| D06/D10坐标/offset | [ADR-002](../architecture/adr/ADR-002-source-anchor.md) | 原生几何、字符单位与真实页校准 |
| D04 IPC/FileGrant | [ADR-003](../architecture/adr/ADR-003-sidecar-ipc.md) | 用户选实验路线、签发/撤销/握手与Windows拒绝测试 |
| D03/D08模型及许可 | [ADR-004](../architecture/adr/ADR-004-model-license.md) | 具体模型/权重许可、完整指纹、下载授权与CPU实测 |
| D07/D10语料/设备/金标 | [ADR-005](../architecture/adr/ADR-005-corpus-goldset.md) | Windows与标注负责人、真实PDF哈希和代表性 |
| D05/D10门槛及P0范围 | [ADR-006](../architecture/adr/ADR-006-performance-gates.md) | 先注册正式合格线；确认§10.4问答和纯本地自动化范围 |
| D02/D08解析质量路由 | [ADR-007](../architecture/adr/ADR-007-parsing-route.md) | 逐页金标、增强前后收益、资源许可和授权 |

P0-02开工前须另冻结Document/Version/FileAsset唯一性、Job API投影与状态机；上表ADR-001只覆盖向量复用部分，未替代D09完整数据子契约。目录RAGSystem/RAGSystem2名称差异、缺.gitignore和源文范围差异见[P0-00报告](reports/P0-00-2026-10-24.md)。

## 后续开发证据更新

| 事项 | 已有新证据 | 仍未决定/验证 |
|---|---|---|
| D01/D05 | Mac两篇119个384维向量；sqlite-vec0.1.9/LanceDB0.40.0相同数据/过滤/查询，独立oracle对照通过 | Windows共同打包、100/1000篇与内存；无最终后端或ANN结论 |
| D02/D06/D10 | 真实BERT/DPR29页，无损codepoint offset、页级anchor、hash/版本校验；无bbox | 表格/多栏阅读序/科学符号人工金标、旋转/CropBox校准、OCR阈值，仍OPEN |
| D03 | 用户已批准固定revision的intfloat/multilingual-e5-small本地试验；已校验hash并CPU推理，完整指纹持久 | 下载批准不等于最终模型/科研质量/发行批准，选型OPEN |
| D04 | 随机回环+会话token实验实现、Rust环境允许名单、鉴权/Origin/正文上限/EOF测试 | Windows边界/OS级隔离/同用户攻击模型、正式协议冻结仍待审；不是Agent批准ADR |
| D07 | 用户确认Mac与另一Windows电脑均16GB；两篇CC-BY样本已本地 | Windows执行通道/干净环境、8GB、代表性规模/金标缺失 |
| D08 | OCR固定两语言候选已获批准、校验并接入，真实/冻结/Rust链路通过；Docling两候选已独立批准、下载/校验/接入，BERT/DPR真实结构候选有列合并/跨页问题，科研质量未通过 | OCR字符/中文/科学符号与版面表格金标、Windows/资源与最终选型仍OPEN |
| D09 | 实验migration：SHA唯一FileAsset/DocumentVersion；完整Job内部实体与无秘密投影分开，见实际子契约 | P1逻辑论文/多版本/项目、人工归并与撤销/批注、schema10生命周期/schema11表格结构均已实现并回归；最终业务规则/科研验收仍未签字 |

[ADR-008](../architecture/adr/ADR-008-platform-targets.md)记录用户要求增加macOS目标。具体最低OS/Intel/8GB范围与双平台验收仍OPEN。原ADR-001—007保持PROPOSED/OPEN；用户广泛开发授权允许候选实施，不是对最终技术选型的验收签字。

当前完整工程状态以continuous-2026-10-24报告与PLANS§11–12为准；历史P0小样本/旧任务状态不作为当前功能缺口清单。已批准Qwen另有真实问答/Research/相关性复核试验，仍出现错误理由和自审，不做科学质量或最终模型选择结论。
