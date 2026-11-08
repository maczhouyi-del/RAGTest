export type ProbeFlow<T> = {
  probe:()=>Promise<T>; refresh:()=>Promise<unknown>; onSaved?:()=>Promise<unknown>;
  alive:()=>boolean; busy:(value:boolean)=>void; success:(value:T)=>void;
  error:(value:string)=>void; message:(error:unknown)=>string;
};

export async function probeConnection<T>(flow:ProbeFlow<T>) {
  if(!flow.alive())return;
  flow.busy(true);flow.error("");
  let primary="";
  try {
    try { const result=await flow.probe();if(flow.alive())flow.success(result); }
    catch(error) { primary=flow.message(error);if(flow.alive())flow.error(primary); }
    if(!flow.alive())return;
    try { await flow.refresh();if(flow.alive())await flow.onSaved?.(); }
    catch(error) { if(flow.alive())flow.error([primary,"刷新连接状态失败："+flow.message(error)].filter(Boolean).join("\n")); }
  } finally { if(flow.alive())flow.busy(false); }
}
