import {useCallback,useEffect,useRef,useState} from "react";
import {createConversation,errorMessage,generationConnections,historyPage,importPdf,parseDocument,prepareMvp,readDocument,restartEngine,snapshot,type DocumentRow,type GenerationConnection,type HistoryPage,type ReaderFile,type Snapshot} from "./bridge";
import MvpAsk from "./components/MvpAsk";
import MvpLibrary from "./components/MvpLibrary";
import MvpSettings from "./components/MvpSettings";
import DocumentDetails from "./components/DocumentDetails";
import Welcome from "./components/Welcome";
import SourceWorkspace,{type ReadingContext} from "./components/SourceWorkspace";
import Icon from "./components/Icon";
import ConversationSidebar from "./components/ConversationSidebar";

type Tab="ask"|"library"|"settings";
export default function App() {
  const [tab,setTab]=useState<Tab>("ask");
  const [data,setData]=useState<Snapshot|null>(null),[providers,setProviders]=useState<GenerationConnection[]>([]);
  const [history,setHistory]=useState<HistoryPage>({items:[],total:0,next_cursor:null});
  const [selectedConversationId,setSelectedConversationId]=useState("");
  const [selected,setSelected]=useState(""),[model,setModel]=useState("extractive"),[strategy,setStrategy]=useState("hybrid");
  const [reader,setReader]=useState<{file:ReaderFile;context:ReadingContext;returnTo:Tab}|null>(null),[detailsId,setDetailsId]=useState("");
  const [error,setError]=useState(""),[busy,setBusy]=useState(false),[pendingImports,setPendingImports]=useState<string[]>([]);
  const recovering=useRef(false),creating=useRef(false);
  const [creatingConversation,setCreatingConversation]=useState(false);
  const [connected,setConnected]=useState(false);
  const polling=useRef(false),request=useRef(0),workspace=useRef<string|null>(null);
  const refresh=useCallback(async()=>{
    const epoch=++request.current;
    const [value,connections,page]=await Promise.all([snapshot(),generationConnections(),historyPage("conversations",null,"")]);
    if(epoch!==request.current)return value;
    const root=value.workspace?.directory??value.workspace?.label??"default";
    const changed=workspace.current!==null&&workspace.current!==root;workspace.current=root;
    setConnected(true);setData(value);setProviders(connections.providers);setModel(current=>current==="local"||current==="extractive"||connections.providers.some(item=>item.id===current)?current:"extractive");
    setHistory(previous=>!changed&&previous.items.length>30?{...page,items:[...page.items,...previous.items.filter(old=>!page.items.some(item=>item.id===old.id))]}:page);
    if(changed){setSelectedConversationId("");setSelected("");setReader(null);setDetailsId("");setPendingImports([]);setModel("extractive");}
    return value;
  },[]);
  useEffect(()=>{let alive=true;const poll=async()=>{if(polling.current||recovering.current||!alive)return;polling.current=true;try{await refresh();}catch(err){if(alive){setConnected(false);setError(errorMessage(err));}}finally{polling.current=false;}};void poll();const timer=window.setInterval(()=>void poll(),3000);return()=>{alive=false;window.clearInterval(timer);};},[refresh]);
  async function run(action:()=>Promise<unknown>) {setBusy(true);setError("");try{await action();await refresh();}catch(err){setError(errorMessage(err));}finally{setBusy(false);}}
  async function reconnect(){if(recovering.current)return;recovering.current=true;setBusy(true);setError("");try{await restartEngine();await refresh();}catch(err){setConnected(false);setError(errorMessage(err));}finally{recovering.current=false;setBusy(false);}}
  useEffect(()=>{
    if(!data||!pendingImports.length)return;
    const rows=pendingImports.map(id=>data.jobs.find(job=>job.job_id===id));
    if(rows.some(job=>!job||["queued","running"].includes(job.status)))return;
    setPendingImports([]);
    const versions=rows.flatMap(job=>job?.status==="completed"&&job.result_ref?.startsWith("document_version:")?[job.result_ref.slice(17)]:[]);
    if(versions.length)void run(()=>prepareMvp([...new Set(versions)]));else setError("本次文件未能导入，请在文献页查看失败记录。");
  },[data,pendingImports]);
  async function importFiles(){const result=await importPdf();if(result){setReader(null);setTab("library");setPendingImports("jobs" in result?result.jobs.map(job=>job.job_id):[result.job_id]);}}
  function navigate(next:Tab){setReader(null);setTab(next);}
  function newConversation(){if(creating.current)return;creating.current=true;setCreatingConversation(true);void run(async()=>{const conversation=await createConversation();setSelectedConversationId(conversation.id);setSelected("");setReader(null);setTab("ask");}).finally(()=>{creating.current=false;setCreatingConversation(false);});}
  function openFile(file:ReaderFile,context?:ReadingContext){const id="anchor" in file?file.anchor.doc_version_id:file.document.doc_version_id;const doc=data?.documents.find(item=>item.doc_version_id===id);setReader({file,context:context??{title:doc?.title??("document" in file?file.document.title:"引用文献"),authors:doc?.authors??[],year:doc?.year??null},returnTo:context?.evidence?"ask":tab});}
  async function read(doc:DocumentRow,page=1){const file=await readDocument(doc.doc_version_id);openFile({...file,document:{...file.document,page_number:page}},{title:doc.title,authors:doc.authors,year:doc.year});}
  const details=data?.documents.find(doc=>doc.doc_version_id===detailsId);
  const active=data?.jobs.some(job=>["queued","running"].includes(job.status))??false;
  const welcome=!!data&&!data.documents.length&&!selectedConversationId;
  return <div className="workspace studio">
    <aside className="studio-sidebar"><button className="studio-brand" onClick={newConversation} aria-label="RAGSystem 问答首页"><span className="book-logo"><Icon name="book" size={23}/></span><span>RAGSystem</span></button>
      <nav aria-label="主导航">{([{id:"ask",label:"问答",icon:"chat"},{id:"library",label:"文献",icon:"file"},{id:"settings",label:"设置",icon:"settings"}] as const).map(item=><button key={item.id} className={`studio-nav-button ${tab===item.id?"active":""}`} onClick={()=>navigate(item.id)} aria-current={tab===item.id?"page":undefined}><Icon name={item.icon} size={21}/>{item.label}</button>)}</nav>
      <ConversationSidebar history={history} selectedId={selectedConversationId} onNew={newConversation} onOpen={id=>{setReader(null);setTab("ask");setSelectedConversationId(id);setSelected("");}} onRefresh={async()=>{setHistory({items:[],total:0,next_cursor:null});await refresh();}} onRemoved={id=>{setHistory(previous=>({...previous,items:previous.items.filter(item=>item.id!==id)}));if(selectedConversationId===id){setSelectedConversationId("");setSelected("");setReader(null);setTab("ask");}}} onOlder={()=>void run(async()=>{const page=await historyPage("conversations",null,history.next_cursor!);setHistory(previous=>({...page,items:[...previous.items,...page.items.filter(item=>!previous.items.some(old=>old.id===item.id))]}));})}/>
      <div className="connection sidebar-connection"><span className={connected?"online-dot":"offline-dot"}/>{connected&&data?data.health.status==="degraded"?"本地引擎部分可用":"本地引擎已连接":"本地引擎未连接"}</div>
    </aside>
    <main className="studio-main">
      {error&&<div role="alert" className="app-feedback"><Icon name="info" size={18}/><span>{error}</span><button disabled={busy} onClick={()=>void reconnect()}>重新连接</button><button disabled={busy} onClick={()=>void run(refresh)}>刷新状态</button><button className="icon-button" aria-label="关闭提示" onClick={()=>setError("")}><Icon name="close" size={16}/></button></div>}
      {!data?<div className="engine-loading"><Icon name="book" size={42}/><h1 role="status">正在打开工作区…</h1></div>:<>
        {reader&&<SourceWorkspace key={"anchor" in reader.file?reader.file.anchor.source_anchor_id:reader.file.document.doc_version_id} file={reader.file} context={reader.context} returnLabel={reader.returnTo==="settings"?"返回设置":reader.returnTo==="ask"?"返回问答":"返回文献"} onClose={()=>{setTab(reader.returnTo);setReader(null);}} onSaved={refresh}/>}
        <div hidden={!!reader||tab!=="ask"} className="ask-view">
          {welcome?<Welcome busy={busy||active} onImport={()=>void run(importFiles)}/>:<MvpAsk key={data.workspace?.directory??"workspace"} data={data} creatingConversation={creatingConversation} providers={providers} model={model} onModel={setModel} strategy={strategy} onStrategy={setStrategy} conversationId={selectedConversationId} onConversation={setSelectedConversationId} selectedId={selected} onSelected={setSelected} onCreated={refresh} onSettings={()=>navigate("settings")} onImport={()=>void run(importFiles)} onRead={openFile}/>}
        </div>
        <div hidden={!!reader||tab!=="library"} className="library-view"><MvpLibrary key={data.workspace?.directory??"workspace"} data={data} busy={busy} onImport={()=>void run(importFiles)} onPrepare={ids=>void run(()=>prepareMvp(ids))} onRead={(doc,page)=>void run(()=>read(doc,page))} onDetails={setDetailsId} onReparse={id=>void run(()=>parseDocument(id))} onAction={action=>void run(action)}/></div>
        {!reader&&tab==="settings"&&<MvpSettings key={data.workspace?.directory??"workspace"} data={data} providers={providers} model={model} strategy={strategy} onStrategy={setStrategy} onRefresh={refresh} onRead={openFile} onWorkspaceChange={async()=>{request.current++;setReader(null);setDetailsId("");setPendingImports([]);await refresh();}}/>}
      </>}
    </main>
    <div className="overlay-host" hidden={!!reader}>{details&&data&&<DocumentDetails minimal document={details} projects={data.projects} onRefresh={refresh} onClose={()=>setDetailsId("")} onOpenPdf={async page=>{const value=await readDocument(details.doc_version_id);openFile({...value,document:{...value.document,page_number:page}});}}/>}</div>
  </div>;
}
