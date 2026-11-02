import {errorMessage,type AnswerRun} from "../bridge";

export function refusalText(turn:AnswerRun):string {
 if(turn.result?.outcome!=="insufficient_evidence")return turn.result?.refusal_reason??(turn.evidence.length?"当前证据不足以支持回答，请查看本次检索。":"本轮未检索到可用于回答的证据。");
 if(!turn.claims.length)return "已检索到原文，但模型未生成可引用的结论，因此未执行支持性检查。请查看右侧片段是否覆盖问题；比较文献时需各篇的研究目的、方法或结果。";
 return "模型生成了草稿，但没有结论通过支持性检查。具体原因见右侧对应引用；这不等于PDF解析失败，也不代表论文没有相关结论。";
}

export function answerParagraphs(turn:AnswerRun,isSystem:boolean):{text:string;className:string;role?:"status"|"alert"}[] {
 const rows:{text:string;className:string;role?:"status"|"alert"}[]=[];
 if(["queued","running"].includes(turn.status))rows.push({text:isSystem?"正在读取本机配置…":"正在整理回答…",className:"loading-text",role:"status"});
 if(turn.result?.kind==="system_info"&&typeof turn.result.text==="string")rows.push({text:turn.result.text,className:"system-answer"});
 if(turn.result?.intent==="mixed")for(const info of turn.result.system_information??[])rows.push({text:`本机系统信息：${info.text}`,className:"system-answer"});
 if(turn.status==="refused")rows.push({text:refusalText(turn),className:"notice"});
 if(["failed","cancelled"].includes(turn.status))rows.push({text:(turn.result?.outcome==="generation_failed"?"检索已完成，生成或引用核验失败：":"本轮问答未完成：")+errorMessage(turn.error_code??turn.status),className:"job-error",role:"alert"});
 if(turn.result?.kind!=="system_info"&&turn.mode==="extractive"&&turn.status==="completed")rows.push({text:"原文摘录模式，未生成模型答案。原文见右侧「本次检索」。",className:"extractive-status"});
 if(turn.status==="completed")for(const claim of turn.claims.filter(item=>item.model_support==="supported"))rows.push({text:claim.text,className:"answer-body"});
 return rows;
}
