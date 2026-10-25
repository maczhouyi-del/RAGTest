import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cancelJob, retryJob, errorMessage, importPdf, restartEngine, snapshot, parseDocument, readDocument, type ReaderFile, type Snapshot } from "./bridge";
import SourceSearch from "./components/SourceSearch";
import ProjectPicker from "./components/ProjectPicker";
import DocumentDetails from "./components/DocumentDetails";
import BackupSettings from "./components/BackupSettings";
import LifecycleSettings from "./components/LifecycleSettings";
import ModelSettings from "./components/ModelSettings";
import IdentitySettings from "./components/IdentitySettings";
import ResearchWorkbench from "./components/ResearchWorkbench";
const PdfPreview = lazy(() => import("./components/PdfPreview"));

const taskLabels: Record<string,string> = {parse_page:"解析文献",embed_batch:"构建候选索引",verify:"模型或证据检查",research_extract:"逐篇研究",backup:"备份与恢复",index_upsert:"更新索引"};
const statusLabels: Record<string, string> = {
  queued: "排队中", running: "处理中", completed: "已完成", failed: "失败",
  retry_wait: "等待恢复", cancelled: "已取消", cancelling: "取消中",
  not_started: "尚未解析", partial: "部分解析", ready: "已解析", failed_parse: "解析失败",
};

