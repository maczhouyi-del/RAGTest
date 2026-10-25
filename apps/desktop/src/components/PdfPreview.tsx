import { useEffect, useRef, useState, type FormEvent } from "react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type RenderTask } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import ReadingNotes from "./ReadingNotes";
import { type ReaderFile } from "../bridge";

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfPreview({file, onClose, presentation="reader"}: {file: ReaderFile; onClose: () => void; presentation?:"reader"|"evidence"|"embedded"}) {
  const [wide,setWide]=useState(()=>window.matchMedia("(min-width: 1600px)").matches);
  const [surfaceWidth,setSurfaceWidth]=useState(0);
  useEffect(()=>{const media=window.matchMedia("(min-width: 1600px)");const update=()=>setWide(media.matches);media.addEventListener("change",update);return()=>media.removeEventListener("change",update);},[]);
  const embedded=presentation==="embedded";
  const inline=embedded||presentation==="evidence"&&wide;
  const initialPage = "anchor" in file ? file.anchor.page_number : (file.document.page_number??1);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(()=>{const surface=canvas.current?.parentElement;if(!surface)return;const update=()=>setSurfaceWidth(surface.clientWidth);const observer=new ResizeObserver(update);observer.observe(surface);update();return()=>observer.disconnect();},[]);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [jump, setJump] = useState(String(initialPage));
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const [notesOpen,setNotesOpen]=useState(false);
  const versionId = "anchor" in file ? file.anchor.doc_version_id : file.document.doc_version_id;
  const [rendering, setRendering] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setPdf(null); setError(""); setPageNumber(initialPage); setZoom(1);
    // Data bytes only: no remote URLs, XFA or executable PDF actions.
    const loading = getDocument({data: new Uint8Array(file.pdf_bytes), enableXfa: false, disableAutoFetch: true, disableStream: true});
    void loading.promise.then(document => {
      if (cancelled) return;
      if (initialPage < 1 || initialPage > document.numPages) throw new Error("SOURCE_PAGE_INVALID");
      setPdf(document);
    }).catch(() => {if (!cancelled) {setError("此 PDF 无法打开，原件仍已保存在本地。"); setRendering(false);}});
    return () => {cancelled = true; void loading.destroy();};
  }, [file, initialPage]);
  useEffect(() => {setJump(String(pageNumber));}, [pageNumber]);
  useEffect(() => {
    if (!pdf) return;
    let cancelled = false;
    let task: RenderTask | undefined;
    setError(""); setRendering(true);
    void pdf.getPage(pageNumber).then(async page => {
      if (cancelled || !canvas.current) return;
      const scale = Math.min(1.25, (inline?Math.max(120,surfaceWidth-24):1600) / page.getViewport({scale: 1}).width) * zoom;
      const viewport = page.getViewport({scale});
      if (viewport.width * viewport.height > 6000000) throw new Error("PAGE_CANVAS_LIMIT");
      const surface = canvas.current;
      surface.width = viewport.width; surface.height = viewport.height;
      task = page.render({canvas: surface, viewport});
      await task.promise;
      if (!cancelled) setRendering(false);
    }).catch(() => {if (!cancelled) {setError("此页无法渲染，请尝试其他页或较小缩放。"); setRendering(false);}});
    return () => {cancelled = true; task?.cancel();};
  }, [pdf, pageNumber, zoom,inline,surfaceWidth]);
  function go(event: FormEvent) {
    event.preventDefault();
    const next = Number(jump);
    if (pdf && Number.isInteger(next) && next >= 1 && next <= pdf.numPages) setPageNumber(next);
  }
  return <section className={`pdf-overlay ${embedded?"pdf-embedded":""} ${presentation==="evidence"?"evidence-panel":""}`} role={inline?"region":"dialog"} aria-modal={inline?undefined:true} aria-labelledby="pdf-title"
    onKeyDown={event => {if (event.key === "Escape") onClose();}}>
    <header><div><h2 id="pdf-title">{"anchor" in file ? "原文来源" : "PDF 阅读"} · 第 {pageNumber} 页</h2>
      <small>{"anchor" in file ? `来源位于第 ${initialPage} 页 · 页级定位 · 坐标尚未校准` : file.document.title}</small>
    </div>{!embedded&&<button onClick={onClose} autoFocus>关闭</button>}</header>
    <div className="reader-toolbar">
      <button disabled={!pdf || pageNumber <= 1} onClick={() => setPageNumber(pageNumber - 1)}>上一页</button>
      <form onSubmit={go}><label htmlFor="reader-page">跳转页码</label><input id="reader-page" type="number" min={1} max={pdf?.numPages ?? 1} value={jump} onChange={event => setJump(event.target.value)} disabled={!pdf} /><span>/ {pdf?.numPages ?? "—"}</span><button disabled={!pdf}>跳转</button></form>
      <button disabled={!pdf || pageNumber >= pdf.numPages} onClick={() => setPageNumber(pageNumber + 1)}>下一页</button>
      <label>缩放<select aria-label="阅读缩放" value={zoom} onChange={event => setZoom(Number(event.target.value))}>{[0.75, 1, 1.25, 1.5, 2].map(value => <option key={value} value={value}>{Math.round(value * 100)}%</option>)}</select></label>
      <button onClick={()=>setNotesOpen(!notesOpen)}>{notesOpen?"收起批注":"阅读批注"}</button>
    </div>
    {"anchor" in file&&file.anchor.reason_if_degraded?.startsWith("OCR_")&&<p className="notice">来源文本由 OCR 识别，请对照本页图像核对字符、数值和单位。</p>}
    {!embedded&&"anchor" in file&&file.evidence_quote&&<blockquote className="reader-evidence">{file.evidence_quote}</blockquote>}
    {notesOpen&&<ReadingNotes key={versionId+pageNumber} versionId={versionId} pageNumber={pageNumber} sourceId={"anchor" in file&&pageNumber===initialPage?file.anchor.source_anchor_id:null}/>}
    {rendering && <p role="status" className="reader-status">正在渲染页面…</p>}{error && <p role="alert">{error}</p>}
    <div className="pdf-page"><canvas ref={canvas} aria-label={`PDF 第 ${pageNumber} 页`} /></div>
  </section>;
}
