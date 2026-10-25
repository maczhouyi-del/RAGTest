import { useState, type FormEvent } from "react";
import { createProject, errorMessage, type Project } from "../bridge";

export default function ProjectPicker({projects, selected, onSelect, onRefresh}: {
  projects: Project[]; selected: string; onSelect: (id: string) => void; onRefresh: () => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  async function create(event: FormEvent) {
    event.preventDefault(); setCreating(true); setError("");
    try {
      const project = await createProject(name.trim());
      await onRefresh(); onSelect(project.id); setName(""); setExpanded(false);
    } catch (err) {setError(errorMessage(err));}
    finally {setCreating(false);}
  }
  return <section className="project-picker" aria-label="项目切换">
    <label htmlFor="project-select">当前项目</label>
    <select id="project-select" value={selected} onChange={event => onSelect(event.target.value)}>
      <option value="">全部文献</option>
      {projects.map(project => <option key={project.id} value={project.id}>{project.name} ({project.document_count})</option>)}
    </select>
    <button className="project-create-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>新建项目</button>
    {expanded && <form onSubmit={event => void create(event)}>
      <label htmlFor="project-name">项目名称</label>
      <input id="project-name" value={name} maxLength={100} onChange={event => setName(event.target.value)} autoFocus required />
      <button disabled={creating || !name.trim()}>{creating ? "创建中…" : "创建项目"}</button>
    </form>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