export default function App() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"library" | "tasks" | "search" | "settings" | "ask" | "research">("library");
  const [projectId, setProjectId] = useState("");
  const [filter, setFilter] = useState("");
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [reader, setReader] = useState<ReaderFile | null>(null);
  const inFlight = useRef<Promise<Snapshot> | null>(null);
  const refresh = useCallback(async () => {
    // Explicit post-mutation refresh waits for an older poll before fetching
    // again, so a stale in-flight snapshot cannot hide a successful edit.
    if (inFlight.current) await inFlight.current.catch(() => undefined);
    const request = snapshot(); inFlight.current = request;
    try {const result = await request; setData(result); setConnectionError(""); return result;}
    catch (err) {setConnectionError(errorMessage(err)); throw err;}
    finally {if (inFlight.current === request) inFlight.current = null;}
  }, []);
  useEffect(() => {
    void refresh().catch(() => undefined);
    const timer = window.setInterval(() => {if (!inFlight.current) void refresh().catch(() => undefined);}, 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function perform(action: () => Promise<unknown>) {
    setBusy(true); setOperationError("");
    try {await action(); await refresh();}
    catch (err) {setOperationError(errorMessage(err));}
    finally {setBusy(false);}
  }
  const importCurrentProject = () => importPdf(projectId || null);
  function selectProject(id: string) {setProjectId(id); setFilter(""); setDetailsId(null); setReader(null);}
  async function workspaceChanged() {setProjectId(""); setFilter(""); setDetailsId(null); setReader(null); await refresh();}
  const documents = useMemo(() => (data?.documents ?? []).filter(document => !projectId || document.project_ids.includes(projectId)), [data, projectId]);
  const filtered = useMemo(() => documents.filter(document => [document.title, document.doi ?? "", ...document.authors, ...document.tags].join(" ").toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase())), [documents, filter]);
  const details = data?.documents.find(document => document.doc_version_id === detailsId);
  const projectName = data?.projects.find(project => project.id === projectId)?.name ?? "全部文献";
  const disconnected = !data || Boolean(connectionError);

  return <div className={`workspace ${reader&&details?"comparing-document":""}`}>
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">R</span><div>RAGSystem<small>本地科研文献工作台</small></div></div>
      {data && <ProjectPicker projects={data.projects} selected={projectId} onSelect={selectProject} onRefresh={refresh} />}
      <nav aria-label="工作区">
        <button className={tab === "library" ? "nav active" : "nav"} onClick={() => setTab("library")}>文献库 <span>{documents.length}</span></button>
        <button className={tab === "search" ? "nav active" : "nav"} onClick={() => setTab("search")}>来源检索</button>
        <button className={tab === "ask" ? "nav active" : "nav"} onClick={() => setTab("ask")}>证据问答</button>
        <button className={tab === "research" ? "nav active" : "nav"} onClick={() => setTab("research")}>Research 工作台</button>
        <button className={tab === "tasks" ? "nav active" : "nav"} onClick={() => setTab("tasks")}>任务与恢复 <span>{data?.jobs.filter(job => ["running", "queued", "retry_wait"].includes(job.status)).length ?? "—"}</span></button>
        <button className={tab === "settings" ? "nav active" : "nav"} onClick={() => setTab("settings")}>设置与备份</button>
      </nav>
      <div className="sidebar-note"><span className={`dot ${!disconnected ? "online" : ""}`} />{!disconnected ? "本地引擎已连接" : "本地引擎未连接"}<small>本地开发预览</small></div>
    </aside>
    <main>
      <header><div><p className="eyebrow">研究资料 / {projectName}</p><h1>{tab === "library" ? "文献库" : tab === "search" ? "来源检索" : tab === "settings" ? "设置与备份" : tab === "ask" ? "证据问答" : tab === "research" ? "Research 工作台" : "任务与恢复"}</h1><p className="subtitle">{tab === "library" ? "保存论文原件，整理项目与元数据，随时阅读。" : tab === "search" ? "在当前项目文献中查找片段，回到真实 PDF 页面。" : "任务状态持久保存，失败原因与恢复状态可查。"}</p></div><button className="primary" disabled={busy || disconnected} onClick={() => void perform(importCurrentProject)}>{busy ? "正在处理…" : "+ 导入 PDF"}</button></header>
      {connectionError && <section role="alert" className="notice error"><div><strong>本地引擎连接失败</strong><p>{connectionError}</p></div><button disabled={busy} onClick={() => void perform(restartEngine)}>重启引擎</button></section>}
      {operationError && <section role="alert" className="notice error"><p>{operationError}</p><button onClick={() => setOperationError("")}>收起</button></section>}
      {!data && !connectionError && <p role="status" className="empty">正在连接本地引擎…</p>}
      {data && <>
        <section className="stats" aria-label="资料概览"><div><span>当前范围原件</span><strong>{new Set(documents.map(doc=>doc.document_id)).size}<small> 篇 / {documents.length} 文件</small></strong></div><div><span>存储体积</span><strong>{(documents.reduce((sum, document) => sum + document.size_bytes, 0) / 1048576).toFixed(1)}<small> MiB</small></strong></div><div><span>向量检索</span><strong className="muted-stat">{data.index?.ready ? "已就绪" : data.index?.configured ? "待更新" : "尚未配置"}</strong></div></section>
        {tab === "ask" || tab === "research" ? <ResearchWorkbench key={(data.workspace?.label ?? "") + projectId + tab} documents={documents} projectId={projectId || null} kind={tab} /> : tab === "settings" ? <><ModelSettings index={data.index} generator={data.generator} ocr={data.ocr} docling={data.docling} onRefresh={refresh} /><LifecycleSettings documents={data.documents} onRefresh={refresh} onRead={setReader} /><IdentitySettings documents={data.documents} onRefresh={refresh} /><BackupSettings key={data.workspace?.label ?? "default"} workspace={data.workspace} onChange={workspaceChanged} /></> : tab === "search" ? <SourceSearch key={(data.workspace?.label ?? "") + projectId} documents={documents} projectId={projectId || null} /> : tab === "library" ? <section className="panel">
          <div className="panel-head"><h2>论文原件</h2><span>{projectName} · SHA256 校验</span></div>
          <div className="library-filter"><label htmlFor="library-filter">筛选文献</label><input id="library-filter" placeholder="题名、作者、DOI 或标签" value={filter} onChange={event => setFilter(event.target.value)} maxLength={1000} /></div>
          {documents.length === 0 ? <div className="empty"><div className="paper-symbol" aria-hidden="true">▤</div><h3>{projectId ? "这个项目还没有文献" : "从第一篇论文开始"}</h3><p>{projectId ? "从全部文献的详情中勾选所属项目。同一份原件可以关联多个项目。" : "选择本机 PDF。导入成功后，原件与任务记录会保存在本地。"}</p>{projectId ? <button onClick={() => selectProject("")}>查看全部文献</button> : <button disabled={busy || disconnected} onClick={() => void perform(importCurrentProject)}>选择 PDF 文件</button>}</div> : filtered.length === 0 ? <p className="empty">没有符合筛选条件的文献。</p> : <div className="table-wrap"><table><thead><tr><th>论文</th><th>年份</th><th>处理状态</th><th>标签</th><th>操作</th></tr></thead><tbody>{filtered.map(document => <tr key={document.doc_version_id}><td><strong className="document-title">{document.title}</strong><small>文件 {document.file_sha256.slice(0,10)} · {document.authors.length ? document.authors.join("，") : "作者未填写"}</small>{document.duplicate_candidates.length > 0 && <small className="duplicate-text">DOI 重复候选，待核对</small>}</td><td>{document.year ?? "—"}</td><td><span className="badge">{statusLabels[document.parse_status] ?? document.parse_status}</span></td><td><span className="document-tags">{document.tags.join(" · ") || "—"}</span></td><td className="document-actions"><button disabled={busy || disconnected} onClick={() => void perform(async () => setReader(await readDocument(document.doc_version_id)))}>阅读</button><button disabled={busy || disconnected} onClick={() => setDetailsId(document.doc_version_id)}>详情</button><button disabled={busy || disconnected} onClick={() => void perform(() => parseDocument(document.doc_version_id))}>{["ready", "partial"].includes(document.parse_status) ? "重解析" : "解析"}</button></td></tr>)}</tbody></table></div>}
          <p className="panel-foot">在详情中编辑元数据和所属项目。元数据由人工维护；文本提取与科研质量分开记录。</p>
        </section> : <section className="panel"><div className="panel-head"><h2>最近任务（整个工作区）</h2><button onClick={() => void refresh().catch(() => undefined)}>刷新</button></div>{data.jobs.length === 0 ? <p className="empty">暂无任务记录</p> : <ul className="job-list">{data.jobs.map(job => <li key={job.job_id}><div><strong>{job.type === "import" ? `导入：${job.label ?? "PDF 原件"}` : taskLabels[job.type] ?? job.type}</strong><small>{new Date(job.updated_at).toLocaleString("zh-CN")} · 尝试 {job.attempt_count}/{job.max_attempts}</small>{job.error_code && <p className="job-error">{errorMessage(job.error_code)}</p>}</div><span className={`badge ${job.status === "failed" ? "failed" : ""}`}>{statusLabels[job.status] ?? job.status}</span>{["failed", "cancelled", "retry_wait"].includes(job.status) && ["import", "parse_page"].includes(job.type) && job.attempt_count < job.max_attempts && <button disabled={busy} onClick={() => void perform(() => retryJob(job.job_id))}>重试</button>}{["queued", "running", "retry_wait"].includes(job.status) && <button disabled={busy} onClick={() => void perform(() => cancelJob(job.job_id))}>取消</button>}</li>)}</ul>}</section>}
        <footer>引擎 {data.health.sidecar_version} · 资料保存在本机</footer>
      </>}
    </main>
    {details && data && <DocumentDetails key={details.doc_version_id} document={details} projects={data.projects} onOpenPdf={async(page)=>{const file=await readDocument(details.doc_version_id);setReader({...file,document:{...file.document,page_number:page}});}} onRefresh={refresh} onClose={() => setDetailsId(null)} />}
    {reader && <Suspense fallback={<p role="status">正在加载阅读器…</p>}><PdfPreview file={reader} onClose={() => setReader(null)} /></Suspense>}
  </div>;
}
