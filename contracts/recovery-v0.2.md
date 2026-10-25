# 本地备份、任务、身份与批注子契约 v0.2

增量扩展现有v0.1，需求v1.1 §§3.4–3.5、5、7、8。后台单工作槽共用于导入/解析/索引/恢复/模型任务，冲突返回WORKER_BUSY。IPC会话、Host/Origin沿用；普通正文16KiB，仅search/answers/research/document-merges范围请求上限128KiB以容纳1000个版本UUID；stdin握手仍16KiB。旧客户端请求仍兼容，health新增api_revision=0.2-local；前端没有私有路径/凭据/SQL入口。

`POST /v0/import-batches`接受1–32个唯一一次性PDF授权ID，native多选先逐份授权；每份有独立幂等键、项目导入意图、失败/取消/重试状态。内容SHA重复继续复用原件，同文件导入多个项目不复制原件。原选择路径不能充当重试权限；仅已完整保存对象可恢复，否则重新选择。

`POST /v0/jobs/{id}/retry`当前支持import/parse_page，保留attempt_count/上限与事件，不自动清零。备份/模型须重新授权目录，Research在计划内继续。工作区独占锁文件不删除，Unix flock/Windows msvcrt分支；Windows尚未实测。

Rust原生目录选择向`POST /v0/internal/directory-grants`发purpose=backup_parent|snapshot|restore_parent|embedding|generator的300秒、一次性授权；拒绝符号链接/junction/UNC，执行前复核目录identity。前端仅持ID。

`POST /v0/backups`：parent_grant_id、可选source_grant_id、幂等键。省略source创建全新备份目录；指定snapshot恢复至**全新**ragsystem-restored-UUID工作区。SQLite OnlineBackup和不可变PDF逐文件hash，只有全部验证后发布manifest/完成标志；失败保留中间文件，不删除、不覆盖现库。检查文件清单、路径、大小、SHA、SQLite integrity/FK/schema/可见PDF。限制manifest4MiB、1万文件、PDF64MiB/文件、DB512MiB、总8GiB，超限明确拒绝。

备份保留SQLite、PDF和SQLite中的持久原向量/项目/问答/研究/复核/报告，派生向量索引不当权威；恢复后重新构建并复用原向量。快照任务租约全部隔离，不能把复制的running任务当仍运行。记录表只公开摘要，不公开备份路径；Rust切换时再次校验完成标志和来源，当前无活动任务方可切换。先启动新侧车，再原子保存工作区偏好，失败保留旧工作区；不删除旧目录。

`POST /v0/document-merges`须源/目标文献及当前version ID完整清单；必须在UI人工核对勾选，绝不因DOI候选自动合并。仅本工程新资料库内将文件版本归到目标实体，继承项目关联；PDF/版本/Chunk/来源ID和被归并实体元数据均保留。记录before/after及撤销历史；`POST /v0/document-merges/{id}/undo`只有后置版本/项目快照未被后续修改才可撤销，否则IDENTITY_CONFLICT，不覆盖后续工作。

`GET/POST /v0/documents/{version}/annotations`：独立人工笔记，按PDF版本/真实页码保存，CAS与所有修订持久；真实页数由受限PDF子进程确认，若带SourceAnchor必须同页同版本。笔记不会入Chunk/证据池；没有虚构坐标或文本高亮。

SQLite schema5–9新增备份记录、索引设置、范围/会话/证据/研究、复核/批注历史、归并记录；迁移前保留OnlineBackup，事务失败回滚，旧程序拒绝更高版本。没有导入/迁移旧RAGSystem工程数据。
