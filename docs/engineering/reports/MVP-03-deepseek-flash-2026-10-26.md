# MVP-03 DeepSeek官方Flash真实测试

- Task ID / 阶段：MVP-03 real API / DeepSeek Flash，2026-10-26。
- 基线：本地main a06e7dd，工作树开工干净。平台macOS26.2 arm64/M4/16GB。
- 授权：用户提供新密钥并明确指定DeepSeek官方Flash测试。本轮只给https://api.deepseek.com发送新凭据；没有使用上轮第三方地址。发送范围沿用公开BERT测试问题、每轮少量检索片段和最多3轮有界上下文，不上传完整PDF/用户论文/源码。
- 实际修改文件：本计划、PLANS、本报告及既有组合报告的后续说明；无生产源码、测试脚本、迁移、依赖、模型或安装包变更。仅测试结果和文档本地提交，不push/publish。
- 对应契约：mvp-v0.4、ADR-011，已有GenerationProvider/NetworkProvider/ProviderRegistry和Workbench流程；没有修改来源或科学支持性标准。

官方资料核对：

- [DeepSeek官方快速开始](https://api-docs.deepseek.com/)列出api.deepseek.com与deepseek-flash模型名。
- [官方模型目录接口](https://api-docs.deepseek.com/api/list-models/)规定通过GET /models获取当前可用模型。
- [官方思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)说明默认开启；本轮沿用应用默认请求，不另外注入参数或变更思考预算。

实际接口为https://api.deepseek.com/v1；GET /models返回HTTP200和deepseek-flash、deepseek-v4-pro。按用户指定选deepseek-flash，未调用Pro或其他服务。模型目录与响应只证明服务声明，不独立证明底层权重版本。

## 实际结果

| 检查 | 结果与边界 |
|---|---|
| 认证/模型目录 | PASS，实际官方地址HTTP200，2个模型，Flash在目录内 |
| 配置级保存启用 | PASS，隔离测试库保存非敏感配置/授权；Key只在进程内存 |
| 生成协议/JSON | PASS，4次POST均HTTP200且finish_reason=stop，json_object/max_tokens=900可用 |
| 第一轮带引用回答 | PASS，completed；回答“BERT uses two unsupervised pre-training tasks: Masked LM (MLM) and NSP.”；来源真实性verified，模型支持检查supported；人工审查仍unreviewed |
| 第一轮引用 | 2条回答引用，定位公开BERT PDF第4和8页；另有3条检索候选，共5条evidence记录，不混称5条独立回答引用；原件SHA/页号/来源ID复核通过 |
| 第二轮连续上下文 | PASS，同一conversation_id，发送最近1轮有界问题/回答上下文，重新执行当前问题的真实检索 |
| 第二轮回答验收 | FAIL/拒答，INSUFFICIENT_EVIDENCE；生成了候选草稿，模型支持检查uncertain，没有发布为已支持结论 |
| 第二轮原因 | 当前检索片段没有充分覆盖两个任务的定义与差异；模型候选把“No NSP”消融与两个任务混在一起，支持检查未认可。保留原文和失败记录，不改排序/Chunk/校验来制造成功 |
| 关闭授权 | PASS，后端在网络前拒绝旧allow_external=true，未额外调用 |
| 凭据与授权 | PASS，Registry新实例没有Key/can_answer=false，非敏感授权保留；本轮没有做完整引擎进程重启 |
| 本地持久化复核 | PASS，独立进程重新打开隔离SQLite，1会话/2轮，来源原件SHA/页号一致，integrity_check=ok/FK无错误 |
| 原生桌面界面 | NOT EXECUTED，使用真实Python引擎业务流程；没有宣称原生设置页点击/文件对话框通过 |

仅使用已列入项目许可清单的公开tests/fixtures/public/N19-1423.pdf。第一轮发送3片段共1141字符，第二轮3片段共1070字符；支持检查另发送相关候选结论及原文证据。没有全文上传、Embedding重算或用户工作区改动。未向应用当前用户工作区自动保存该连接或凭据。

调用总量：1次GET模型列表，4次POST（2次回答生成+2次支持性检查）。服务返回用量合计input/prompt=1973、output/completion=1568、total=3541 token；completion中reasoning_tokens=1271（包含关系，不额外相加）。没有读取账户账单或独立核算实际费用，不把估价当实扣金额。四次POST累计测得11.748秒，仅单次小样本调用记录，不是性能SLA。

## 命令、退出码与证据

命令：engine/.venv/bin/python tools/test_real_generation_api.py --base-url https://api.deepseek.com/v1 --model deepseek-flash。密钥通过getpass关闭回显的stdin传入，不在argv/环境变量/源码/SQLite/日志里。实际脚本退出码1：脚本要求两轮均completed，第二轮拒答导致cited_generation=FAIL，**原始失败结果保留，没有把总验收改为PASS**。

证据目录：docs/engineering/evidence/MVP-03-2026-10-26/。

- real-api-20261026T131213232584Z.json：真实模型目录、每次HTTP/usage/时长、两轮answer_run、支持检查理由和来源记录；script status=FAIL。
- deepseek-flash-20261026-summary.json：独立来源/持久化复核、页号、调用token汇总；明确api_protocol=PASS与all_turns_cited_completion=FAIL，均对应原始记录。
- 测试命令退出码1；独立只读SQLite/来源复核命令退出码0。没有为文档更新重跑付费调用或无关全套回归；生产代码没有变更。

功能测试：真实官方API认证/目录/结构化生成PASS；首轮引用问答PASS；两轮都成功回答FAIL；多轮上下文/本地持久化/授权安全PASS。真实Windows安装NOT EXECUTED；原生桌面本轮NOT EXECUTED；科研质量金标NOT EVALUATED，模型自审不代表人工科研结论。

当前可确认DeepSeek Flash可调用；仍有现有检索覆盖/片段完整性问题影响追问回答，本轮不优化。建议用户本机设置用DeepSeek、https://api.deepseek.com/v1、目录返回的deepseek-flash，输入Key并保存启用；重启需重输Key。正式人工操作和科研质量验收另行执行。本次测试授权不等于今后无限付费调用授权。
