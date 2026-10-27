# 本地检索实现子契约 v0.2

2026-10-27当前排名、实际分词版本、内容多样性和问答配额的增量以[retrieval-answer-v0.6.md](retrieval-answer-v0.6.md)为准；以下保留此前实现记录，不把历史候选配置当当前验收结论。

需求v1.1 §§3、4.3–4.5、9；新增策略为可选实验能力，不改变后端/Embedding最终选型。协议仍0.1.0，API`/v0`。向量/模型候选版本不当作已批准性能结论。

`POST /v0/search`：query、authorized_doc_version_ids、k(1–100)、可选project_id、strategy=fts_only|keyword|vector_exact|hybrid。SQLite可见性/项目关联先过滤；不可用范围拒绝，不悄悄扩大到全库。向量结果再关联当前SQLite可见Chunk，拒绝孤儿命中。

完整短语用既有unicode61字面转义；关键词用版本cjk-bigrams-latin-v1，CJK连续段双字、拉丁/其他词段分开，OR候选+FTS5 BM25。清洗文本和来源偏移不改写，新增FTS索引可从当前Chunk回填。不是领域词典、中文分词质量或中英文相关性合格的声明。

Rust选择本机Embedding资源目录，授权purpose=embedding；`POST /v0/index`指定sqlite-vec|lancedb候选、一次性model_grant_id及幂等键。核对已批准固定E5 ONNX/tokenizer资源，CPU本地推理。内容+模型/预处理指纹相同的原向量持久复用，新增内容增量编码；建立新索引世代后核对ID、可见Chunk指纹和任务租约，在同一SQLite事务发布active_index。失败保留旧发布索引和新原向量缓存，不污染旧代。

vector_exact先授权过滤embedding ID后候选精确KNN；重复内容向量可映射到多个当前Chunk。hybrid对词法与向量的候选做RRF(k0=60)，按确定性ID破同分。未接入可选Reranker，不能宣称重排质量。候选上限、向量适配器具体实现和查询Embedding成本见代码/原始测试，Top-K不代表论文级覆盖。

`GET /v0/index`只公开configured/ready/候选名称/当前及索引Chunk数量/世代，不公开模型路径。重解析或缺失派生索引后返回需要重建，已有相同指纹原向量可复用。恢复备份后派生索引重建，不能误认SQLite原向量丢失。

真实样本仍仅两篇29页119Chunk；Mac候选精确对照/重启/增量已测，Windows、100/1000篇与人工检索相关性/性能门槛延期；P95≤1s不宣称达成。未自动选择默认后端。

范围筛选扩展：GUI以当前标签/年份挑选PDF版本，`/v0/search`的可选filters(tag/year_from/year_to)在服务端查当前SQLite元数据，召回前及慢查询后重查；不符返回SCOPE_FILTER_CHANGED，不能默默采用过时筛选。未知年份不进入年份范围。项目和可见性仍独立校验。局部问答候选按逻辑论文每篇最多3片段，总计最多8片段，不用于Research完整覆盖。

可选问答策略keyword_review/hybrid_review：在后台问答任务中，用已批准Qwen候选对最多6条、每条500字符作0–5相关性复核，所有编号必须恰出现一次且分数有界。只改变召回池顺序，不创造引文/科学事实。原排序、新排序、模型完整指纹和理由写入AnswerRun.result；调用前记录模型事件，失败保留任务。默认关闭，真实候选仍给出错误理由，不能声称检索质量提升或已完成专用Reranker最终选型。
