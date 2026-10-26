# MVP-03 DeepSeek Flash 真实验证（2026-10-26）

基线main a06e7dd，用户本轮提供新凭据并指定DeepSeek官方Flash真实测试；只授权https://api.deepseek.com/v1，不能给上次第三方域名发送新Key。先核对官方模型命名与认证目录，再用实际目录的deepseek-flash执行既有BERT测试。沿用每次最多6次生成POST/900输出token、公开必要片段/有界历史、Key仅内存和隔离工作区；不得上传完整PDF、用户论文、源码，不能自动换供应商/模型、充值/改账户设置、push/publish。

实现意图：优先不改生产代码，运行tools/test_real_generation_api.py --base-url https://api.deepseek.com/v1 --model deepseek-flash，通过关闭回显的stdin输入Key。记录真实认证/模型目录、带引用问答与多轮、支持性/授权与持久化检查；失败保留脱敏结果。涉及协议确不兼容则核对官方原文和实际响应，按授权测试边界处理，不放宽科研校验或冒充PASS。

对应mvp-v0.4/ADR-011；本地macOS26.2 arm64/16GB。仅本计划、PLANS、测试记录及报告为预期变更，无新增依赖/模型/迁移。状态TEST EXECUTED：真实API协议/首轮引用成功，多轮持久化与授权通过；第二轮支持不足拒答，总脚本exit1保留。正式原生/Windows/科研门禁不变。
