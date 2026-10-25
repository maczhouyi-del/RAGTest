import {useState} from "react";
import {chooseEmbeddingModel,chooseGeneratorModel,errorMessage,prepareMvp,type Snapshot,type ReaderFile} from "../bridge";
import GenerationConnections from "./GenerationConnections";
import BackupSettings from "./BackupSettings";
import ModelSettings from "./ModelSettings";
import LifecycleSettings from "./LifecycleSettings";
import IdentitySettings from "./IdentitySettings";

export default function MvpSettings({data,onRefresh,onWorkspaceChange,onRead}:{data:Snapshot;onRefresh:()=>Promise<unknown>;onWorkspaceChange:()=>Promise<unknown>;onRead:(file:ReaderFile)=>void}){
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  async function run(action:()=>Promise<unknown>){setBusy(true);setError("");try{const result=await action();if(result!==null)setMessage("任务已提交，可在文献页查看进度。");await onRefresh();}catch(err){setError(errorMessage(err));}finally{setBusy(false);}}
  return <div className="mvp-settings">
    <section className="panel"><div className="panel-head"><h2>模型与索引</h2><span>{data.index?.ready?"检索已就绪":"等待准备"}</span></div><div className="settings-content">
      <h3>Embedding</h3><p>multilingual-E5-small · 本机计算并持久保存。更换生成模型不会重新计算向量。</p><button disabled={busy||!data.documents.length} onClick={()=>void run(()=>chooseEmbeddingModel("sqlite-vec"))}>选择 E5 目录并建立索引</button>
      {data.index?.configured&&<button disabled={busy} onClick={()=>void run(()=>prepareMvp(data.documents.map(doc=>doc.doc_version_id)))}>更新本地索引</button>}
      <p>{data.index?.indexed_chunks??0} 个片段已索引 · {data.index?.visible_chunks??0} 个当前片段</p>
      <h3>本地生成模型</h3><p>{data.generator?.configured?"本地 Qwen 已配置":"可选：配置本地 Qwen 以生成有引用的回答。"}</p><button disabled={busy} onClick={()=>void run(chooseGeneratorModel)}>选择本地生成模型目录</button>
      {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="job-error">{error}</p>}
    </div></section>
    <GenerationConnections/>
    <section className="panel"><div className="settings-content"><h2>本地资料目录</h2><p className="workspace-path">{data.workspace?.directory??data.workspace?.label}</p><p>更换资料工作区请使用下方备份与恢复流程。</p></div></section>
    <BackupSettings workspace={data.workspace} onChange={onWorkspaceChange}/>
    <details className="panel mvp-advanced"><summary>高级设置</summary><div className="settings-content"><p>当前资料工作区：{data.workspace?.label}</p><p>索引后端：{data.index?.backend??"未配置"}；索引版本：{data.index?.generation??"尚未建立"}。</p><ModelSettings index={data.index} generator={data.generator} ocr={data.ocr} docling={data.docling} onRefresh={onRefresh}/><IdentitySettings documents={data.documents} onRefresh={onRefresh}/><LifecycleSettings documents={data.documents} onRead={onRead} onRefresh={onRefresh}/></div></details>
  </div>;
}
