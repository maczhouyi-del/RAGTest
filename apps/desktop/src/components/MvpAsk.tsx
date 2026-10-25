import {lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent} from "react";
import {askQuestion, generationConnections, type GenerationConnection, errorMessage, historyPage, readMvpAnswer, readSource, type AnswerRun, type HistoryPage, type Snapshot, type SourceFile} from "../bridge";
const PdfPreview=lazy(()=>import("./PdfPreview"));

export default function MvpAsk({data,onSettings}:{data:Snapshot;onSettings:()=>void}){
  const [question,setQuestion]=useState("");
  const [model,setModel]=useState("extractive");
  const [providers,setProviders]=useState<GenerationConnection[]>([]),[consent,setConsent]=useState(false);
  const provider=providers.find(item=>item.id===model);
  useEffect(()=>{void generationConnections().then(result=>setProviders(result.providers)).catch(err=>setError(errorMessage(err)));},[]);
  const [history,setHistory]=useState<HistoryPage>({items:[],total:0,next_cursor:null});
  const [selected,setSelected]=useState("");
  const selectedRef=useRef("");selectedRef.current=selected;
  const [answer,setAnswer]=useState<AnswerRun|null>(null);
  const [source,setSource]=useState<SourceFile|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const [conversation,setConversation]=useState<string|null>(null);
  const refresh=useCallback(async()=>{
    const page=await historyPage("answers",null,"");
    setHistory(previous=>previous.items.length>30?{...previous,total:page.total,items:[...page.items,...previous.items.filter(old=>!page.items.some(item=>item.id===old.id))]}:page);
    const id=selectedRef.current;
    if(id){const result=await readMvpAnswer(id);if(id===selectedRef.current)setAnswer(result);}
  },[]);
  useEffect(()=>{let alive=true,inFlight=false;const poll=async()=>{if(inFlight||!alive)return;inFlight=true;try{await refresh();}catch(err){if(alive)setError(errorMessage(err));}finally{inFlight=false;}};void poll();const timer=window.setInterval(()=>void poll(),2500);return()=>{alive=false;window.clearInterval(timer);};},[refresh]);
  useEffect(()=>{setAnswer(null);if(selected)void refresh().catch(err=>setError(errorMessage(err)));},[selected,refresh]);
  const versions=data.documents.filter(doc=>["ready","partial"].includes(doc.parse_status)).map(doc=>doc.doc_version_id);
  async function submit(event:FormEvent){
    event.preventDefault();setBusy(true);setError("");
    try{const run=await askQuestion({question,version_ids:versions,project_id:null,mode:model==="extractive"?"extractive":"generative",strategy:data.index?.ready?"hybrid":"keyword",conversation_id:conversation,provider_id:provider?.id??null,allow_external:Boolean(provider&&consent),provider_revision:provider?.revision,per_paper_limit:8});setConversation(run.conversation_id);setConsent(false);selectedRef.current=run.id;setSelected(run.id);await refresh();setQuestion("");}
    catch(err){setError(errorMessage(err));}finally{setBusy(false);}
  }
  async function open(sourceId:string){try{setError("");setSource({...await readSource(sourceId),evidence_quote:answer?.evidence.find(item=>item.source_anchor_id===sourceId)?.quote});}catch(err){setError(errorMessage(err));}}
  const working=answer&&["queued","running"].includes(answer.status);
  return <div className="mvp-ask">
    <aside className="mvp-history"><div className="panel-head"><h2>历史会话</h2><button onClick={()=>{setConversation(null);setSelected("");setAnswer(null);}}>新会话</button></div>
      {!history.items.length&&<p className="empty">你的问题和引用将保存在本机。</p>}
      {history.items.map(item=><button key={item.id} className={selected===item.id?"history-item selected":"history-item"} onClick={()=>{setConversation(item.conversation_id??null);setSelected(item.id);}}>{item.question}<small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></button>)}
      {history.next_cursor&&<button onClick={()=>{void historyPage("answers",null,history.next_cursor!).then(page=>setHistory(previous=>({...page,items:[...previous.items,...page.items]}))).catch(err=>setError(errorMessage(err)));}}>更早的会话</button>}
    </aside>
    <section className="panel mvp-chat"><div className="panel-head"><h2>与论文对话</h2><span>{versions.length} 篇可检索文献</span></div>
      <div className="mvp-chat-content">
        {!answer&&<div className="mvp-welcome"><h3>从原文中寻找答案</h3><p>导入论文后提问，点击引用回到 PDF。未配置模型时可先查看相关原文。</p></div>}
        {answer&&<article className="answer-run"><h3>{answer.question}</h3>{working&&<p role="status">正在查找来源并整理回答…</p>}
          {answer.status==="refused"&&<p className="notice">当前来源不足以支持可靠回答。请调整问题或文献范围。</p>}
          {["failed","cancelled"].includes(answer.status)&&<p role="alert">{errorMessage(answer.error_code??answer.status)}</p>}
          {answer.mode==="extractive"&&answer.evidence.length>0&&<p>以下是相关原文摘录，未生成综合结论。</p>}
          {answer.status==="completed"&&answer.claims.map(claim=><div className="mvp-claim" key={claim.id}><p>{claim.text}</p><small className="settings-help">模型自检：{claim.model_support==="supported"?"支持":claim.model_support==="contradicted"?"相矛盾":"不确定"} · 人工核对：{claim.human_status==="confirmed"?"已核对":"待核对"}</small><div className="mvp-citations">{claim.evidence_ids.map(id=>{const i=answer.evidence.findIndex(e=>e.id===id);const evidence=answer.evidence[i];return evidence?<button key={id} disabled={evidence.current_source_status!=="verified"} onClick={()=>void open(evidence.source_anchor_id)}>引用 {i+1}</button>:null;})}</div></div>)}
          {answer.mode==="generative"&&answer.status==="completed"&&<p className="settings-help">模型生成的回答，请结合引用核对。</p>}
          {answer.evidence.map((evidence,index)=>{let page:number|undefined;try{page=JSON.parse(evidence.anchor_json).page_number;}catch{/* page unavailable; never invent it */}return <section className="evidence-card" key={evidence.id}><button disabled={evidence.current_source_status!=="verified"} onClick={()=>void open(evidence.source_anchor_id)}>查看引用 {index+1}{page?` · 第 ${page} 页`:""}</button><blockquote>{evidence.quote}</blockquote>{evidence.current_source_status!=="verified"&&<p className="notice">该来源已变化，请重新提问获取当前引用。</p>}</section>;})}
        </article>}
      </div>
      <form className="mvp-composer" onSubmit={event=>void submit(event)}>
        <label>生成模型<select aria-label="生成模型" value={model} onChange={event=>{setModel(event.target.value);setConsent(false);}}><option value="extractive">原文摘录（不调用模型）</option>{data.generator?.configured&&<option value="local">本地 Qwen</option>}{providers.map(item=><option key={item.id} value={item.id} disabled={!item.configured}>{item.name} · {item.model}{item.configured?"":"（需配置）"}</option>)}</select></label><button type="button" onClick={onSettings}>配置模型</button>
        {provider&&<label className="notice"><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)}/>允许本次请求向 {provider.base_url} 的 {provider.model} 发送问题与检索片段；该服务可能产生费用。不会自动切换其他服务。</label>}
        <label className="mvp-question">你的问题<textarea aria-label="你的问题" value={question} onChange={event=>setQuestion(event.target.value)} maxLength={4000} required placeholder="例如：BERT 使用了哪些预训练任务？"/></label>
        {!data.index?.ready&&<p className="settings-help">当前使用关键词检索；在设置中准备本地索引后启用混合检索。</p>}
        {error&&<p role="alert" className="job-error">{error}</p>}
        <button className="primary" disabled={busy||Boolean(working)||!versions.length||!question.trim()||Boolean(provider&&!consent)}>发送问题</button>
      </form>
    </section>
    {source&&<Suspense fallback={<p role="status">正在加载原文…</p>}><PdfPreview file={source} onClose={()=>setSource(null)}/></Suspense>}
  </div>;
}
