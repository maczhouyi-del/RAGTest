# P1 文献基础子契约 0.1.0

日期：2026-10-24。依据v1.1 §§3.4、5、7、10.1；实施顺序例外ADR-009。此文档补充implementation-v0.1，不改写P0历史记录或宣称P1整阶段通过。新增API向后兼容旧客户端；当前桌面端要求随包引擎有`projects/manual_metadata/pdf_reader`能力，不能与旧二进制随意混搭。启动协议仍0.1.0；SQLite schema由3升级4，旧程序拒绝读高版本。

## 项目和文献身份

Project(id/name/name_key/created_at)，名字strip后1—100字符，NFKC+casefold唯一。项目与逻辑Document多对多；关联以(project_id,document_id)为主键，linked=0软撤销，无文件或记录删除。重复关联幂等，项目计数只含仍有可见版本的Document。项目是同一用户工作区的整理/查询子集，非多租户隔离身份。

同SHA文件仍复用原DocumentVersion/Document，关联项目不复制PDF/Chunk/向量；导入任务意图可携带project_id，Document/项目关联与Job完成同一短事务提交，恢复沿用该意图。不同SHA不会因人工填写相同DOI自动合并。完整题名/作者匹配、人工论文合并、多个PDF版本管理尚待后续P1任务。

## 手工元数据

Document的title仍为展示标题；新document_metadata表保存authors/year/doi/venue/tags/revision/origin=manual/updated_at。旧文献无元数据行时revision=0。首次保存revision=1，每次保存要求expected_revision等于当前值，否则409 METADATA_CONFLICT且不部分写入；title与元数据同一事务。

题名1—1000字符，作者最多100位/每位200字符，年份可空（1000—2999仅格式范围，不证明年份真实），DOI可空，期刊500字符，标签最多30个/每个200字符。DOI去doi:/doi.org前缀后小写、校验10.数字/非空后缀。原始PDF不改；人工字段不进入页文本FTS、不触发解析/Embedding，不作为模型证据。重复DOI仅返回当前可见文献ID候选，由研究者核对。

## 固定API

沿用会话鉴权、Host/Origin/16KiB正文限制，API错误不反射字段内容或路径。

| 方法/路径 | 请求与响应 |
|---|---|
| GET /v0/projects | projects数组：id/name/created_at/document_count |
| POST /v0/projects | {name}；201项目；同名409 PROJECT_NAME_EXISTS |
| POST /v0/projects/{project}/documents/{document} | {linked:boolean}；200关联状态；不存在/隐藏Document或项目拒绝 |
| GET /v0/documents?project_id=可选 | 保留旧字段，增加authors/year/doi/venue/tags/metadata_revision/metadata_origin/project_ids/duplicate_candidates；无project_id仍全工作区 |
| POST /v0/documents/{document}/metadata | expected_revision/title/authors/year/doi/venue/tags的完整替换；200更新后的文献投影；400非法输入、409冲突 |
| POST /v0/imports | 原请求新增可空project_id，未提供保持旧语义；幂等键同时绑定原grant和项目，重复键换项目409 |
| GET /v0/documents/{version}/file | 可见文献版本的doc_version_id/file_sha256/title/size_bytes；检查原件hash/大小；无文件路径、无SourceAnchor |
| POST /v0/search | 原请求新增可空project_id；同一个SQLite读快照内核对可见版本/项目关联再FTS Top-K；不属于该项目409 SCOPE_NOT_AVAILABLE |

Rust命令新增create_project(name)、set_project_document(projectId,documentId,linked)、update_document_metadata(documentId,metadata)、read_document(versionId)。choose_pdf_and_import/search_sources新增可空projectId，workspace_snapshot新增projects。所有路由ID先验证，路径来自原生选择器/配置或服务端hash，JS不提供任意读文件路径，不持有token。PDF读取复核SHA/64MiB上限并拒绝符号链接。

## 阅读器与范围更新

原件阅读不依赖ParseRun，返回document描述+PDF字节；不可伪造source_anchor_id。来源打开返回已有SourceAnchor+PDF字节，原始来源页保持单独标签，翻到其他页时显示当前页，不假装新的引用定位。页号从1开始，导航由PDF.js实际页数约束；缩放75%—200%，渲染上限6M像素，无XFA/远程URL/执行PDF动作。

项目切换时清空上个项目的检索结果/阅读窗；已解析版本集合变化也清空旧结果并拒绝迟到请求覆盖当前范围。本地表格筛选只匹配人工题名/作者/DOI/标签，不冒充全文或语义检索。来源仍只按页定位，没有新bbox/科学支持结论。

## 迁移/恢复

仅加表/索引，不更改旧migration/原文件/Chunk/向量ID。升级前OnlineBackup到migration-backups，migration事务失败回滚；通过v3夹具验证备份版本及旧记录保留。备份恢复自动包含新表，恢复到新目录。降级时保留新库并在新目录恢复旧备份，禁止直接下调user_version或覆盖正在使用的库。
