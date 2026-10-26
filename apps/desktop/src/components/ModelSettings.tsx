import { useState } from "react";
import { chooseOcrModel, chooseDoclingModel, chooseEmbeddingModel, chooseGeneratorModel, errorMessage, type IndexStatus, type GeneratorStatus, type ParsingCandidateStatus } from "../bridge";

export default function ModelSettings({index, generator, ocr, docling, onRefresh, parsingOnly=false}: {index?: IndexStatus; generator?: GeneratorStatus; ocr?: ParsingCandidateStatus; docling?: ParsingCandidateStatus; onRefresh: () => Promise<unknown>; parsingOnly?:boolean}) {
  const [backend, setBackend] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function configure() {
    setBusy(true); setError(""); setMessage("");
    try {if (await chooseEmbeddingModel(backend)) setMessage("索引任务已提交，可在任务与恢复中查看完成或失败状态。"); await onRefresh();}
    catch (err) {setError(errorMessage(err));}
    finally {setBusy(false);}
  }
  return <section className="panel model-settings"><div className="panel-head"><h2>{parsingOnly?"解析候选资源":"本地模型与索引"}</h2><span>{parsingOnly?"仅使用本地已批准资源":index?.ready ? "索引已就绪" : index?.configured ? "需要构建或检查" : "尚未配置"}</span></div><div className="settings-content">
    {!parsingOnly&&<>
    <p>当前接入 multilingual-e5-small 候选。请选择已保存在本机并核对版本的资源目录，应用会校验文件。</p>
    {index?.configured && <p>{index.model} · {index.backend} · {index.indexed_chunks}/{index.visible_chunks} 个片段</p>}
    <label htmlFor="vector-backend">试验后端</label><select id="vector-backend" value={backend} onChange={event => setBackend(event.target.value)}><option value="">请选择候选</option><option value="sqlite-vec">sqlite-vec 候选</option><option value="lancedb">LanceDB 候选</option></select>
    <div className="settings-actions"><button disabled={!backend || busy} onClick={() => void configure()}>选择本地模型并构建索引</button></div>
    <h3>本地问答候选</h3><p>{generator?.configured ? "Qwen2.5-1.5B-Instruct GGUF 已配置；尚未通过科研质量验收。" : "尚未配置生成模型，仍可使用原文摘录与逐篇整理。"}</p><button disabled={busy} onClick={()=>{setBusy(true);setError("");void chooseGeneratorModel().then(async result=>{if(result)setMessage("生成候选加载任务已提交。");await onRefresh();}).catch(err=>setError(errorMessage(err))).finally(()=>setBusy(false));}}>选择或重新校验生成模型</button>
    </>}
    <h3>离线 OCR 候选</h3><p>{ocr?.configured?"eng + chi_sim 已校验；低文本页可显式重解析。OCR 文本仍需核对原件。":"尚未配置；扫描页将明确保留覆盖缺口。"}</p><button disabled={busy} onClick={()=>{setBusy(true);setError("");void chooseOcrModel().then(async result=>{if(result)setMessage("OCR 候选校验任务已提交。");await onRefresh();}).catch(err=>setError(errorMessage(err))).finally(()=>setBusy(false));}}>选择或重新校验 OCR 语言目录</button>
    <h3>布局与表格候选</h3><p>{docling?.configured?"Heron / TableFormer fast 已校验，可在文献详情显式增强解析。表格结构仍需对照原件核对。":"尚未配置布局与表格候选。"}</p><button disabled={busy} onClick={()=>{setBusy(true);setError("");void chooseDoclingModel().then(async result=>{if(result)setMessage("布局与表格候选校验任务已提交。");await onRefresh();}).catch(err=>setError(errorMessage(err))).finally(()=>setBusy(false));}}>选择或重新校验布局与表格目录</button>
    {message && <p role="status">{message}</p>}{error && <p role="alert" className="job-error">{error}</p>}
    <p className="settings-help">{parsingOnly?"配置候选资源后，可在文献详情显式重解析；未配置的能力保持关闭。":"重复构建复用内容与模型指纹相同的持久向量。"}候选试验不代表最终选型或科研质量验收。</p>
  </div></section>;
}
