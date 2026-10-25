# ADR-008 Windows 与 macOS 双平台开发范围

- 日期：2026-10-24。
- 范围依据：用户在本轮明确提出“调整为windows和macos都兼容”；本轮按该请求增加macOS开发/验证目标。不是Agent自行变更平台需求。
- 状态：双平台实施已获用户请求；具体OS最低版本、Intel Mac和8GB门槛调整仍OPEN，未宣布任何平台验收PASS。
- 对应v1.1 §§1.3、2.4、8.1、9.4：原Windows优先、macOS保留扩展；本ADR仅将macOS扩展提前，不修改核心Tauri/Rust/Python/SQLite架构。

当前目标：Windows11x64与macOS（先当前AppleSilicon），代码/API/数据指纹共用；每个平台分别冻结Sidecar、原生DLL/dylib、安装包、权限与凭据实现、构建/恢复证据。用户已确认当前Mac和另一台Windows电脑均为16GB；当前会话只能执行Mac本地命令，另一台电脑尚无可用执行通道。8GB原门槛未被明确取消，不擅自豁免，记录为未执行/待范围确认。

本机macOS开发与冻结Sidecar可测，不代替干净Windows；Intel Mac、具体macOS最低版本、干净无开发依赖Mac安装/签名/公证未测。应用标识、数据目录与日志保持平台分离；Windows Credential Manager与macOS Keychain在实际需要云密钥的后续阶段分别实现，前端不持有密钥。

回退与兼容：业务数据库/不可变PDF和向量指纹无平台专属身份，不直接假定二进制索引可跨平台复制。优先按Manifest在新目录恢复；暂不迁移旧用户资料。平台不足保留BLOCKED，不把开发机运行转为双平台发布结论。
