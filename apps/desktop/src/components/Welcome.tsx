import Icon from "./Icon";

export default function Welcome({busy,onImport}: {busy:boolean;onImport:()=>void}) {
  return <section className="welcome-page" aria-label="欢迎使用">
    <div className="welcome-empty">
      <Icon name="book" size={36}/>
      <h1>文献库还是空的</h1>
      <button className="primary" disabled={busy} onClick={onImport}><Icon name="plus"/>导入文件</button>
    </div>
  </section>;
}
