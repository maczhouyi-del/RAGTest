# MVP-03 真实兼容 API 验证（2026-10-26）

用户本轮提供指定 HTTPS endpoint 和凭据，明确要求真实测试；这是此前禁止真实调用的本次有限例外。不把此授权扩展到其他服务、用户论文、源码、上传完整PDF、日后自动调用或GitHub。

范围：仅指定cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1，TLS验证/禁止重定向/禁止代理与自动供应商回退保持；先认证与真实模型目录，再选目录中可用的小型通用文本模型；最多6次生成POST，每次沿用900输出token上限。问题为公开BERT预训练任务及后续指代，最多2轮；仅既有许可公开PDF的检索片段、有界上下文和问题。通过既有ProviderRegistry、NetworkProvider、Workbench原科学校验完成，不修改检索或支持性规则。

新建隔离测试工作区，不写用户工作区，不将密钥放入argv、文件、环境变量、SQLite、日志或前端storage。工具通过关闭回显的stdin仅内存交付凭据；脚本只保存脱敏调用摘要、用量、状态、引用和可复核公开证据。失败也保留脱敏日志；目录不可用时停止，不能伪造模型ID/接口成功。

拟改文件：可复用显式触发的tools/test_real_generation_api.py，本计划/PLANS和本次报告。测试命令：engine/.venv/bin/python tools/test_real_generation_api.py --base-url <指定地址>；stdin输入密钥。macOS26.2 arm64/16GB。厂商身份/价格未独立验证，不宣称其为官方服务或保证费用；只据真实响应报告可达/认证/目录/生成/引用/重启/授权。

状态：TEST EXECUTED；目录/认证通过，真实生成FAIL（远端insufficient_quota），多轮/引用BLOCKED。无新依赖/模型/迁移/前端改动，不推送或发布。

真实调用仅1次生成POST后停止。真实服务返回403 quota而现有应用映射AUTH_FAILED，未擅自修改生产代码或计费；见本次真实API报告。
