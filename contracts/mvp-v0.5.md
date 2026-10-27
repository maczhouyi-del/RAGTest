# MVP v0.5 加固增量契约（2026-10-27）

继承mvp-v0.4，SQLite仍schema18，没有迁移。IPC握手0.1.0不变；仅健康诊断api_revision=0.5-local及下述向后兼容增量，旧单文件授权/导入接口保留。

- 模型错误：只从≤16KiB结构化远端错误code/type识别QUOTA_EXCEEDED/AUTH_FAILED/PERMISSION_DENIED/RATE_LIMITED/SERVER_ERROR。未知401/403不根据自由文本猜认证；通用HTTP_ERROR，不清Key。仅AUTH_FAILED清会话Key/验证状态；新码中文提示见bridge.ts。无重试/回退/额外探活。
- restart_engine增加可选force=false：健康运行时复用，健康失败但活着返回ENGINE_HEALTH_FAILED而不杀；退出/缺实例可恢复。force=true仅显式主动重启。并发恢复ENGINE_RECOVERING；启动失败保持不可用可再试。旧键名/本地工作区不改。
- POST /v0/internal/file-grants/batch接收paths（1–32项、每项≤4096字符），一次失败撤销本批未消费授权；请求上限单独使用128KiB以支持中长路径，普通单文件接口仍16KiB。POST .../revoke接收file_grant_ids≤32，幂等，仅撤销池内未消费授权，已消费归任务。原有大小/头/SHA/300秒/32池上限不变。
- GET /v0/backups新增incomplete[]，仅id/kind/state/error_code，无公开路径；失败产物本机journal复核后隔离，不批量删除。备份操作元数据使用app_settings现有键前缀backup-operation:，绑定owner_root，恢复副本不得处理原库journal。旧无标记的完整manifest仍可验证；新有标记者未complete不允许恢复/激活。
- 纯keyword/fts_only读可使用独立上限2读取闸门；重任务闸门仍1；后台metadata单pump。忙请求429 WORKER_BUSY/retriable=true，无隐式无界队列/自动重试。
- health.schema_version来自实际PRAGMA并以字符串返回；components区分engine/database/keyword_search/vector_search/generation/ocr。generation.configured/eligible不等于远端探活，remote_health_checked=false。缺向量/可调用生成配置或数据库异常时degraded，HTTP200仅表示诊断可达，不能当所有功能/科研/发布通过。
- PDF新增几何上限/明确资源错误；环境白名单，不继承任意密钥。CPU/内存/权限/网络能力分别记录，不宣称完整OS沙箱。安全P1门禁见security-baseline。

兼容：旧客户端可以忽略新增字段；新客户端批量授权需匹配0.5侧车，不自动回退旧逐个申请。数据库前后版本没变，回滚源码无需删新app_settings记录；原件/向量/旧会话不删，旧程序的安全缺陷不会因兼容而被宣布已修复。
