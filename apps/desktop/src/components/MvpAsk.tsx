import {useEffect,useRef,useState,type FormEvent} from "react";
import {askQuestion,errorMessage,readMvpAnswer,readSource,type AnswerRun,type Evidence,type GenerationConnection,type ReaderFile,type Snapshot} from "../bridge";
import Icon from "./Icon";
import type {ReadingContext} from "./SourceWorkspace";

function evidencePage(evidence:Evidence):number|null {try{const value=JSON.parse(evidence.anchor_json).page_number;return Number.isInteger(value)&&value>0?value:null;}catch{return null;}}
export default function MvpAsk({data,providers,model,onModel,strategy,onStrategy,selectedId,onSelected,onCreated,onSettings,onImport,onRead}: {
  data:Snapshot;providers:GenerationConnection[];model:string;onModel:(model:string)=>void;strategy:string;onStrategy:(value:string)=>void;selectedId:string;onSelected:(id:string)=>void;onCreated:()=>Promise<unknown>;onSettings:()=>void;onImport:()=>void;onRead:(file:ReaderFile,context:ReadingContext)=>void;
}) {
  const [question,setQuestion]=useState("");
  const [answer,setAnswer]=useState<AnswerRun|null>(null);
  const [scope,setScope]=useState("all");
  const [busy,setBusy]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState(""),[consent,setConsent]=useState(false),[allSources,setAllSources]=useState(false);
  const submitting=useRef(false),composing=useRef(false);
  const current=useRef(selectedId);current.current=selectedId;
  const provider=providers.find(item=>item.id===model);
  useEffect(()=>setConsent(false),[model,provider?.revision]);
  useEffect(()=>{
    let alive=true,inFlight=false;
    setAnswer(null);setError("");setAllSources(false);setPending(false);setConsent(false);
    if(!selectedId){setQuestion("");setScope("all");return;}
    const poll=async()=>{if(inFlight)return;inFlight=true;try{const result=await readMvpAnswer(selectedId);if(alive&&current.current===selectedId){setAnswer(result);setPending(["queued","running"].includes(result.status));}}catch(err){if(alive)setError(errorMessage(err));}finally{inFlight=false;}};
    void poll();const timer=window.setInterval(()=>void poll(),2500);return()=>{alive=false;window.clearInterval(timer);};
  },[selectedId]);
  const parsed=data.documents.filter(doc=>["ready","partial"].includes(doc.parse_status));
  const versions=parsed.filter(doc=>scope==="all"||scope===doc.doc_version_id).map(doc=>doc.doc_version_id);
  const effectiveStrategy=data.index?.ready?strategy:"keyword";
  const available=model==="extractive"||(model==="local"?data.generator?.configured:provider?.configured);
  async function submit(event:FormEvent) {
    event.preventDefault();if(submitting.current||busy||pending||!question.trim()||question.length>4000||!versions.length||!available||(provider&&!consent))return;
    submitting.current=true;setBusy(true);setPending(true);setError("");
    try{const run=await askQuestion({question,version_ids:versions,project_id:null,mode:model==="extractive"?"extractive":"generative",strategy:effectiveStrategy,conversation_id:selectedId?answer?.conversation_id??null:null,provider_id:provider?.id??null,allow_external:!!provider&&consent,provider_revision:provider?.revision,per_paper_limit:8});setConsent(false);onSelected(run.id);setQuestion("");await onCreated();}
    catch(err){setError(errorMessage(err));setPending(false);}finally{submitting.current=false;setBusy(false);}
  }
  async function open(evidence:Evidence) {
    try{setError("");const file=await readSource(evidence.source_anchor_id);const document=data.documents.find(doc=>doc.doc_version_id===file.anchor.doc_version_id);const claim=answer?.claims.find(item=>item.evidence_ids.includes(evidence.id));onRead({...file,evidence_quote:evidence.quote},{title:document?.title??"引用文献",authors:document?.authors??[],year:document?.year??null,evidence,claim:claim?.text,question:answer?.question});}
    catch(err){setError(errorMessage(err));}
  }
  const sources=answer?.evidence.filter((item,index,rows)=>rows.findIndex(other=>other.source_anchor_id===item.source_anchor_id)===index)??[];
  const documentFor=(evidence:Evidence)=>{try{return data.documents.find(doc=>doc.doc_version_id===JSON.parse(evidence.anchor_json).doc_version_id);}catch{return undefined;}};
  return <section className="chat-page">
    <div className="chat-center"><header className="page-heading chat-heading"><div><h1>与文献对话</h1><p>基于你的 PDF 文献，进行问答、总结与知识探索</p></div><div className="chat-scope"><label><Icon name="book"/><select aria-label="问答文献范围" value={scope} onChange={e=>setScope(e.target.value)}><option value="all">全部文献</option>{parsed.map(doc=><option key={doc.doc_version_id} value={doc.doc_version_id}>{doc.title}</option>)}</select></label><span className="count-badge"><Icon name="database"/>{parsed.length} 篇可检索</span></div></header>
      <div className="chat-scroll" aria-live="polite">
        {!answer&&!selectedId&&<div className="chat-start"><span className="round-icon"><Icon name="chat" size={34}/></span><h2>从文献出发，找到有据可查的答案</h2><p>输入你的问题，或选择左侧的历史对话继续核查。<br/>每条引用都能回到本地 PDF 原文。</p><div className="prompt-examples"><button onClick={()=>setQuestion("这篇论文采用了什么研究方法？")}>论文采用了什么研究方法？</button><button onClick={()=>setQuestion("论文中的主要实验结论是什么？")}>论文的主要实验结论是什么？</button></div></div>}
        {selectedId&&!answer&&<p className="loading-text" role="status">正在读取本地对话…</p>}
        {answer&&<><div className="user-message"><span className="user-avatar">U</span><div><h3>{answer.question}</h3></div></div><div className="assistant-message"><span className="assistant-avatar"><Icon name="robot" size={23}/></span><article className="answer-card"><h2><span className="mini-icon"><Icon name="database" size={18}/></span>{answer.mode==="extractive"?"检索到的原文证据":"基于检索证据的回答"}</h2>
          {["queued","running"].includes(answer.status)&&<p role="status" className="loading-text">正在查找来源并整理回答…</p>}
          {answer.status==="refused"&&<p className="notice">当前来源不足以支持可靠回答。请调整问题或文献范围。</p>}
          {["failed","cancelled"].includes(answer.status)&&<p className="job-error" role="alert">{errorMessage(answer.error_code??answer.status)}</p>}
          {answer.mode==="extractive"&&answer.evidence.length>0&&<p className="answer-intro">以下是相关原文摘录，未生成综合结论。</p>}
          {answer.status==="completed"&&answer.claims.map(claim=><section className="answer-claim" key={claim.id}><p>{claim.text}</p><div className="claim-status">模型自检：{claim.model_support==="supported"?"支持":claim.model_support==="contradicted"?"相矛盾":"不确定"}<span>人工核对：{claim.human_status==="confirmed"?"已核对":claim.human_status==="rejected"?"存在歧义":"待核对"}</span></div><div className="citation-cards">{claim.evidence_ids.map(id=>{const evidence=answer.evidence.find(e=>e.id===id);if(!evidence)return null;const doc=documentFor(evidence);return <button key={id} disabled={evidence.current_source_status!=="verified"} onClick={()=>void open(evidence)}><Icon name="file"/><span>{doc?.title??"引用文献"}<small>{evidencePage(evidence)?`第 ${evidencePage(evidence)} 页`:"页码未验证"}{doc?.year?` · ${doc.year}`:""}</small></span><Icon name="chevron" size={16}/></button>;})}</div></section>)}
          {(answer.mode==="extractive"||answer.status==="refused")&&sources.slice(0,3).map((evidence,index)=><section className="answer-excerpt" key={evidence.id}><div><Icon name="file" size={17}/><strong>{documentFor(evidence)?.title??"引用文献"}</strong></div><blockquote>{evidence.quote}</blockquote><button className="text-button" disabled={evidence.current_source_status!=="verified"} onClick={()=>void open(evidence)}>查看引用 {index+1}{evidencePage(evidence)?` · 第 ${evidencePage(evidence)} 页`:""}<Icon name="chevron" size={15}/></button></section>)}
          {answer.mode==="generative"&&answer.status==="completed"&&<p className="answer-note"><Icon name="info" size={16}/>模型生成的回答，请结合引用核对。</p>}
          {answer.evidence.some(e=>e.current_source_status!=="verified")&&<p className="notice">部分来源已变化或不可用，请重新提问获取当前引用。</p>}
        </article></div></>}
      </div>
      <form className="chat-composer" onSubmit={event=>void submit(event)}><label className="sr-only" htmlFor="chat-question">你的问题</label><textarea id="chat-question" aria-label="你的问题" value={question} onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;}} onKeyDown={event=>{if(event.key!=="Enter"||event.shiftKey)return;if(composing.current||event.nativeEvent.isComposing||event.keyCode===229)return;event.preventDefault();event.currentTarget.form?.requestSubmit();}} onChange={event=>setQuestion(event.target.value)} maxLength={4000} required placeholder="询问你的 PDF 文献…" rows={2}/>
        {provider&&<label className="provider-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>允许本次请求向 {provider.base_url} 的 {provider.model} 发送问题与检索片段；该服务可能产生费用。不会自动切换其他服务。</label>}
        {error&&<p role="alert" className="job-error">{error}</p>}
        <div className="composer-toolbar"><div className="composer-left"><button type="button" className="icon-button" aria-label="导入 PDF" title="导入 PDF" onClick={onImport} disabled={busy||pending}><Icon name="folder"/></button><button type="button" className="icon-button" aria-label="配置模型" title="配置模型" onClick={onSettings}><Icon name="settings"/></button><small>Enter 发送 · Shift+Enter 换行</small></div><div className="composer-controls"><label><Icon name="sliders" size={18}/><select aria-label="检索策略" value={effectiveStrategy} onChange={e=>onStrategy(e.target.value)}><option value="hybrid" disabled={!data.index?.ready}>混合检索</option><option value="keyword">关键词检索</option><option value="vector_exact" disabled={!data.index?.ready}>向量检索</option></select></label><label><Icon name="monitor" size={18}/><select aria-label="生成模型" value={model} onChange={e=>onModel(e.target.value)}><option value="extractive">原文摘录（不调用模型）</option><option value="local" disabled={!data.generator?.configured}>本地 Qwen{data.generator?.configured?"":"（未配置）"}</option>{providers.map(item=><option key={item.id} value={item.id} disabled={!item.configured}>{item.name} · {item.model}{item.configured?"":"（需配置）"}</option>)}</select></label><button className="primary" disabled={busy||pending||!versions.length||!question.trim()||!available||!!provider&&!consent}><Icon name="send" size={19}/>{busy||pending?"处理中…":"发送问题"}</button></div></div>
        {!data.index?.ready&&<p className="composer-hint">当前使用关键词检索；在设置中准备本地索引后启用混合检索。</p>}
      </form>
    </div>
    <aside className="chat-evidence"><section className="panel connection-card"><span className="round-icon"><Icon name="database" size={28}/></span><div><h2><span className="online-dot"/>本地资料库已连接</h2><p>索引状态：<span className={data.index?.ready?"text-green":"text-muted"}>{data.index?.ready?"就绪":data.index?.configured?"需更新":"尚未建立"}</span></p></div></section><section className="panel evidence-list"><div className="evidence-list-heading"><h2>本次检索</h2><Icon name="down" size={18}/></div><p className="text-muted">{sources.length?`共找到 ${sources.length} 条来源证据`:"提问后在这里查看相关原文"}</p><div className="evidence-items">{(allSources?sources:sources.slice(0,4)).map((evidence,index)=><button key={evidence.id} className="evidence-result" disabled={evidence.current_source_status!=="verified"} aria-label={`打开证据 ${index+1}`} onClick={()=>void open(evidence)}><span className="evidence-number">{index+1}</span><Icon name="file" size={18}/><div><strong>{documentFor(evidence)?.title??"引用文献"}</strong><p>{evidence.quote}</p></div><small>{evidencePage(evidence)?`p.${evidencePage(evidence)}`:"—"}</small></button>)}</div>{sources.length>4&&<button className="all-evidence" onClick={()=>setAllSources(!allSources)}><Icon name="list" size={17}/>{allSources?"收起检索结果":"查看全部检索结果"}<Icon name="chevron" size={16}/></button>}{!sources.length&&<div className="evidence-placeholder"><Icon name="file" size={32}/><p>引用会关联真实 PDF 和页码，<br/>点击即可打开原文核查。</p></div>}</section></aside>
  </section>;
}
