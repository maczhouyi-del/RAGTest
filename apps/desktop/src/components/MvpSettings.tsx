import {useState} from "react";
import {chooseEmbeddingModel,chooseGeneratorModel,errorMessage,prepareMvp,type GenerationConnection,type Snapshot,type ReaderFile} from "../bridge";
import GenerationConnections from "./GenerationConnections";
import BackupSettings from "./BackupSettings";
import ModelSettings from "./ModelSettings";
import LifecycleSettings from "./LifecycleSettings";
import IdentitySettings from "./IdentitySettings";
import Icon,{type IconName} from "./Icon";
import {bytesLabel} from "./uiFormat";

const categories=[
  {id:"models",name:"模型服务",icon:"monitor",help:"本地生成模型与已保存的 API 连接"},
  {id:"retrieval",name:"检索与索引",icon:"database",help:"Embedding、检索策略与持久索引"},
  {id:"parsing",name:"文献解析",icon:"file",help:"离线 OCR、布局与表格候选"},
  {id:"workspace",name:"工作区与数据",icon:"folder",help:"本地资料、文献身份与可见性"},
  {id:"backups",name:"备份与恢复",icon:"archive",help:"校验备份并恢复到全新工作区"},
  {id:"diagnostics",name:"高级与诊断",icon:"settings",help:"当前引擎、配置修订与索引状态"},
] as const;
type Category=typeof categories[number]["id"];

