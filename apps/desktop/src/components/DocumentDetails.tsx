import { useEffect, useRef, useState, type FormEvent } from "react";
import { errorMessage, parseDocument, inspectDocumentParse, type ParseDiagnostics, setProjectDocument, updateMetadata, type DocumentRow, type Project } from "../bridge";

import TableCandidates from "./TableCandidates";

export default function DocumentDetails({document, projects, onRefresh, onClose, onOpenPdf, minimal=false}: {
  minimal?: boolean; document: DocumentRow; projects: Project[]; onOpenPdf:(page:number)=>Promise<void>; onRefresh: () => Promise<unknown>; onClose: () => void;
}) {
  const [diagnostics,setDiagnostics]=useState<ParseDiagnostics|null>(null);
  useEffect(()=>{let alive=true;void inspectDocumentParse(document.doc_version_id).then(result=>{if(alive)setDiagnostics(result);}).catch(err=>{if(alive)setError(errorMessage(err));});return()=>{alive=false;};},[document.doc_version_id,document.parse_status]);
  useEffect(()=>{let alive=true;const timer=window.setInterval(()=>{void inspectDocumentParse(document.doc_version_id).then(result=>{if(alive)setDiagnostics(result);}).catch(err=>{if(alive)setError(errorMessage(err));});},2000);return()=>{alive=false;window.clearInterval(timer);};},[document.doc_version_id]);
  const warningPages=diagnostics?.pages.filter(page=>Boolean(page.error_code)||diagnostics.needs_ocr_pages.includes(page.page_number)).map(page=>page.page_number)??[];
  const [singlePage,setSinglePage]=useState(false);
  const [targetPage,setTargetPage]=useState(1);
  const selection=singlePage?[targetPage]:null;
  const validPage=!singlePage||(Number.isInteger(targetPage)&&targetPage>=1&&targetPage<=(diagnostics?.pages.length??0));
  const [title, setTitle] = useState(document.title);
  const [authors, setAuthors] = useState(document.authors.join("\n"));
  const [year, setYear] = useState(document.year?.toString() ?? "");
  const [doi, setDoi] = useState(document.doi ?? "");
  const [venue, setVenue] = useState(document.venue);
  const [tags, setTags] = useState(document.tags.join("，"));
  const revision = useRef(document.metadata_revision);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [membershipPending, setMembershipPending] = useState<Record<string, boolean>>({});

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await updateMetadata(document.document_id, {expected_revision: revision.current,
        title: title.trim(), authors: authors.split(/\n/).map(value => value.trim()).filter(Boolean),
        year: year ? Number(year) : null, doi: doi.trim() || null, venue: venue.trim(),
        tags: tags.split(/[,，]/).map(value => value.trim()).filter(Boolean)});
      await onRefresh(); onClose();
    } catch (err) {setError(errorMessage(err));}
    finally {setBusy(false);}
  }
  async function membership(project: Project, linked: boolean) {
    setBusy(true); setError(""); setMembershipPending({[project.id]: linked});
    try {await setProjectDocument(project.id, document.document_id, linked); await onRefresh();}
    catch (err) {setError(errorMessage(err));}
    finally {setMembershipPending({}); setBusy(false);}
  }

  return <section className="details-overlay" role="dialog" aria-modal="true" aria-labelledby="document-details-title"
    onKeyDown={event => {if (event.key === "Escape" && !busy) onClose();}}>
    <header><div><h2 id="document-details-title">文献详情</h2><small>元数据由人工维护，修改不会改变 PDF 原件。</small></div><button disabled={busy} onClick={onClose}>关闭</button></header>
    {error && <p role="alert" className="job-error">{error}</p>}
    {document.duplicate_candidates.length > 0 && <p className="duplicate-notice">另有 {document.duplicate_candidates.length} 篇文献使用相同 DOI，请人工核对版本。系统未自动合并。</p>}
    <form onSubmit={event => void save(event)} className="metadata-form">
      <label>题名<input value={title} onChange={event => setTitle(event.target.value)} maxLength={1000} required autoFocus /></label>
      <label>作者（每行一位）<textarea aria-label="作者（每行一位）" value={authors} onChange={event => setAuthors(event.target.value)} rows={3} maxLength={10000} /></label>
      <div className="metadata-row"><label>年份<input type="number" min={1000} max={2999} value={year} onChange={event => setYear(event.target.value)} /></label><label>期刊或会议<input value={venue} onChange={event => setVenue(event.target.value)} maxLength={500} /></label></div>
      <label>DOI<input value={doi} onChange={event => setDoi(event.target.value)} maxLength={300} placeholder="10.xxxx/… 或 https://doi.org/…" /></label>
      <label>标签（逗号分隔）<input value={tags} onChange={event => setTags(event.target.value)} maxLength={3000} /></label>
      <button className="primary" disabled={busy || !title.trim()}>{busy ? "保存中…" : "保存元数据"}</button>
    </form>
    <details className="paper-advanced" open={minimal?undefined:true}><summary>高级解析与表格核对</summary>
    <fieldset className="project-memberships" disabled={busy}><legend>所属项目</legend>
      {projects.length ? projects.map(project => <label key={project.id}><input type="checkbox" checked={membershipPending[project.id] ?? document.project_ids.includes(project.id)} onChange={event => void membership(project, event.target.checked)} />{project.name}</label>) : <p>当前没有项目关联；MVP 默认使用整个资料库。</p>}
    </fieldset>
    <section className="page-parse-scope"><h3>本次解析范围</h3><label><input type="checkbox" checked={singlePage} disabled={!diagnostics?.pages.length} onChange={e=>setSinglePage(e.target.checked)}/>只更新指定页（未改动页的引用与表格复核保留）</label>{singlePage&&<label>页码<input aria-label="指定重解析页码" type="number" min={1} max={diagnostics?.pages.length??1} value={targetPage} onChange={e=>setTargetPage(Number(e.target.value))}/></label>}<button disabled={busy||!validPage} onClick={()=>{setBusy(true);setError("");void parseDocument(document.doc_version_id,false,false,{pageNumbers:selection}).then(async()=>{await onRefresh();setDiagnostics(await inspectDocumentParse(document.doc_version_id));}).catch(err=>setError(errorMessage(err))).finally(()=>setBusy(false));}}>仅提取原生文本</button><button disabled={busy||!validPage} onClick={()=>{setBusy(true);setError("");void parseDocument(document.doc_version_id,false,false,{autoEnhance:true,pageNumbers:selection}).then(async()=>{await onRefresh();setDiagnostics(await inspectDocumentParse(document.doc_version_id));}).catch(err=>setError(errorMessage(err))).finally(()=>setBusy(false));}}>按质量信号自动候选解析</button><p className="settings-help">先检查原生文本，再按页使用已配置的 OCR 或布局候选；资源缺失、增强失败和内容减少会留痕并保留回退文本。阈值尚未通过科研金标校准。</p></section>
    <section className="parse-diagnostics"><h3>解析与覆盖</h3>{Boolean(diagnostics?.unlocated_items)&&<p className="job-error">还有 {diagnostics?.unlocated_items} 个对象无法可靠定位到页。单页重解析不能确认这些遗漏已修复；请对照原件并考虑全篇重解析。</p>}<p>{diagnostics?.pages.length??0} 页有处理记录；{warningPages.length} 页存在解析错误或质量警告。</p>{warningPages.length>0&&<p>待核对页：{warningPages.join("、")}。请查看页级诊断并对照原件；不能据此断言全文缺少某信息。</p>}<button disabled={busy||!validPage||!diagnostics?.ocr_configured} onClick={()=>{setBusy(true);setError("");void parseDocument(document.doc_version_id,true,false,{pageNumbers:selection}).then(async()=>{await onRefresh();setDiagnostics(await inspectDocumentParse(document.doc_version_id));}).catch(err=>setError(errorMessage(err))).finally(()=>setBusy(false));}}>使用离线 OCR 重解析低文本页</button><p className="settings-help">{diagnostics?.ocr_configured?"OCR 候选已配置。新批次成功发布后替换旧解析；原件不变，历史引用可能过期。":"请先在设置中选择已批准的 OCR 语言目录。"}</p><details><summary>页级诊断与最近解析批次</summary>{diagnostics?.pages.map(page=><p key={page.page_number}>第 {page.page_number} 页 · {page.text_chars} 字符 · {page.quality} {page.error_code??""}</p>)}{diagnostics?.runs.map(run=><div key={run.id}><p>{labelRun(run.status)} · {run.page_count??"—"} 页 · {run.error_code??""}</p>{Boolean(run.attempts?.length)&&<ul>{run.attempts?.map(attempt=><li key={attempt.id}>{attempt.method} · {attempt.status} · 页 {attempt.page_numbers_json??"全部"} {attempt.error_code??""}</li>)}</ul>}{Boolean(run.routing?.length)&&<details><summary>逐页路由与回退原因</summary><pre>{JSON.stringify(run.routing,null,2)}</pre></details>}{run.parser_configuration&&<pre>{JSON.stringify(run.parser_configuration,null,2)}</pre>}</div>)}</details></section>
    <section className="layout-parse-actions"><button disabled={busy} onClick={()=>{setError("");void inspectDocumentParse(document.doc_version_id).then(setDiagnostics).catch(err=>setError(errorMessage(err)));}}>刷新解析与表格</button><button disabled={busy||!validPage||!diagnostics?.docling_configured} onClick={()=>{setBusy(true);setError("");void parseDocument(document.doc_version_id,false,true,{pageNumbers:selection}).then(async()=>{await onRefresh();setDiagnostics(await inspectDocumentParse(document.doc_version_id));}).catch(err=>setError(errorMessage(err))).finally(()=>setBusy(false));}}>使用本地布局与表格增强解析</button><p className="settings-help">增强解析每次最多 40 页；可只更新指定页。成功发布后仅受影响页的旧引用过期，请核对新结果。</p></section>
    <TableCandidates key={`${document.doc_version_id}:${diagnostics?.publication_revision??0}`} versionId={document.doc_version_id} onOpenPdf={onOpenPdf} />
    </details>
    <small>原件 SHA256：<code>{document.file_sha256}</code></small>
  </section>;
}

function labelRun(status:string){return status==="ready"?"解析完成（未经人工复核）":status==="partial"?"部分解析":status;}
