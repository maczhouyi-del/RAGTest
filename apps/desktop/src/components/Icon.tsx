import type {CSSProperties} from "react";

const paths = {
  book: "M12 5.5C8 2.5 4 3 2 4v15c3-1 6-1 10 2 4-3 7-3 10-2V4c-2-1-6-1-10 1.5ZM12 6v15",
  chat: "M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V7a3 3 0 0 1 3-3Z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 0v6h6M8 12h8M8 16h6",
  settings: "m9 3 1-2h4l1 2 2 1 2-1 2 3-1 2v3l2 2-2 3-2-1-3 2-1 3h-4l-1-3-3-2-2 1-2-3 2-2V8L2 6l2-3 2 1Zm3 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
  database: "M21 5c0 2-4 4-9 4S3 7 3 5s4-3 9-3 9 1 9 3ZM3 5v14c0 2 4 3 9 3s9-1 9-3V5M3 12c0 2 4 3 9 3s9-1 9-3",
  upload: "M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5",
  folder: "M3 5h6l2 3h9a1 1 0 0 1 1 1v11H3Z",
  search: "M21 21l-6-6M17 9a7 7 0 1 1-14 0 7 7 0 0 1 14 0",
  robot: "M12 3V1M8 12v2m8-2v2M8 18h8M5 7h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2ZM1 11v5m22-5v5",
  shield: "m12 2 9 4v6c0 5-5 9-9 11-4-2-9-6-9-11V6Zm-5 9 3 3 7-7",
  lock: "M6 10V7a6 6 0 0 1 12 0v3M4 10h16v12H4Zm8 5v3",
  plus: "M12 5v14M5 12h14",
  chevron: "m9 5 7 7-7 7",
  down: "m6 9 6 6 6-6",
  check: "m5 12 4 4L20 5",
  close: "m6 6 12 12M6 18 18 6",
  refresh: "M20 9a8 8 0 0 0-14-5L3 7m0-5v5h5M4 15a8 8 0 0 0 14 5l3-3m0 5v-5h-5",
  send: "m22 2-7 20-4-9-9-4Zm0 0L11 13",
  monitor: "M3 3h18v14H3Zm9 14v5m-5 0h10",
  cloud: "M5 20a5 5 0 0 1-1-10 8 8 0 0 1 15-3 6 6 0 0 1 0 13Z",
  bird: "m3 20 5-9 7-9 5 3-4 8-5 1-3 6Zm12-18 1 6 4-3M3 20h9",
  info: "M12 11v6m0-10v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  list: "M8 5h13M8 12h13M8 19h13M3 5h.1M3 12h.1M3 19h.1",
  sliders: "M3 6h7m4 0h7M3 18h3m4 0h11M10 3v6M6 15v6M3 12h13m4 0h1M16 9v6",
  copy: "M9 8h12v14H9ZM5 17H3V2h12v3",
  calendar: "M3 5h18v17H3ZM7 2v6m10-6v6M3 10h18",
  user: "M4 22v-4a8 8 0 0 1 16 0v4M17 6a5 5 0 1 1-10 0 5 5 0 0 1 10 0",
  link: "m10 14 4-4M8 16l-2 2a4 4 0 0 1-6-6l6-6a4 4 0 0 1 6 0m0 2 2-2a4 4 0 0 1 6 6l-6 6a4 4 0 0 1-6 0",
  clock: "M12 6v6l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  archive: "M3 3h18v5H3Zm2 5v14h14V8M9 12h6",
  download: "M12 2v14m-5-5 5 5 5-5M3 17v5h18v-5",
  light: "M9 19h6m-5 3h4M8 15a7 7 0 1 1 8 0l-1 2H9ZM12 1v1M1 9h2m18 0h2M4 2l2 2m12 0 2-2",
  dots: "M4 12h.1M12 12h.1M20 12h.1",
  minus: "M5 12h14",
  graduate: "m1 8 11-5 11 5-11 5Zm4 3v7c4 3 10 3 14 0v-7m3-2v9",
} as const;
export type IconName = keyof typeof paths;
export default function Icon({name, size=20, className="", style}: {name: IconName; size?: number; className?: string; style?: CSSProperties}) {
  return <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={paths[name]}/></svg>;
}
