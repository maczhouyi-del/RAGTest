import {useEffect,useRef,useState} from "react";
import Icon from "./Icon";

export default function CopyButton({text,label}:{text:string;label:string}) {
 const [status,setStatus]=useState<"idle"|"copied"|"failed">("idle"),timer=useRef<number|null>(null);
 useEffect(()=>()=>{if(timer.current!==null)window.clearTimeout(timer.current);},[]);
 async function copy(){
  try{
   if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
   else {
    const previous=document.activeElement as HTMLElement|null,field=document.createElement("textarea");
    field.value=text;field.style.position="fixed";field.style.opacity="0";document.body.appendChild(field);
    try{field.select();if(!document.execCommand("copy"))throw new Error("COPY_FAILED");}
    finally{field.remove();previous?.focus({preventScroll:true});}
   }
   setStatus("copied");
  }catch{setStatus("failed");}
  if(timer.current!==null)window.clearTimeout(timer.current);timer.current=window.setTimeout(()=>setStatus("idle"),2500);
 }
 return <span className="copy-control"><button type="button" className="message-copy" aria-label={label} title={label} onClick={event=>{event.stopPropagation();void copy();}}><Icon name={status==="copied"?"check":"copy"} size={15}/></button><span role="status">{status==="copied"?"已复制":status==="failed"?"复制失败，请选中文字手动复制":""}</span></span>;
}
