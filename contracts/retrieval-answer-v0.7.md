# API问答全链路增量契约 v0.7（RAG-02，2026-10-28）

继承v0.6；本轮用户授权本地全链路检查/优化及企业、GitHub项目对照。SQLite schema18、IPC握手0.1.0、`/v0`与health.api_revision不变，无迁移/模型下载/新依赖。旧客户端可忽略新增结果字段，历史记录、原文偏移及人工审查保留。

## 输入、意图和查询构造

系统问法仍由引擎精确清单确定。复合问题保留非系统子句内部的标点、and、并行/合并/并发等科研词；仅删除独立完整系统子句及其连接词。不能可靠拆出的问法完整交给论文链路，不静默删改内容。纯系统0检索/推理/论文引用仍有效。

历史上下文现在要求项目、版本集合、逻辑论文身份、PDF SHA及解析批次均与本轮相同。范围切换中断指代链，不跳过新范围去寻找更早的旧范围问题。1600字符/最近最多3轮缓存、只补最多2轮的问题和“历史不是证据”规则保留。`Is it possible…`、`Would it be possible…`等非指代it不触发历史补全。

`context_policy.version=current-question-first-v3-scope`，保存strategy、实际retrieval_query及预算。该步骤是确定性查询构造，没有LLM同义改写、翻译、HyDE或多查询生成调用，不把历史拼接称为独立LLM改写。E5前缀/512-token拒绝溢出/指纹不变，查询超限仍明确失败。

## 词法召回与融合

无显式引号的keyword继续OR/BM25。对最多3个、每个2–200字符的英文双引号或中文引号短语，先用安全转义的FTS词元短语查询（多短语AND），再用既有OR结果补足；按Chunk ID去重。引号内重复词保留位置；索引/CJK分词版本不变，不重解析/重算向量。

`lexical_stage=quoted_phrase|or|literal`、`lexical_stage_rank`记录各阶段BM25原排名；`lexical_rank`是该词法通道合并后的1-based排名。FTS短语按分词位置匹配，不是逐字符引文核验。RRF继续`Σ1/(60+rank_i)`，不得把BM25、距离、RRF或模型0–5意见作为校准概率。每路问答候选50、默认最终8/每篇3保持。

## 可选本地重排与最终上下文

只有显式keyword_review/hybrid_review使用此实验；普通策略和GUI默认不触发。引擎内部取回未截断的融合候选，以原本最终上下文≤8为种子，优先补入不同内容，组成最多12条的池。原有上下文候选不会因扩池丢失。模型每批≤6条、每条≤500字符，最多2批，不调用网络Provider；每批编号完整且唯一、整数0–5校验，任何一批失败整轮不发布。

排序后再执行最终≤8/每逻辑论文默认3；内容关联继续保留。结果记录policy=bounded-local-relevance-v2-batched、每批编号、原上下文、扩展池、全池排序及最终上下文ID。**跨批分数尚未校准，位置偏差/增益未经金标验证**；不能以工程测试通过建议默认开启。直接调用review_order的旧默认6条保留兼容；此段替代v0.6仅一批6条的Workbench实验预算。

离线compare_retrieval的review策略共享上述池/批次逻辑，但评估最终为Top10且无论文配额，以便与其他策略同口径评分；应用上下文Top8/论文配额须另验。未标注数据只测执行与耗时，不计算质量分数。

## API输入与来源边界

API模型不读取本地SQLite或PDF文件，应用先完成本地检索，再向已保存且已授权的Provider发送当前问题、有界同范围历史及编号原文。回答先返回结构化claims/citation_id，再由Python还原引文；每条Claim另调用同一生成模型作支持性辅助判断。摘录/纯系统/无命中不调用回答模型；普通生成通常为1次回答加每条Claim 1次支持检查，应用仍强制最多6条Claim，不能把调用尝试计数当计费次数。

本地/网络生成共用numbered_excerpts：仅包含citation_id、原文前≤1200字符、original_characters/included_characters/is_partial及可选source。source白名单为本轮P/V分组标签、保存题名（≤300字符，截取有标志）、已核对页码。P/V仅是本轮标签；题名是冻结的资料库元数据，不是独立核实的科学事实。回答请求的编号excerpts不含内部Chunk ID、路径、凭据或source中的其他键；支持检查的evidence沿用本轮chunk_id/quote格式（不含文件路径或凭据）。真实引用仍必须逐字符匹配本轮有效原文，不能由模型改写引文。

`context_metadata`保存应用实际included/dropped ID、excerpt_lengths、excerpt_policy及接口usage（若存在且为非负整数）。缺失usage保持null，不推断Token数或账单。模型引用只能属于实际included且确实送出的原文前缀；旧无细分输入清单的生成Fixture/历史仍按本轮池兼容，不能声称其输入审计完整。

首次推理前核验原件SHA/Chunk映射。每次推理与网络请求入口、响应读取期间继续核对租约、Provider授权及当前冻结范围；回答与支持检查之间来源撤稿、解析变化、项目解除等会阻止后续调用，最终短事务再次复查。已在有效授权下发出的请求不能被事后撤回；取消/撤权后停止进一步处理和发布。

本地提示版本v12-sources，旧v9/v10/v11仅提示字段兼容升级，权重/运行时/其它指纹仍必须相同；网络提示v4-sources。提示变化不会更换Embedding空间。模型支持检查仍是同模型意见，不等同独立事实、冲突检测或人工审查。

## 阶段诊断

`result.pipeline_trace`：version=answer-pipeline-v1、stages[{stage,status,input_count?,output_count?,elapsed_ms}]、model_attempts{answer,support,relevance}及elapsed_ms。失败保留已执行阶段，失败阶段标failed；未执行模型尝试为0。计时自任务领取后开始，不含排队、UI传输及最终提交收尾，不是完整端到端SLA。尝试计数包含调用前失败，不能当成功HTTP请求或账单。

`retrieval.timings_ms`包含实际执行的scope/lexical/model-ready/query-embedding/vector/source-mapping/fusion/context-selection/total子项；未执行通道不伪造耗时。结果中不保存整个召回池正文，只保存最终来源摘要和有界重排记录。

GUI“本轮检索过程”显示查询、候选/选中/实际模型输入数量、预算移除/部分截取、阶段状态/耗时和模型尝试。模型标题根据generation阶段记录显示，避免把相关性复核模型冒充回答模型。旧结果无trace时不构造假诊断。

Windows、千篇容量/重复来源载荷、真实生成/跨语言/冲突/多轮金标、专用Reranker增益及签名发行保持原门禁。官方项目的阈值、架构和宣传指标不是本项目验收证据。
