# GH-01：上传当前源码到用户指定仓库

日期：2026-10-25。用户明确要求将代码上传到`https://github.com/maczhouyi-del/RAGTest.git`，因此本次指定仓库的初始化、提交与推送已获授权，覆盖此前仅本地开发的执行限制。其他仓库、Release、安装包分发、用户资料/凭据外发和旧数据操作仍未授权。

已确认目标为maczhouyi-del拥有的公开空仓库，默认分支main；本机已有相同账号GitHub CLI授权，使用该授权，不使用或保存聊天中的密码。账号资料来自对应GitHub连接核对。

范围：项目源码、测试代码、锁文件、构建脚本、设计及契约、许可证和项目文档。修改.gitignore、README.md、PLANS.md及本计划，初始化本地Git并设置指定origin。保留原始AGENTS、设计、迁移和锁文件内容。

排除：.tools、虚拟环境、node_modules、target/dist、冻结二进制/安装包、生成schema、PDF、数据库、运行日志、engineering/evidence、私有样本、机器依赖清单、模型权重与凭据。仅修改忽略规则，所有原文件继续留在本机，不删除。公开PDF保留来源manifest，克隆后按清单另行取得并校验。

验证：先生成待提交清单并检查敏感扩展/路径、符号链接、大文件、疑似真实token/私钥；检查锁和核心源码SHA未改变；git diff --cached --check。代码未变更，不重复运行既有模型和应用功能测试；Windows及科研门禁沿用原状态。推送前复核远端仍为空，正常推送main，不强推、不覆盖既有历史。

验收：远端main的commit与本地HEAD一致，远端文件树与核准上传清单一致；Git状态干净。原始命令、清单及最终报告保存在本机被忽略的`docs/engineering/evidence/GH-01-2026-10-25/`。如远端状态变化，先检查差异，不绕过冲突；如授权失效，保留完成的本地准备，不要求用户发送密码或token。
