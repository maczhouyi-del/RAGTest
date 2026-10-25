import type {Snapshot} from "../bridge";
import Icon, {type IconName} from "./Icon";

export default function Welcome({data, busy, onImport, onIndex, onModels,modelConfigured}: {data:Snapshot;modelConfigured?:boolean; busy:boolean; onImport:()=>void; onIndex:()=>void; onModels:()=>void}) {
  const steps: {title:string; icon:IconName; description:string; action:string; help:string; click:()=>void}[] = [
    {title:"导入 PDF 文献",icon:"upload",description:"批量选择你的研究论文，自动保存原件、解析内容，提取可追溯的文本片段。",action:"导入文件",help:"支持本机 PDF 批量选择",click:onImport},
    {title:"建立检索索引",icon:"database",description:"使用本地 multilingual-E5-small，为文献建立持久向量索引，结合关键词找到相关证据。",action:"选择目录并建立索引",help:"本地计算 · 已有向量按指纹复用",click:onIndex},
    {title:"选择问答模型",icon:"robot",description:"配置本地模型或 API 连接，基于检索到的原文进行问答，并随时回到 PDF 核查。",action:"配置模型",help:"支持本地模型 / API / Magpie",click:onModels},
  ];
  return <section className="welcome-page" aria-label="欢迎使用">
    <div className="welcome-intro"><div><h1>欢迎使用 <span>RAGSystem</span></h1><h2>只需三步，即可开始与你的 PDF 文献对话</h2><p>导入你的研究论文，建立本地检索索引，选择合适的问答模型，<br className="wide-only"/>即可基于文献内容进行问答、总结与原文核查。</p></div>
      <div className="welcome-art" aria-hidden="true"><div className="art-halo"/><div className="art-paper paper-back"><i/><i/><i/><i/><i/></div><div className="art-paper paper-front"><b>PDF</b><i/><i/><i/><i/></div><div className="art-answer"><i/><i/><i/></div><div className="art-bot"><Icon name="robot" size={48}/></div></div>
      <div className="welcome-motto"><Icon name="graduate" size={28}/><span>让每一篇论文，都能成为<br/>你思考的起点。</span></div>
    </div>
    <div className="welcome-steps">{steps.map((step,index)=><article className="welcome-step" key={step.title}><span className="step-number">{index+1}</span><div className={`step-art step-art-${index}`}><Icon name={step.icon} size={44}/></div><h3>{step.title}</h3><p>{step.description}</p><button className="primary" disabled={busy||index===1&&!data.documents.length} onClick={step.click}><Icon name={index===0?"folder":index===1?"database":"settings"}/>{step.action}</button><small>{step.help}</small></article>)}</div>
    <div className="welcome-values">{[{icon:"shield",title:"数据安全，默认本地存储",text:"论文原件保存于本地工作区，不自动上传到外部服务器。"},{icon:"lock",title:"可控的隐私策略",text:"只有你明确允许本次发送后，问题与检索片段才会发送给所选服务。"},{icon:"file",title:"学术导向的设计",text:"引用关联真实文献与页码，帮助你对照原文检查回答。"}].map(item=><article key={item.title}><span className="round-icon"><Icon name={item.icon as IconName} size={28}/></span><div><h3>{item.title}</h3><p>{item.text}</p></div></article>)}</div>
    <div className="welcome-checklist"><Icon name="list" size={30}/><div><h3>开始前的准备</h3><p>按顺序完成以下步骤，开始你的文献问答之旅。</p></div><div className="checklist-items">{[{title:"文献",icon:"file",ready:data.documents.length>0,text:data.documents.length?`${data.documents.length} 篇已导入`:"未导入"},{title:"索引",icon:"database",ready:!!data.index?.ready,text:data.index?.ready?"已就绪":"未建立"},{title:"模型",icon:"settings",ready:modelConfigured??!!data.generator?.configured,text:(modelConfigured??data.generator?.configured)?"已配置":"可先使用原文摘录"}].map((item,index)=><div key={item.title}><span className="checklist-number">{index+1}</span><Icon name={item.icon as IconName}/><span>{item.title}<small className={item.ready?"text-green":"text-muted"}>{item.text}</small></span></div>)}</div></div>
  </section>;
}
