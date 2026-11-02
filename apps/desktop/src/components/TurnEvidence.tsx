import type {AnswerRun,Evidence,Snapshot} from "../bridge";
import PipelineDiagnostics from "./PipelineDiagnostics";

function page(item:Evidence){try{const n=JSON.parse(item.anchor_json).page_number;return Number.isInteger(n)&&n>0?n:null;}catch{return null;}}
function version(item:Evidence){try{return JSON.parse(item.anchor_json).doc_version_id as string;}catch{return "";}}
const human=(value:string)=>value==="confirmed"?"已核对":value==="rejected"?"存在歧义":"待核对";
const support=(value:string)=>value==="supported"?"认为支持":value==="contradicted"?"相矛盾":value==="uncertain"?"不确定":"未执行";
export default function TurnEvidence({answer,data,pending,onOpen}:{answer:AnswerRun|null;data:Snapshot;pending:boolean;onOpen:(evidence:Evidence)=>void}) {
 const system=answer?.result?.kind==="system_info";
 return <aside className="chat-evidence" aria-label="本次检索" data-answer-run={answer?.id??""}>
  <header className="evidence-list-heading"><h2>本次检索</h2></header>
  {!answer?<p className="text-muted">{pending?"正在提交本轮问题，检索尚未完成。":"选择对话中的一轮，查看其检索与证据。"}</p>:<>
  <p className="evidence-question">当前问题：{answer.question}</p>
  <p className="text-muted">{system?"本机配置（未调用模型）":answer.mode==="extractive"?"原文摘录（未生成答案）":String(answer.model_history?.find(attempt=>attempt.stage==="generation")?.fingerprint.model??"尚未调用回答模型")} · {answer.status}</p>
  {system?<p className="notice">本轮属于系统信息查询。未执行文献检索，没有论文引用。</p>:<>
  {answer.status==="refused"&&answer.result?.outcome==="insufficient_evidence"&&<section><h3>本轮未能回答的原因</h3><p>检索片段 {answer.result.retrieval?.hits?.length??"未记录"} 段；生成草稿 {answer.claims.length} 条；通过支持性检查 {answer.claims.filter(item=>item.model_support==="supported").length} 条。</p><p>{answer.claims.length?"模型检查的具体理由列在下方对应引用中。":"模型未提供结论，未执行支持性检查；没有结论不等于没有检索结果。"}</p></section>}
  <section className="turn-scope"><h3>本轮文献范围</h3><p>{new Set(answer.scope.map(doc=>doc.document_id??doc.doc_version_id)).size} 篇文献 · {answer.scope.length} 个文件版本</p>
   <ul>{answer.scope.map(doc=>{const current=data.documents.find(item=>item.doc_version_id===doc.doc_version_id);return <li key={doc.doc_version_id}><strong>{current?.title??doc.title}</strong>{current&&current.title!==doc.title&&<small>保存题名：{doc.title}</small>}<small>版本 {doc.file_sha256.slice(0,12)} · 本轮解析状态 {doc.parse_status}</small><small>当前状态：{current?current.parse_status:"当前可见列表中不可用"}</small></li>;})}</ul>
   <small>{answer.result?.retrieval?"实际检索限定于以上冻结范围；未命中的文献不表示未纳入范围。":"检索尚未执行或本轮未保存检索记录。"}</small>
  </section>
  <section><h3>检索策略与过程</h3><p>本轮策略：{answer.strategy}</p><PipelineDiagnostics result={answer.result} expanded/>{!answer.result?.pipeline_trace&&<p>本轮尚无阶段记录；旧记录缺失的数据不补造。</p>}</section>
  <section className="turn-sources"><h3>原文引用</h3>{answer.evidence.length===0&&<p>{["queued","running"].includes(answer.status)?"正在处理本轮，引用尚未发布。":"本轮没有可展示的原文引用。"}</p>}
   {answer.evidence.map((item,index)=>{const saved=answer.scope.find(doc=>doc.doc_version_id===version(item));const doc=data.documents.find(doc=>doc.doc_version_id===version(item));const claims=answer.claims.filter(claim=>claim.evidence_ids.includes(item.id));return <article className="turn-source" key={item.id} data-evidence-id={item.id}>
    <button className="source-link" aria-label={`打开证据 ${index+1}`} disabled={item.current_source_status!=="verified"} onClick={()=>onOpen(item)}>{doc?.title??saved?.title??"引用文献"} · {page(item)?`第 ${page(item)} 页`:"页码未验证"}</button>
    <small>版本 {(saved?.file_sha256??doc?.file_sha256)?.slice(0,12)??"未保存"}</small>
    <blockquote>{item.quote}</blockquote>
    <p className="source-status">引用校验：{item.current_source_status==="verified"?"原文精确匹配":item.current_source_status} · 人工核对：{human(item.human_status)}</p>
    {claims.length?claims.map(claim=><div className="source-claim" key={claim.id}><h4>对应模型结论</h4><p>{claim.text}</p><small>原始引用校验：{claim.source_status} · 同一模型自检：{support(claim.model_support)} · 人工核对：{human(claim.human_status)}</small>{answer.result?.support_checks?.filter(check=>check.claim_id===claim.id).map((check,n)=><p className="text-muted" key={n}>{check.reason}</p>)}</div>):<p className="text-muted">候选原文，未关联模型结论；支持性检查未执行。</p>}
   </article>;})}
   {answer.claims.filter(claim=>!claim.evidence_ids.length).map(claim=><p key={claim.id}>未关联引用的草稿：{claim.text}（{support(claim.model_support)}）</p>)}
  </section>
  </>}
  </>}
 </aside>;
}
