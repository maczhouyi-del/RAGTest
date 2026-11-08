import {useEffect,useLayoutEffect,useRef,useState,type FormEvent} from "react";
import {manageConversation,conversationTurns,askQuestion,errorMessage,readSource,type AnswerRun,type Evidence,type GenerationConnection,type ReaderFile,type Snapshot} from "../bridge";
import Icon from "./Icon";
import TurnEvidence from "./TurnEvidence";
import CopyButton from "./CopyButton";
import {answerParagraphs} from "./answerPresentation";
import type {ReadingContext} from "./SourceWorkspace";

export default function MvpAsk({data,creatingConversation,providers,model,onModel,strategy,onStrategy,conversationId,onConversation,selectedId,onSelected,onCreated,onSettings,onImport,onRead}: {
  data:Snapshot;creatingConversation:boolean;providers:GenerationConnection[];model:string;onModel:(model:string)=>void;strategy:string;onStrategy:(value:string)=>void;conversationId:string;onConversation:(id:string)=>void;selectedId:string;onSelected:(id:string)=>void;onCreated:()=>Promise<unknown>;onSettings:()=>void;onImport:()=>void;onRead:(file:ReaderFile,context:ReadingContext)=>void;
}) {
  const [question,setQuestion]=useState(""),[loading,setLoading]=useState(false);
  const [answers,setAnswers]=useState<AnswerRun[]>([]),[olderCursor,setOlderCursor]=useState<string|null>(null);
  const [awaitingResult,setAwaitingResult]=useState(false);
  const visibleAnswers=answers.filter(item=>item.conversation_id===conversationId);
  const answer=awaitingResult?null:selectedId?visibleAnswers.find(item=>item.id===selectedId)??null:visibleAnswers.at(-1)??null;
  useEffect(()=>{setAwaitingResult(false);},[selectedId,conversationId]);
  const [scope,setScope]=useState("all");
  const [busy,setBusy]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState("");
  const submitting=useRef(false),composing=useRef(false),polling=useRef(true),pendingRun=useRef<string|null>(null);
  const chat=useRef<HTMLDivElement>(null),scrollIntent=useRef<string|null>(null),prepend=useRef<{height:number;top:number}|null>(null);
  const [pendingQuestion,setPendingQuestion]=useState<{text:string;runId?:string}|null>(null),[archived,setArchived]=useState(false);
  useLayoutEffect(()=>{
    const container=chat.current;if(!container)return;
    if(prepend.current){container.scrollTop=prepend.current.top+container.scrollHeight-prepend.current.height;prepend.current=null;return;}
    const target=scrollIntent.current;if(!target)return;
    const node=target==="pending"?container.querySelector<HTMLElement>("[data-pending-question]"):Array.from(container.querySelectorAll<HTMLElement>("[data-run-id]")).find(item=>item.dataset.runId===target);
    if(node){container.scrollTo({top:container.scrollTop+node.getBoundingClientRect().top-container.getBoundingClientRect().top,behavior:"instant"});scrollIntent.current=null;}
  },[answers,pendingQuestion]);
  const current=useRef(conversationId),submittedConversation=useRef<string|null>(null);current.current=conversationId;
  const provider=providers.find(item=>item.id===model);
  useEffect(()=>{
    let alive=true,inFlight=false,cursorLoaded=false;
    polling.current=true;
    if(submittedConversation.current!==conversationId){pendingRun.current=null;setPendingQuestion(null);scrollIntent.current=null;prepend.current=null;}
    setLoading(!!conversationId);setAnswers([]);setOlderCursor(null);setError("");setPending(false);setQuestion("");setArchived(false);
    if(!conversationId){setScope("all");setPendingQuestion(null);return;}
    const poll=async()=>{if(inFlight)return;inFlight=true;try{const result=await conversationTurns(conversationId);if(alive&&current.current===conversationId){setLoading(false);setArchived(!!result.conversation.archived_at);if(!cursorLoaded&&!pendingQuestion){scrollIntent.current=result.items.at(-1)?.id??null;}setPendingQuestion(previous=>previous?.runId&&result.items.some(item=>item.id===previous.runId)?null:previous);setAnswers(previous=>[...previous.filter(old=>!result.items.some(item=>item.id===old.id)),...result.items]);if(!cursorLoaded){setOlderCursor(result.next_cursor);cursorLoaded=true;}if(pendingRun.current&&result.items.some(item=>item.id===pendingRun.current))pendingRun.current=null;polling.current=!!pendingRun.current||result.items.some(item=>["queued","running"].includes(item.status));setPending(polling.current);}}catch(err){if(alive){setLoading(false);setError(errorMessage(err));}}finally{inFlight=false;}};
    void poll();const timer=window.setInterval(()=>{if(polling.current&&document.visibilityState==="visible")void poll();},1000);return()=>{alive=false;window.clearInterval(timer);};
  },[conversationId]);
  const parsed=data.documents.filter(doc=>["ready","partial"].includes(doc.parse_status));
  const newest = new Map<string,string>();
  for(const doc of [...parsed].sort((a,b)=>b.created_at.localeCompare(a.created_at)||a.doc_version_id.localeCompare(b.doc_version_id))) if(!newest.has(doc.document_id))newest.set(doc.document_id,doc.doc_version_id);
  const versions=parsed.filter(doc=>scope==="compare"||(scope==="all"?newest.get(doc.document_id)===doc.doc_version_id:scope===doc.doc_version_id)).map(doc=>doc.doc_version_id);
  const effectiveStrategy=data.index?.ready?strategy:"keyword";
  function isSystemInformationQuestion(value:string){const normalized=value.normalize("NFKC").toLowerCase().replace(/[\s\p{P}]+/gu,"");return Object.values(data.health.system_question_forms??{}).some(forms=>forms.includes(normalized));}
  const systemQuestion=isSystemInformationQuestion(question);
  const available=systemQuestion||model==="extractive"||(model==="local"?data.generator?.configured:provider?.can_answer);
  async function submit(event:FormEvent) {
    event.preventDefault();if(submitting.current||busy||pending||!question.trim()||question.length>4000||(!systemQuestion&&!versions.length)||!available||archived||loading||creatingConversation)return;
    const submittingConversation=conversationId;submittedConversation.current=conversationId;
    submitting.current=true;polling.current=true;pendingRun.current="submitting";scrollIntent.current="pending";setPendingQuestion({text:question});setAwaitingResult(true);setBusy(true);setPending(true);setError("");
    try{const run=await askQuestion({question,version_ids:versions,project_id:null,mode:model==="extractive"?"extractive":"generative",strategy:effectiveStrategy,conversation_id:conversationId||null,provider_id:provider?.id??null,provider_revision:provider?.revision,per_paper_limit:3,version_policy:scope==="all"?"latest_imported":"explicit_versions"});if(current.current!==submittingConversation){await onCreated();return;}submittedConversation.current=run.conversation_id;pendingRun.current=run.id;setPendingQuestion(previous=>previous?{...previous,runId:run.id}:null);onConversation(run.conversation_id);onSelected(run.id);setQuestion("");await onCreated();}
    catch(err){pendingRun.current=null;polling.current=false;setError(errorMessage(err));setPendingQuestion(null);setAwaitingResult(false);setPending(false);}finally{submitting.current=false;setBusy(false);}
  }
  async function open(evidence:Evidence,owner:AnswerRun|null=answer) {
    try{setError("");const file=await readSource(evidence.source_anchor_id);const document=data.documents.find(doc=>doc.doc_version_id===file.anchor.doc_version_id);const claim=owner?.claims.find(item=>item.evidence_ids.includes(evidence.id));onRead({...file,evidence_quote:evidence.quote},{title:document?.title??"引用文献",authors:document?.authors??[],year:document?.year??null,evidence,claim:claim?.text,question:owner?.question});}
    catch(err){setError(errorMessage(err));}
  }
  return <section className="chat-page">
    <div className="chat-center"><header className="page-heading chat-heading"><div><h1>与文献对话</h1><p>基于你的 PDF 文献，进行问答、总结与知识探索</p></div><div className="chat-scope"><label><Icon name="book"/><select aria-label="问答文献范围" value={scope} onChange={e=>setScope(e.target.value)}><option value="all">全部文献（每篇最近导入的可检索版本）</option><option value="compare">显式比较全部可检索版本</option>{parsed.map(doc=><option key={doc.doc_version_id} value={doc.doc_version_id}>{doc.title} · {doc.file_sha256.slice(0,8)} · 导入 {doc.created_at}</option>)}</select></label><span className="count-badge"><Icon name="database"/>{versions.length} 个版本已选</span></div></header>
      <div className="chat-scroll" ref={chat} aria-label="对话消息" aria-live="polite">
        {!answers.length&&!loading&&<div className="chat-start"><span className="round-icon"><Icon name="chat" size={34}/></span><h2>从文献出发，找到有据可查的答案</h2><p>输入你的问题，或选择左侧的历史对话继续核查。<br/>每条引用都能回到本地 PDF 原文。</p><div className="prompt-examples"><button onClick={()=>setQuestion("这篇论文采用了什么研究方法？")}>论文采用了什么研究方法？</button><button onClick={()=>setQuestion("论文中的主要实验结论是什么？")}>论文的主要实验结论是什么？</button></div></div>}
        {loading&&!answers.length&&<p className="loading-text" role="status">正在读取本地对话…</p>}
        {olderCursor&&<button onClick={()=>void conversationTurns(conversationId,olderCursor).then(page=>{if(current.current!==conversationId)return;const node=chat.current;if(node)prepend.current={height:node.scrollHeight,top:node.scrollTop};setAnswers(previous=>[...page.items.filter(item=>!previous.some(old=>old.id===item.id)),...previous]);setOlderCursor(page.next_cursor);}).catch(err=>setError(errorMessage(err)))}>加载更早消息</button>}
        {visibleAnswers.map(turn=>{const paragraphs=answerParagraphs(turn,isSystemInformationQuestion(turn.question));return <div key={turn.id} className={`conversation-turn ${answer?.id===turn.id?"selected-turn":""}`} data-run-id={turn.id} onClick={()=>{setAwaitingResult(false);onSelected(turn.id);}}>
          <div className="user-message"><span className="user-avatar">U</span><div className="question-content"><button className="turn-question" aria-label={`查看本轮检索：${turn.question}`} onClick={()=>{setAwaitingResult(false);onSelected(turn.id);}}><h3>{turn.question}</h3></button><div className="turn-actions"><CopyButton text={turn.question} label="复制问题"/></div></div></div>
          <div className="assistant-message"><span className="assistant-avatar"><Icon name="robot" size={23}/></span><article className="answer-card" aria-label="回答正文">
          {paragraphs.map((part,index)=><p key={index} className={part.className} role={part.role}>{part.text}</p>)}
          {!["queued","running"].includes(turn.status)&&paragraphs.length>0&&<div className="turn-actions"><CopyButton text={paragraphs.map(part=>part.text).join("\n\n")} label="复制回答"/></div>}
          </article></div>
        </div>;})}
        {pendingQuestion&&!answers.some(item=>item.id===pendingQuestion.runId)&&<div className="conversation-turn" data-pending-question><div className="user-message"><span className="user-avatar">U</span><div className="turn-question"><h3>{pendingQuestion.text}</h3></div></div><p role="status">正在提交问题…</p></div>}
      </div>
      <form className="chat-composer" onSubmit={event=>void submit(event)}><label className="sr-only" htmlFor="chat-question">你的问题</label><textarea id="chat-question" aria-label="你的问题" disabled={loading||creatingConversation} value={question} onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;}} onKeyDown={event=>{if(event.key!=="Enter"||event.shiftKey)return;if(composing.current||event.nativeEvent.isComposing||event.keyCode===229)return;event.preventDefault();event.currentTarget.form?.requestSubmit();}} onChange={event=>setQuestion(event.target.value)} maxLength={4000} required placeholder="询问你的 PDF 文献…" rows={2}/>

        {archived&&<p className="notice">此对话已归档。<button type="button" onClick={()=>void manageConversation(conversationId,"restore").then(async()=>{setArchived(false);await onCreated();}).catch(err=>setError(errorMessage(err)))}>恢复后继续提问</button></p>}
        {error&&<p role="alert" className="job-error">{error}</p>}
        <div className="composer-toolbar"><div className="composer-left"><button type="button" className="icon-button" aria-label="导入 PDF" title="导入 PDF" onClick={onImport} disabled={busy||pending}><Icon name="folder"/></button><button type="button" className="icon-button" aria-label="配置模型" title="配置模型" onClick={onSettings}><Icon name="settings"/></button><small>Enter 发送 · Shift+Enter 换行</small></div><div className="composer-controls"><label><Icon name="sliders" size={18}/><select aria-label="检索策略" value={effectiveStrategy} onChange={e=>onStrategy(e.target.value)}><option value="hybrid" disabled={!data.index?.ready}>混合检索</option><option value="keyword">关键词检索</option><option value="vector_exact" disabled={!data.index?.ready}>向量检索</option></select></label><label><Icon name="monitor" size={18}/><select aria-label="生成模型" value={model} onChange={e=>onModel(e.target.value)}><option value="extractive">原文摘录（不调用模型）</option><option value="local" disabled={!data.generator?.configured}>本地 Qwen{data.generator?.configured?"":"（未配置）"}</option>{providers.map(item=><option key={item.id} value={item.id} disabled={!item.can_answer}>{item.name} · {item.model}{!item.configured?"（需配置凭据）":!item.document_qa_enabled?"（未启用文献问答）":""}</option>)}</select></label><button className="primary" disabled={loading||creatingConversation||archived||busy||pending||(!systemQuestion&&!versions.length)||!question.trim()||!available}><Icon name="send" size={19}/>{busy||pending?"处理中…":"发送问题"}</button></div></div>
        {!systemQuestion&&effectiveStrategy==="keyword"&&data.index?.ready&&<p className="composer-hint">关键词检索依赖原文词语；中文提问英文文献时可使用混合检索。<button type="button" className="text-button" onClick={()=>onStrategy("hybrid")}>切换混合检索</button></p>}
        {systemQuestion?<p className="composer-hint">此问题读取本机配置，不执行文献检索或模型推理。</p>:!data.index?.ready&&<p className="composer-hint">当前使用关键词检索；在设置中准备本地索引后启用混合检索。</p>}
      </form>
    </div>
    <TurnEvidence answer={answer} data={data} pending={awaitingResult||pending} onOpen={evidence=>void open(evidence)}/>
  </section>;
}
