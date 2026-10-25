import {lazy,Suspense,useCallback,useEffect,useRef,useState} from "react";
import {cancelJob,errorMessage,importPdf,prepareMvp,readDocument,retryJob,snapshot,type Snapshot,type ReaderFile} from "./bridge";
import MvpAsk from "./components/MvpAsk";
import MvpSettings from "./components/MvpSettings";
import DocumentDetails from "./components/DocumentDetails";
const PdfPreview=lazy(()=>import("./components/PdfPreview"));
const stateLabels:Record<string,string>={not_started:"待解析",ready:"已解析",partial:"部分解析",failed:"失败",queued:"等待中",running:"处理中",completed:"完成",cancelled:"已取消",retry_wait:"待重试"};
export default function App(){
  const [tab,setTab]=useState<"ask"|"library"|"settings">("ask");
  const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[filter,setFilter]=useState("");
  const [reader,setReader]=useState<ReaderFile|null>(null),[detailsId,setDetailsId]=useState("");
  const [pendingImports,setPendingImports]=useState<string[]>([]);
  const polling=useRef(false);
  const refresh=useCallback(async()=>{const value=await snapshot();setData(value);return value;},[]);
  useEffect(()=>{let alive=true;const poll=async()=>{if(polling.current||!alive)return;polling.current=true;try{await refresh();}catch(err){if(alive)setError(errorMessage(err));}finally{polling.current=false;}};void poll();const timer=window.setInterval(()=>void poll(),3000);return()=>{alive=false;window.clearInterval(timer);};},[refresh]);
  async function run(action:()=>Promise<unknown>){setBusy(true);setError("");try{await action();await refresh();}catch(err){setError(errorMessage(err));}finally{setBusy(false);}}
  useEffect(()=>{
    if(!data||!pendingImports.length)return;
    const rows=pendingImports.map(id=>data.jobs.find(job=>job.job_id===id));
    if(rows.some(job=>!job||["queued","running"].includes(job.status)))return;
    setPendingImports([]);
    const versions=rows.flatMap(job=>job?.status==="completed"&&job.result_ref?.startsWith("document_version:")?[job.result_ref.slice(17)]:[]);
    if(versions.length)void run(()=>prepareMvp([...new Set(versions)]));
    else setError("本次文件未能导入，请查看下方失败记录。");
  },[data,pendingImports]);
  async function importFiles(){const result=await importPdf();if(result){setTab("library");setPendingImports("jobs" in result?result.jobs.map(job=>job.job_id):[result.job_id]);}}
  const details=data?.documents.find(doc=>doc.doc_version_id===detailsId);
  const active=data?.jobs.some(job=>["queued","running"].includes(job.status))??false;
  return <div className={`workspace mvp-workspace ${reader&&details?"comparing-document":""}`}>
    <aside className="sidebar"><div className="brand"><span className="brand-mark">R</span><div>RAGSystem<small>本地 PDF 问答</small></div></div>
      <nav aria-label="主导航">{([['ask','问答'],['library','文献'],['settings','设置']] as const).map(([key,label])=><button key={key} className={tab===key?"nav active":"nav"} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      <div className="connection"><span className={data?"status-dot ready":"status-dot"}/>{data?"本地引擎已连接":"正在连接本地引擎"}</div>
    </aside>
    <main><header><div><p className="eyebrow">你的论文，保存在本机</p><h1>{tab==="ask"?"问答":tab==="library"?"文献":"设置"}</h1></div><button className="primary" disabled={busy||active||!data} onClick={()=>void run(importFiles)}>导入 PDF</button></header>
      {error&&<p role="alert" className="job-error">{error}<button onClick={()=>void run(refresh)}>重新连接</button></p>}
      {!data?<section className="panel"><p className="empty">正在准备本地工作区…</p></section>:<>
        {tab==="ask"&&<MvpAsk data={data} onSettings={()=>setTab("settings")}/>}
        {tab==="settings"&&<MvpSettings key={data.workspace?.directory??data.workspace?.label} data={data} onRefresh={refresh} onRead={setReader} onWorkspaceChange={async()=>{setReader(null);setDetailsId("");setPendingImports([]);await refresh();}}/>}
        {tab==="library"&&<>
          <section className="panel"><div className="panel-head"><h2>我的文献（{data.documents.length}）</h2><button disabled={busy||active||!data.documents.length} onClick={()=>void run(()=>prepareMvp(data.documents.map(doc=>doc.doc_version_id)))}>准备问答 / 更新索引</button></div>
            <div className="settings-content"><p>{active||pendingImports.length?"正在保存、解析或更新索引，请查看任务进度。":data.index?.ready?"混合检索已就绪，可以开始提问。":data.documents.length?"文献保存在本机；解析后请在设置中配置 E5 索引。":"导入第一篇 PDF，自动准备可检索的文本。"}</p><label>筛选文献<input aria-label="筛选文献" value={filter} onChange={event=>setFilter(event.target.value)} placeholder="题名、作者或标签"/></label></div>
            <div className="table-wrap"><table><thead><tr><th>文献</th><th>状态</th><th>操作</th></tr></thead><tbody>{data.documents.filter(doc=>[doc.title,...doc.authors,...doc.tags].join(" ").toLowerCase().includes(filter.toLowerCase())).map(doc=><tr key={doc.doc_version_id}><td><strong>{doc.title}</strong><small>{doc.authors.join("，")||"可在详情中填写作者"}</small></td><td>{stateLabels[doc.parse_status]??doc.parse_status}</td><td><button onClick={()=>void run(async()=>setReader(await readDocument(doc.doc_version_id)))}>阅读 PDF</button><button onClick={()=>setDetailsId(doc.doc_version_id)}>详情</button></td></tr>)}</tbody></table></div>
          </section>
          <section className="panel mvp-tasks"><div className="panel-head"><h2>处理进度与失败重试</h2><button onClick={()=>void run(refresh)}>刷新</button></div><ul className="job-list">{data.jobs.slice(0,30).map(job=><li key={job.job_id}><div><strong>{job.type==="import"?`导入 ${job.label??"PDF"}`:job.type==="parse_page"?"解析 PDF":job.type==="embed_batch"?"建立检索索引":job.label==="mvp_prepare"?"准备问答":"后台任务"}</strong>{job.error_code&&<p className="job-error">{errorMessage(job.error_code)}</p>}</div><span>{stateLabels[job.status]??job.status}</span>{["failed","cancelled","retry_wait"].includes(job.status)&&["import","parse_page"].includes(job.type)&&job.attempt_count<job.max_attempts&&<button disabled={busy||active} onClick={()=>void run(()=>retryJob(job.job_id))}>重试</button>}{["queued","running"].includes(job.status)&&<button onClick={()=>void run(()=>cancelJob(job.job_id))}>取消</button>}</li>)}</ul></section>
        </>}
      </>}
    </main>
    {details&&data&&<DocumentDetails minimal document={details} projects={data.projects} onRefresh={refresh} onClose={()=>setDetailsId("")} onOpenPdf={async page=>{const value=await readDocument(details.doc_version_id);setReader({...value,document:{...value.document,page_number:page}});}}/>}
    {reader&&<Suspense fallback={<p>正在打开原文…</p>}><PdfPreview file={reader} onClose={()=>setReader(null)}/></Suspense>}
  </div>;
}