export default function MvpSettings({data,providers,model,strategy,onStrategy,onRefresh,onWorkspaceChange,onRead}: {
  data:Snapshot;providers:GenerationConnection[];model:string;strategy:string;onStrategy:(value:string)=>void;onRefresh:()=>Promise<unknown>;onWorkspaceChange:()=>Promise<unknown>;onRead:(file:ReaderFile)=>void;
}) {
  const [category,setCategory]=useState<Category>("models");
  const [mode,setMode]=useState<"local"|"deepseek"|"openai"|"custom"|"magpie">("local");
  const [backend,setBackend]=useState(data.index?.backend??"sqlite-vec");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  const originalBytes=[...new Map(data.documents.map(doc=>[doc.file_sha256,doc.size_bytes])).values()].reduce((sum,value)=>sum+value,0);
  const selected=providers.find(provider=>provider.id===model);
  const currentModel=model==="extractive"?"原文摘录":model==="local"?String(data.generator?.fingerprint?.model??"本地生成模型尚未配置"):selected?`${selected.name} · ${selected.model}`:"连接不可用";
  const active=categories.find(item=>item.id===category)!;
  async function run(action:()=>Promise<unknown>,success="任务已提交，可在文献页查看进度。") {setBusy(true);setError("");setMessage("");try{const result=await action();if(result!==null)setMessage(success);await onRefresh();}catch(err){setError(errorMessage(err));}finally{setBusy(false);}}
  return <section className="settings-page settings-categories">
    <header className="page-heading settings-heading"><div><h1>设置</h1><p>配置模型、检索与本地工作区</p></div></header>
    <div className="settings-layout">
      <nav className="settings-navigation" aria-label="设置分类">{categories.map(item=><button key={item.id} type="button" aria-current={category===item.id?"page":undefined} aria-controls="settings-category-content" onClick={()=>setCategory(item.id)}><Icon name={item.icon}/>{item.name}</button>)}</nav>
      <div className="settings-category-content" id="settings-category-content" role="region" aria-label={active.name} data-category={category}>
        <header className="settings-category-heading"><h2>{active.name}</h2><p>{active.help}</p></header>
        {category==="models"&&<section className="panel settings-card generation-card"><div className="settings-card-heading"><span className="section-icon"><Icon name="settings" size={24}/></span><div><h2>生成模型</h2><p>在问答页选择已配置的模型；切换生成模型不重算 Embedding。</p></div></div>
          <div className="model-mode-tabs" role="tablist" aria-label="生成模型类型">{[{id:"local",name:"本地模型",icon:"monitor",help:"在本地运行，数据留在本机"},{id:"deepseek",name:"DeepSeek",icon:"cloud",help:"配置 DeepSeek API"},{id:"openai",name:"OpenAI",icon:"cloud",help:"配置 OpenAI API"},{id:"custom",name:"自定义兼容接口",icon:"cloud",help:"配置其他兼容服务"},{id:"magpie",name:"Magpie",icon:"bird",help:"连接可选的本机网关"}].map(item=><button key={item.id} type="button" role="tab" aria-selected={mode===item.id} onClick={()=>setMode(item.id as typeof mode)}><Icon name={item.icon as IconName} size={26}/><span><strong>{item.name}</strong><small>{item.help}</small></span></button>)}</div>
          {mode==="local"?<div className="local-model-form"><label>本地生成模型<span className="readonly-field"><Icon name="monitor"/>{String(data.generator?.fingerprint?.model??"尚未配置本地生成模型")}</span></label><div className="model-resource-status"><span className={`status-pill ${data.generator?.configured?"success":"pending"}`}><span className="status-dot"/>{data.generator?.configured?"资源已配置":"尚未配置"}</span><button disabled={busy} onClick={()=>void run(chooseGeneratorModel)}><Icon name="folder"/>选择本地生成模型目录</button></div><p className="form-help">仅使用已批准的本地候选资源，不自动下载。未配置时可以先使用原文摘录模式；模型回答仍需核查。</p></div>:<GenerationConnections key={mode} initialKind={mode} onSaved={onRefresh}/>}
          <details className="settings-help-details"><summary>如何选择模型？</summary><p>本地模型在本机计算。API 连接启用文献问答后会发送当前问题、最近最多三轮有界上下文及本轮检索片段，可能产生费用。可随时关闭授权；重启后需重新输入密钥。Magpie 是可选网关，可能转发云端，不会读取订阅凭据。</p></details>
          <p className="settings-current-model">当前问答方式：{currentModel}</p>
        </section>}
        {category==="retrieval"&&<section className="panel settings-card"><div className="settings-card-heading"><span className="section-icon"><Icon name="database" size={24}/></span><div><h2>检索配置</h2><p>设置文献检索使用的向量模型和索引方式。</p></div></div><div className="retrieval-form"><label>Embedding 模型<select aria-label="Embedding 模型" value="e5-small" disabled><option value="e5-small">intfloat/multilingual-e5-small（候选）</option></select><small className={data.index?.configured?"text-green":"text-muted"}><span className="status-dot"/>{data.index?.configured?"已配置":"未配置"}</small><p>{data.index?.model??"用于将文献和问题转为向量表示。"}</p></label><label>向量索引后端<select aria-label="向量索引后端" value={backend} onChange={e=>setBackend(e.target.value)}><option value="sqlite-vec">sqlite-vec</option><option value="lancedb">LanceDB（候选）</option></select><p>用于存储和检索文献向量，保留候选对照。</p></label><label>默认检索策略<select aria-label="默认检索策略" value={strategy} onChange={e=>onStrategy(e.target.value)}><option value="hybrid">混合检索（向量 + 关键词）</option><option value="keyword">关键词检索</option><option value="vector_exact">向量检索</option></select><p>索引未就绪时，仅提供关键词检索。</p></label></div><div className="retrieval-actions"><span>{data.index?.indexed_chunks??0} 个片段已索引 · {data.index?.visible_chunks??0} 个当前片段</span><button disabled={busy||!data.documents.length} onClick={()=>void run(()=>chooseEmbeddingModel(backend))}><Icon name="folder"/>选择 E5 目录并建立索引</button>{data.index?.configured&&<button disabled={busy} onClick={()=>void run(()=>prepareMvp(data.documents.map(doc=>doc.doc_version_id)))}><Icon name="refresh"/>更新本地索引</button>}</div><p className="form-help">当前已发布后端：{data.index?.backend??"未建立"} · 索引状态：{data.index?.ready?"就绪":data.index?.configured?"需更新":"未配置"}</p></section>}
        {category==="parsing"&&<ModelSettings parsingOnly ocr={data.ocr} docling={data.docling} onRefresh={onRefresh}/>}
        {category==="workspace"&&<><section className="panel settings-card workspace-card"><div className="settings-card-heading"><span className="section-icon"><Icon name="folder" size={24}/></span><div><h2>本地资料</h2><p>PDF 原件按 SHA-256 保存并去重。</p></div></div><div className="workspace-row"><label htmlFor="workspace-directory">当前工作区路径</label><input id="workspace-directory" readOnly value={data.workspace?.directory??data.workspace?.label??"正在读取"}/><button onClick={()=>setCategory("backups")}><Icon name="folder" size={17}/>通过恢复切换</button></div><div className="workspace-row"><span>PDF 原件体积</span><span className="storage-description">{bytesLabel(originalBytes)}<small>按原件 SHA 去重，仅统计当前文献原件</small></span></div>{data.workspace?.warning&&<p role="alert">{data.workspace.warning}</p>}</section><IdentitySettings documents={data.documents} onRefresh={onRefresh}/><LifecycleSettings documents={data.documents} onRead={onRead} onRefresh={onRefresh}/></>}
        {category==="backups"&&<><BackupSettings workspace={data.workspace} onChange={onWorkspaceChange}/><p className="workspace-backup-hint"><Icon name="info" size={15}/>备份包含原件、持久向量和配置；模型权重单独管理，恢复时创建全新副本。</p></>}
        {category==="diagnostics"&&<section className="panel settings-card"><div className="settings-card-heading"><span className="section-icon"><Icon name="settings" size={24}/></span><div><h2>当前运行状态</h2><p>数据来自当前工作区与本地引擎。</p></div><button disabled={busy} onClick={()=>void run(onRefresh,"状态已更新。")}><Icon name="refresh"/>刷新状态</button></div><dl className="settings-diagnostics">{[{name:"引擎状态",value:data.health.status==="ready"?"就绪":data.health.status},{name:"引擎版本",value:data.health.sidecar_version},{name:"数据库版本",value:data.health.schema_version},{name:"当前问答方式",value:currentModel},{name:"Embedding 模型",value:data.index?.model??"未配置"},{name:"已发布索引后端",value:data.index?.backend??"未建立"},{name:"索引版本",value:data.index?.generation??"未建立"},{name:"索引状态",value:data.index?.ready?"就绪":data.index?.configured?"需更新":"未配置"}].map(item=><div key={item.name}><dt>{item.name}</dt><dd>{item.value}</dd></div>)}</dl><h3>已保存的模型连接</h3>{providers.length?<ul className="settings-provider-status">{providers.map(provider=><li key={provider.id}><strong>{provider.name} · {provider.model}</strong><span>配置修订 {provider.revision} · {provider.document_qa_enabled?"文献问答已启用":"文献问答未启用"} · {provider.configured?"会话凭据或无需认证配置可用":"需重新输入凭据"}</span></li>)}</ul>:<p className="form-help">尚未保存连接。</p>}<details className="settings-help-details"><summary>引擎能力与限制</summary><p>{data.health.capabilities.join(" · ")||"暂无能力声明"}</p>{data.health.disabled_reasons.map(reason=><p key={reason}>{reason}</p>)}</details></section>}
        {message&&<p role="status" className="feedback success-feedback">{message}</p>}{error&&<p role="alert" className="job-error">{error}</p>}
      </div>
    </div>
  </section>;
}
