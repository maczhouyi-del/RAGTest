import {useEffect, useState} from "react";
import {errorMessage, listDocumentTables, readTableCandidate, reviewTableCandidate, type TableCandidate, type TableSummary} from "../bridge";

const statusLabels:Record<string,string>={unreviewed:"待审",confirmed:"人工确认结构",rejected:"人工否定结构",uncertain:"人工记录不确定"};

export function TableInspector({tableId,onOpenPdf}:{tableId:string;onOpenPdf?:(page:number)=>Promise<void>}){
  const [data,setData]=useState<TableCandidate|null>(null);
  const [rowOffset,setRowOffset]=useState(0);
  const [note,setNote]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{let alive=true;setError("");void readTableCandidate(tableId,rowOffset).then(result=>{if(alive){setData(result);setNote(result.review.note);}}).catch(err=>{if(alive)setError(errorMessage(err));});return()=>{alive=false;};},[tableId,rowOffset]);
  async function review(status:string){
    if(!data)return;
    setBusy(true);setError("");
    try{await reviewTableCandidate(tableId,{expected_revision:data.review.revision,status,note:note.trim()});setData(await readTableCandidate(tableId,rowOffset));}
    catch(err){setError(errorMessage(err));}
    finally{setBusy(false);}
  }
  return <section className="table-inspector" aria-label="表格候选核对">
    {error&&<p role="alert" className="job-error">{error}</p>}
    {data&&<><h4>表格候选 · {data.row_count} 行 × {data.column_count} 列</h4>
      <p className="notice">结构来自本地模型，数值、表头、单位与实验条件均需对照原件核对。结构复核与科学可比性分别记录；当前仅提供页级定位。</p>
      <p>来源页：{data.source_pages.join("、")||"无法确定"} · {statusLabels[data.review.status]} · 修订 {data.review.revision}</p>
      <div className="settings-actions">{data.page_number&&onOpenPdf&&<button disabled={busy} onClick={()=>void onOpenPdf(data.page_number!).catch(err=>setError(errorMessage(err)))}>对照 PDF 第 {data.page_number} 页</button>}
        {rowOffset>0&&<button onClick={()=>setRowOffset(Math.max(0,rowOffset-10))}>上一组表格行</button>}
        {data.next_row_offset!==null&&<button onClick={()=>setRowOffset(data.next_row_offset!)}>下一组表格行</button>}
      </div><p className="settings-help">显示第 {Math.min(rowOffset+1,data.row_count)}–{Math.min(rowOffset+10,data.row_count)} 行的单元格。行列从 1 开始，跨度来自候选结构。</p>
      <div className="table-scroll"><table><thead><tr><th>行范围</th><th>列范围</th><th>表头候选</th><th>文本 / 数值 / 单位</th></tr></thead><tbody>{data.cells.map(cell=><tr key={cell.id}><td>{cell.row_start+1}–{cell.row_end}</td><td>{cell.column_start+1}–{cell.column_end}</td><td>{cell.column_header?"列头 ":""}{cell.row_header?"行头":""}</td><td className="cell-text">{cell.text||"（空单元格）"}</td></tr>)}</tbody></table></div>
      <label>结构复核备注<textarea aria-label="表格结构复核备注" maxLength={4000} rows={2} value={note} onChange={event=>setNote(event.target.value)} /></label>
      <div className="review-actions">{(["confirmed","rejected","uncertain","unreviewed"] as const).map(status=><button key={status} disabled={busy||!note.trim()} onClick={()=>void review(status)}>{statusLabels[status]}</button>)}</div>
      {data.review_history.length>0&&<details><summary>表格结构复核历史</summary>{data.review_history.map(record=><p key={record.revision}>修订 {record.revision} · {statusLabels[record.status]} · {record.note}</p>)}</details>}
      <small>解析批次 {data.parse_run_id} · 表格 {data.id} · 科学可比性未自动判定</small>
    </>}
  </section>;
}

export default function TableCandidates({versionId,onOpenPdf}:{versionId:string;onOpenPdf:(page:number)=>Promise<void>}){
  const [tables,setTables]=useState<TableSummary[]>([]);
  const [next,setNext]=useState<number|null>(null);
  const [total,setTotal]=useState(0);
  const [selected,setSelected]=useState("");
  const [error,setError]=useState("");
  useEffect(()=>{let alive=true;void listDocumentTables(versionId).then(result=>{if(alive){setTables(result.tables);setTotal(result.total);setNext(result.next_offset);setSelected(result.tables[0]?.id??"");}}).catch(err=>{if(alive)setError(errorMessage(err));});return()=>{alive=false;};},[versionId]);
  async function more(){if(next===null)return;try{const result=await listDocumentTables(versionId,next);setTables(previous=>[...previous,...result.tables]);setNext(result.next_offset);}catch(err){setError(errorMessage(err));}}
  return <section className="table-candidates"><h3>结构化表格候选（{total}）</h3>{error&&<p role="alert" className="job-error">{error}</p>}
    {!tables.length?<p>当前已发布解析没有表格候选。可配置本地模型后显式增强解析；没有候选不表示原文没有表格。</p>:<><label>选择表格<select aria-label="选择表格候选" value={selected} onChange={event=>setSelected(event.target.value)}>{tables.map(table=><option key={table.id} value={table.id}>表 {table.ordinal+1} · 第 {table.source_pages.join("、")} 页 · {table.row_count} × {table.column_count}</option>)}</select></label>{next!==null&&<button onClick={()=>void more()}>载入更多表格</button>}{selected&&<TableInspector key={selected} tableId={selected} onOpenPdf={onOpenPdf}/>}</>}
  </section>;
}
