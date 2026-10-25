# 历史与文献生命周期实现契约 v0.2

依据v1.1 §§4.5、5.3、6.2、7.3、8.4。增量兼容原/v0接口；schema10新增生命周期状态/不可覆盖修订及历史索引，升级前保留v9快照。

## 历史访问

`GET /v0/history/{answers|research}`：project_id（省略表示全库范围会话）、cursor、limit(1–50，默认30)。返回items/next_cursor/total，只含ID/问题/模式/状态/创建时间等元数据；排序(created_at DESC,id DESC)，游标base64url编码此对并验证时间/UUID。并发新增不会把新记录插进已经开始的旧记录遍历；前页刷新可取得新增。项目过滤在SQLite进行，不能用其他项目的ID获取详情。

`GET /v0/answers/{id}?project_id=…`按ID加载单轮完整记录，近30条以外仍可访问。原GET /v0/answers保留兼容的近期列表。

`GET /v0/research/{id}`：相同project_id，以及paper_offset、observation_offset，返回选定一篇与当前20条观察/证据、全范围覆盖计数、scope_count、paper_list、字段实际总数、下一观察偏移。字段在别页时不能显示为“未提取”。报告列表仅ID/修订/时间，正文由GET /v0/reports/{id}按需取。新GUI不在每次轮询加载所有计划/观察/报告正文。旧GET /v0/research用于兼容与内部报告生成，仍只列近期计划；不是新版GUI分页路径。完整大语料响应/内存与导出性能仍待实测。

模型调用前先保存owner/job/完整fingerprint事件，即使失败也保留；每条model_draft观察另存原模型指纹，恢复可使用另一配置但不改写旧记录的模型来源。人工修改保留指纹。报告与UI显示调用历史/每条抽取指纹，未知历史数据不能补造模型。

局部问答候选使用每篇逻辑论文最多3片段配额，多个PDF版本共用论文配额；最多8片段，来源渠道候选池有界，不表示全库覆盖。Research逐篇扫描不使用该Top-K或配额。

## 手工生命周期与来源失效

`GET /v0/lifecycle`返回本机人工维护的状态/理由/修订/版本/审计。`POST /v0/documents/{paper}/lifecycle`接收expected_revision、state(active|archived|retracted)、非空note；CAS冲突409。retracted表示**用户手工标记，未经出版方验证**，不自动声称某论文确被撤稿。

状态和该论文所有版本的visibility在同一短事务提交，立即退出新检索、新范围与新问答。向量/原件/旧Chunk/证据/报告全部保留，没有物理删除；派生索引变更后要求重建，持久向量可复用。重复导入不会静默激活隐藏版本。恢复只恢复本次停用前的可见性快照，版本集变化需人工核对；历史标记不覆盖。停用后撤销归并会被拒绝，先恢复并核对身份。

历史Evidence来源状态单独显示archived/retracted/unavailable，不能被人工confirmed抵消。原件仍可从设置中的保留版本入口只读核对；这不重新授予其科研证据有效性。模型或解析处理期间发生停用，最终发布重新校验后拒绝迟到结果。

旧ReportRevision.body不可改写。读取报告另返回当前source_warnings（生命周期、解析批次或论文身份变化）；export_body在不可变正文前附明确的“导出时来源状态提示”。Rust创建新文件时使用export_body；UI显示警告，不能把静态旧报告正文当当前有效结论。
