import {lazy,Suspense,useState} from "react";
import {errorMessage,reviewEvidence,type Evidence,type ReaderFile} from "../bridge";
import Icon,{type IconName} from "./Icon";
const PdfPreview=lazy(()=>import("./PdfPreview"));
export interface ReadingContext {title:string;authors:string[];year:number|null;evidence?:Evidence;claim?:string;question?:string}
export default function SourceWorkspace({file,context,onClose,onSaved,returnLabel}: {returnLabel?:string;file:ReaderFile;context:ReadingContext;onClose:()=>void;onSaved:()=>Promise<unknown>}) {
  const evidence=context.evidence;
  const [status,setStatus]=useState(evidence?.human_status??"unreviewed");
  const [note,setNote]=useState(evidence?.review_note??"");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  const page="anchor" in file?file.anchor.page_number:file.document.page_number??1;
  async function save() {if(!evidence)return;setBusy(true);setError("");setMessage("");try{await reviewEvidence(evidence.id,status,note);setMessage("核查记录已保存，模型自检状态保持独立。");await onSaved();}catch(err){setError(errorMessage(err));}finally{setBusy(false);}}
  async function copy(){try{await navigator.clipboard.writeText(evidence?.quote??"");setMessage("证据摘录已复制。");}catch{setError("未能复制，请选择摘录文本手动复制。");}}
  return <section className="source-page"><header className="page-heading"><div><h1>{evidence?"原文核查":"PDF 阅读"}</h1><div className="breadcrumbs"><span>{evidence?"问答":"文献"}</span><Icon name="chevron" size={14}/><span>{context.question??context.title}</span><Icon name="chevron" size={14}/><span>p.{page}</span></div></div><button onClick={onClose}><Icon name="chevron" className="turn-back" size={17}/>{returnLabel??(evidence?"返回问答":"返回文献")}</button></header>
    <div className={`source-columns ${evidence?"has-evidence":""}`}><section className="source-reader panel"><div className="source-document-title"><span className="round-icon"><Icon name="file"/></span><div><h2>{context.title}</h2><p>{context.authors.join("，")||"作者尚未填写"}{context.year?`（${context.year}）`:""}</p></div></div><Suspense fallback={<p role="status">正在打开 PDF…</p>}><PdfPreview file={file} presentation="embedded" onClose={onClose}/></Suspense></section>
    {evidence&&<aside className="panel source-inspector"><div className="source-reference"><span className="file-icon"><Icon name="file" size={23}/></span><div><h2>引用原文 · p.{page}</h2><p>{context.title}</p><small>{context.authors.join("，")}{context.year?` · ${context.year}`:""}</small></div></div>
      <section className="inspector-section"><header><h3><Icon name="file" size={18}/>证据摘录</h3><button className="text-button" onClick={()=>void copy()}><Icon name="copy" size={15}/>复制</button></header><blockquote className="evidence-quote">{evidence.quote}</blockquote><small className="location-note"><Icon name="info" size={14}/>来源位于第 {page} 页 · 页级定位，未提供精确高亮</small></section>
      <section className="inspector-section"><h3><Icon name="chat" size={18}/>回答中的对应结论</h3>{context.claim?<blockquote className="claim-quote">{context.claim}</blockquote>:<p className="text-muted">此摘录未关联独立生成结论，请直接对照 PDF 核查原文。</p>}</section>
      <section className="inspector-section human-review"><h3><Icon name="user" size={18}/>人工核查</h3><fieldset disabled={busy||evidence.current_source_status!=="verified"}><legend className="sr-only">人工核查状态</legend>{[{value:"confirmed",label:"已核对",icon:"check"},{value:"unreviewed",label:"待确认",icon:"clock"},{value:"rejected",label:"存在歧义",icon:"info"}].map(item=><label key={item.value} className={status===item.value?"selected":""}><input type="radio" name="evidence-review" value={item.value} checked={status===item.value} onChange={()=>setStatus(item.value)}/><Icon name={item.icon as IconName} size={15}/>{item.label}</label>)}</fieldset><label className="sr-only" htmlFor="review-note">核查备注</label><textarea id="review-note" aria-label="核查备注" value={note} onChange={e=>setNote(e.target.value)} maxLength={4000} placeholder="添加核查备注（可选）…" rows={3}/><div className="review-save"><small>{note.length}/4000</small><button className="primary" disabled={busy||evidence.current_source_status!=="verified"} onClick={()=>void save()}>{busy?"保存中…":"保存核查"}</button></div></section>
      {"anchor" in file&&file.anchor.reason_if_degraded?.startsWith("OCR_")&&<p className="notice"><Icon name="info" size={18}/>OCR 内容请与原页图像核对字符与数值，可能存在识别误差。</p>}
      {evidence.current_source_status!=="verified"&&<p className="notice">来源已变化，暂不能核查，请重新提问获取当前引用。</p>}
      {message&&<p role="status" className="text-green">{message}</p>}{error&&<p role="alert" className="job-error">{error}</p>}
    </aside>}</div>
  </section>;
}
