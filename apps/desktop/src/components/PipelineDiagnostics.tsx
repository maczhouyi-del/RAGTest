import type {AnswerRun} from "../bridge";

const stageNames:Record<string,string>={
  scope_validation:"范围校验",query_construction:"查询构造",retrieval:"本地检索",
  relevance_review:"本地相关性复核",context_selection:"上下文选择",source_validation:"来源校验",
  answer_generation:"回答生成",quote_validation:"引用校验",support_check:"支持性检查",
  publication_validation:"发布校验",system_info:"系统信息",
};
export default function PipelineDiagnostics({result}:{result:AnswerRun["result"]}) {
  const trace=result?.pipeline_trace;
  if(!trace||result?.kind==="system_info")return null;
  const counts=trace.model_attempts,retrieval=result?.retrieval,context=result?.model_context;
  return <details className="pipeline-diagnostics">
    <summary>本轮检索过程</summary>
    {result?.context_policy&&<p>实际检索查询：{result.context_policy.retrieval_query}</p>}
    {retrieval&&<p>策略：{retrieval.strategy}；关键词候选 {retrieval.candidate_counts?.lexical??0} 条，向量候选 {retrieval.candidate_counts?.vector_embeddings??0} 组；最终选择 {retrieval.hits?.length??0} 段。</p>}
    {context?.included_chunk_ids&&<p>应用送入模型 {context.included_chunk_ids.length} 段；预算移除 {context.dropped_chunk_ids?.length??0} 段，部分截取 {context.excerpt_lengths?.filter(item=>item.is_partial).length??0} 段。</p>}
    {typeof context?.usage?.total_tokens==="number"&&<p>回答调用返回 Token 总量：{context.usage.total_tokens}（不含后续支持性检查）。</p>}
    <p>模型尝试：回答 {counts.answer} 次，支持性检查 {counts.support} 次，本地相关性复核 {counts.relevance} 次。</p>
    <small>次数是应用调用尝试；实际 Token 用量以接口返回为准。分段时间不含排队与界面传输。</small>
    <table><thead><tr><th>步骤</th><th>状态</th><th>耗时</th></tr></thead><tbody>{trace.stages.map((stage,index)=><tr key={index}><td>{stageNames[stage.stage]??stage.stage}</td><td>{stage.status==="completed"?"完成":stage.status==="failed"?"失败":"处理中"}</td><td>{typeof stage.elapsed_ms==="number"&&Number.isFinite(stage.elapsed_ms)?`${stage.elapsed_ms.toFixed(1)} ms`:"未测量"}</td></tr>)}</tbody></table>
  </details>;
}
