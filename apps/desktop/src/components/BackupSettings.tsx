import { useCallback, useEffect, useState } from "react";
import { activateRestoredWorkspace, createBackup, errorMessage, listBackups, restoreBackup, type BackupRecord } from "../bridge";

export default function BackupSettings({workspace, onChange, onRecords}: {onRecords?:(rows:BackupRecord[])=>void; workspace?: {label: string; warning: string}; onChange: () => Promise<unknown>}) {
  const [records, setRecords] = useState<BackupRecord[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {const rows=(await listBackups()).records;setRecords(rows);onRecords?.(rows);}
    catch (err) {setError(errorMessage(err));}
  }, [onRecords]);
  useEffect(() => {void refresh(); const timer = window.setInterval(() => void refresh(), 3000); return () => window.clearInterval(timer);}, [refresh]);
  async function run(action: () => Promise<unknown>, success: string, changed = false) {
    setBusy(true); setError(""); setMessage("");
    try {const result = await action(); if (result !== null) setMessage(success); await refresh(); if (changed) await onChange();}
    catch (err) {setError(errorMessage(err));}
    finally {setBusy(false);}
  }
  return <section className="panel"><div className="panel-head"><h2>备份与恢复</h2><span>当前工作区：{workspace?.label ?? "RAGSystem"}</span></div>
    <div className="settings-content"><p>备份包含原件、文献与项目、任务和持久向量。恢复会先校验文件，再创建全新副本。</p>
      {workspace?.warning && <p role="alert">{workspace.warning}</p>}
      <div className="settings-actions"><button disabled={busy} onClick={() => void run(createBackup, "备份任务已提交。请在文献页查看任务进度。")}>创建备份</button><button disabled={busy} onClick={() => void run(restoreBackup, "恢复任务已提交。校验成功后，可在下面使用恢复副本。")}>从备份恢复副本</button></div>
      {error && <p role="alert" className="job-error">{error}</p>}{message && <p role="status">{message}</p>}
      <p className="settings-help">外部派生索引可以重建；模型权重单独管理。取消、失败或不完整的副本不会标为可使用。</p>
    </div>
    {records.length ? <ul className="job-list">{records.map(record => <li key={record.id}><div><strong>{record.kind === "backup" ? "已完成备份" : "已校验恢复副本"}</strong><small>{new Date(record.created_at).toLocaleString("zh-CN")} · {record.document_count} 篇 · {record.embedding_count} 条持久向量</small><small>{record.label}</small></div>{record.kind === "restored" && <button disabled={busy} onClick={() => void run(async () => {await activateRestoredWorkspace(record.id);}, "已切换到恢复副本，原资料库仍保留。", true)}>使用此恢复副本</button>}</li>)}</ul> : <p className="empty">还没有本工作区记录的备份或恢复副本。</p>}
  </section>;
}
