import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { errorMessage, readSource, searchSources, type DocumentRow, type SearchHit, type SourceFile } from "../bridge";
const PdfPreview = lazy(() => import("./PdfPreview"));

export default function SourceSearch({documents, projectId}: {documents: DocumentRow[]; projectId: string | null}) {
  const [query, setQuery] = useState("");
  const [strategy, setStrategy] = useState("keyword");
  const [tag,setTag]=useState(""),[yearFrom,setYearFrom]=useState(""),[yearTo,setYearTo]=useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const [file, setFile] = useState<SourceFile | null>(null);
  const alive = useRef(true);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  const versions = documents.filter(d => ["ready", "partial"].includes(d.parse_status) && (!tag||d.tags.includes(tag)) && (!yearFrom||(d.year!==null&&d.year>=Number(yearFrom))) && (!yearTo||(d.year!==null&&d.year<=Number(yearTo)))).map(d => d.doc_version_id);
  const scopeKey = versions.slice().sort().join("|") + strategy;
  const activeScope = useRef(scopeKey);
  activeScope.current = scopeKey;
  useEffect(() => {setHits([]); setSearched(false); setFile(null); setError("");}, [scopeKey]);
  async function search(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    const requestedScope = scopeKey;
    try {const result = await searchSources(query, versions, projectId, strategy, {tag:tag||null,year_from:yearFrom?Number(yearFrom):null,year_to:yearTo?Number(yearTo):null}); if (alive.current && activeScope.current === requestedScope) {setHits(result.results); setSearched(true);}}
    catch (err) {if (alive.current) setError(errorMessage(err));}
    finally {if (alive.current) setBusy(false);}
  }
  async function open(hit: SearchHit) {
    setBusy(true); setError("");
    const requestedScope = scopeKey;
    try {const result = await readSource(hit.source_anchor_id); if (alive.current && activeScope.current === requestedScope) setFile(result);}
    catch (err) {if (alive.current) setError(errorMessage(err));}
    finally {if (alive.current) setBusy(false);}
  }
  return <section className="panel"><div className="panel-head"><h2>检索原文来源</h2><span>{versions.length} 篇已解析文献</span></div><form className="search-form" onSubmit={event => void search(event)}><label htmlFor="source-query">关键词或完整短语</label><div><select aria-label="检索方式" value={strategy} onChange={event => {setStrategy(event.target.value); setHits([]); setSearched(false);}}><option value="keyword">关键词</option><option value="fts_only">完整短语</option><option value="vector_exact">语义向量</option><option value="hybrid">混合检索</option></select><input id="source-query" value={query} onChange={e => setQuery(e.target.value)} maxLength={2000} placeholder="例如：BERT、retrieval" /><button disabled={busy || !query.trim() || !versions.length}>检索</button></div><div className="settings-actions"><label>标签筛选<select aria-label="检索标签筛选" value={tag} onChange={e=>setTag(e.target.value)}><option value="">全部标签</option>{Array.from(new Set(documents.flatMap(doc=>doc.tags))).sort().map(value=><option key={value}>{value}</option>)}</select></label><label>起始年份<input aria-label="检索起始年份" type="number" min="1500" max="2200" value={yearFrom} onChange={e=>setYearFrom(e.target.value)}/></label><label>结束年份<input aria-label="检索结束年份" type="number" min="1500" max="2200" value={yearTo} onChange={e=>setYearTo(e.target.value)}/></label></div><p>年份筛选会排除年份未知的记录。仅搜索当前范围的已解析文献。语义/混合检索需先配置本地模型；命中不代表全库结论。</p></form>{error && <p role="alert" className="search-error">{error}</p>}{searched && hits.length === 0 && <p className="empty">当前关键词与范围内没有找到来源片段。</p>}<ul className="search-hits">{hits.map(hit => <li key={hit.chunk_id}><div><strong>{documents.find(d => d.doc_version_id === hit.doc_version_id)?.title ?? "文献来源"}</strong><span>第 {hit.page_number} 页 · 页级定位</span></div><p>{hit.preview}</p><button disabled={busy} onClick={() => void open(hit)}>查看原文</button></li>)}</ul>{file && <Suspense fallback={<p role="status">正在加载阅读器…</p>}><PdfPreview file={file} onClose={() => setFile(null)} /></Suspense>}</section>;
}
