import {useEffect,useRef,useState} from "react";
import {errorMessage,historyPage,manageConversation,type HistoryPage} from "../bridge";
import Icon from "./Icon";
import {recentDate} from "./uiFormat";

type Item=HistoryPage["items"][number];
export default function ConversationSidebar({history,selectedId,onNew,onOpen,onRefresh,onRemoved,onOlder}:{history:HistoryPage;selectedId:string;onNew:()=>void;onOpen:(id:string)=>void;onRefresh:()=>Promise<unknown>;onRemoved:(id:string)=>void;onOlder:()=>void}) {
 const [menu,setMenu]=useState<string|null>(null),[manager,setManager]=useState<"active"|"archived"|null>(null),[archived,setArchived]=useState<HistoryPage>({items:[],total:0,next_cursor:null});
 const [action,setAction]=useState<{kind:"rename"|"delete";item:Item}|null>(null),[title,setTitle]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const guard=useRef(false),epoch=useRef(0);
 const [archiveLoading,setArchiveLoading]=useState(false),[notice,setNotice]=useState("");
 async function loadArchived(cursor=""){const n=++epoch.current;setArchiveLoading(true);try{const page=await historyPage("archived_conversations",null,cursor);if(n===epoch.current)setArchived(previous=>cursor?{...page,items:[...previous.items,...page.items.filter(item=>!previous.items.some(old=>old.id===item.id))]}:page);}catch(err){setError(errorMessage(err));}finally{if(n===epoch.current)setArchiveLoading(false);}}
 useEffect(()=>{setNotice("");if(manager==="archived")void loadArchived();},[manager]);
 async function apply(item:Item,kind:"rename"|"archive"|"restore"|"delete") {
  if(guard.current)return;guard.current=true;setBusy(true);setError("");
  try{await manageConversation(item.id,kind,kind==="rename"?title:null);setMenu(null);setAction(null);if(kind==="archive"||kind==="delete")onRemoved(item.id);await onRefresh();if(manager==="archived")await loadArchived();if(kind==="restore")setNotice("对话已恢复，可在最近对话中继续打开。");}
  catch(err){setError(errorMessage(err));}finally{guard.current=false;setBusy(false);}
 }
 function confirm(item:Item,kind:"rename"|"delete"){setTitle(item.question);setAction({item,kind});setMenu(null);setError("");}
 function row(item:Item,isArchived=false){return <div className="conversation-row" key={item.id}>
  <button className={`recent-conversation ${selectedId===item.id?"selected":""}`} onClick={()=>{onOpen(item.id);setManager(null);setMenu(null);}} title={item.question}><Icon name="chat" size={20}/><span><strong>{item.question}</strong><small>{recentDate(item.created_at)}</small></span></button>
  {isArchived&&<button className="restore-conversation" disabled={busy} onClick={()=>void apply(item,"restore")}>恢复</button>}
  <button className="conversation-menu-toggle" aria-label={`管理对话：${item.question}`} aria-expanded={menu===item.id} onClick={()=>setMenu(menu===item.id?null:item.id)}>…</button>
  {menu===item.id&&<div className="conversation-menu" role="menu"><button role="menuitem" disabled={busy} onClick={()=>confirm(item,"rename")}>重命名</button><button role="menuitem" disabled={busy} onClick={()=>void apply(item,isArchived?"restore":"archive")}>{isArchived?"恢复归档":"归档"}</button><button role="menuitem" disabled={busy} onClick={()=>confirm(item,"delete")}>删除</button></div>}
 </div>;}
 return <section className="sidebar-history"><div className="sidebar-history-heading"><h2>最近对话</h2><button className="icon-button" onClick={onNew} aria-label="新会话"><Icon name="plus" size={18}/></button></div>
 <div className="conversation-management"><button onClick={()=>{setManager("active");setMenu(null);}}>管理对话</button><button onClick={()=>{setManager("archived");setMenu(null);}}>已归档对话</button></div>
 <div className="recent-conversations">{!history.items.length&&<p className="history-empty">开始一次新的文献探索。</p>}{history.items.map(item=>row(item))}{history.next_cursor&&<button className="history-more" onClick={onOlder}>更早的会话</button>}</div>
 {error&&<p role="alert" className="job-error">{error}</p>}
 {manager&&<div className="conversation-modal-backdrop"><section className="conversation-dialog" role="dialog" aria-modal="true" aria-label={manager==="archived"?"已归档对话":"管理对话"}><header><h2>{manager==="archived"?"已归档对话":"管理对话"}</h2><button disabled={busy} onClick={()=>{setManager(null);setMenu(null);}}>关闭</button></header><div className="conversation-manager-tabs"><button disabled={busy} aria-pressed={manager==="active"} onClick={()=>{setManager("active");setMenu(null);}}>最近对话</button><button disabled={busy} aria-pressed={manager==="archived"} onClick={()=>{setManager("archived");setMenu(null);}}>已归档对话</button></div>{manager==="archived"&&<p>点击“恢复”将对话移回最近列表，历史消息和引用均保留。归档的是对话，文献原件仍在文献库。</p>}{notice&&<p role="status">{notice}</p>}{manager==="archived"&&archiveLoading&&<p role="status">正在读取已归档对话…</p>}{error&&<p role="alert" className="job-error">{error}</p>}<div className="conversation-dialog-list">{(manager==="archived"?archived:history).items.map(item=>row(item,manager==="archived"))}{!(manager==="archived"?archived:history).items.length&&!archiveLoading&&<p>暂无对话</p>}{manager==="archived"&&archived.next_cursor&&<button onClick={()=>void loadArchived(archived.next_cursor!)}>加载更早归档</button>}{manager==="active"&&history.next_cursor&&<button onClick={onOlder}>更早的会话</button>}</div></section></div>}
 {action&&<div className="conversation-modal-backdrop confirmation"><form className="conversation-dialog" role="alertdialog" aria-modal="true" aria-label={action.kind==="delete"?"删除对话确认":"重命名对话"} onSubmit={event=>{event.preventDefault();void apply(action.item,action.kind);}}><h2>{action.kind==="delete"?"删除对话？":"重命名对话"}</h2>{action.kind==="delete"?<p>删除后，“{action.item.question}”及其历史问答、引用和结论记录将被删除，无法在应用内恢复。文献原件、解析结果、向量索引和其他对话不受影响。</p>:<label>对话名称<input aria-label="对话名称" autoFocus required maxLength={160} value={title} onChange={event=>setTitle(event.target.value)}/></label>}{error&&<p role="alert" className="job-error">{error}</p>}<footer><button type="button" disabled={busy} onClick={()=>setAction(null)}>取消</button><button className={action.kind==="delete"?"danger-button":"primary"} disabled={busy}>{action.kind==="delete"?"确认删除":"保存名称"}</button></footer></form></div>}
 </section>;
}
