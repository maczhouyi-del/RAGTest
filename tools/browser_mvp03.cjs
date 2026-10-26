/* MVP-03: real source/frozen engine and PDF, simulated Tauri dialogs, loopback API fixture. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {once}=require('node:events');
module.exports=async function({page,rpc,evidence,errors,stage}){
 page.setDefaultTimeout(45000);
 const checks=[];const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);};
 const wait=async test=>{for(let i=0;i<1200;i++){if(await test())return;await page.waitForTimeout(100);}throw Error('TEST_WAIT_TIMEOUT');};
 const nav=page.getByRole('navigation',{name:'主导航'}),input=page.getByLabel('你的问题',{exact:true});
 if(stage==='B'||stage==='C'){
  await page.getByRole('button',{name:'新会话',exact:true}).click();
  await page.getByRole('heading',{name:'从文献出发，找到有据可查的答案',exact:true}).waitFor();
  await input.fill('当前生成模型是什么？');await page.getByRole('button',{name:'发送问题',exact:true}).click();
  await wait(async()=>(await rpc('GET','/v0/history/answers')).total===1);
  const id=(await rpc('GET','/v0/history/answers')).items[0].id;
  await wait(async()=>(await rpc('GET','/v0/answers/'+id)).status==='completed');
  const info=await rpc('GET','/v0/answers/'+id);
  check(info.result.kind==='system_info'&&!info.evidence.length&&info.scope.length===0,'SYSTEM_INFORMATION_WITHOUT_PDFS');
  await page.getByRole('button',{name:'导入 PDF',exact:true}).click();
 }else await page.getByRole('button',{name:'导入文件',exact:true}).click();
 await wait(async()=>{const docs=(await rpc('GET','/v0/documents')).documents;return docs.length===2&&docs.every(doc=>['ready','partial'].includes(doc.parse_status)&&doc.metadata_extraction.status==='completed');});
 await nav.getByRole('button',{name:'设置',exact:true}).click();
 if(stage==='C')await page.getByRole('button',{name:'模型服务',exact:true}).click();
 await page.getByRole('tab',{name:/^自定义兼容接口/}).click();
 const calls=[];let delay=0,supportStatus="supported",postFailure=false;
 const server=http.createServer((req,res)=>{let raw='';req.on('data',part=>raw+=part);req.on('end',()=>{
   if(req.headers.authorization!=='Bearer fixture-authorization-secret'){res.writeHead(401);res.end('{}');return;}
   const body=raw?JSON.parse(raw):null;calls.push({url:req.url,body});res.setHeader('Content-Type','application/json');
   if(req.method==='GET'){res.end(JSON.stringify({data:[{id:'fixture-one'},{id:'fixture-two'}]}));return;}
   if(postFailure){res.writeHead(500);res.end('{}');return;}
   const support=body.messages[0].content.includes('entire claim');
   const result=support?{status:supportStatus,reason:'Protocol fixture, not scientific assessment'}:{claims:[{text:'Protocol fixture answer',evidence:[{citation_id:'E1'}]}]};
   setTimeout(()=>res.end(JSON.stringify({choices:[{message:{content:JSON.stringify(result)}}]})),delay);
 });});server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  await page.getByLabel('连接名称',{exact:true}).fill('授权测试');await page.getByLabel('接口地址（以 /v1 结尾）',{exact:true}).fill(`http://127.0.0.1:${server.address().port}/v1`);
  await page.getByLabel('API Key',{exact:true}).fill('fixture-authorization-secret');await page.getByRole('button',{name:'获取模型列表',exact:true}).click();
  await page.getByText('模型列表已获取，连接/认证已验证。选择模型后直接保存，无需重复输入密钥。',{exact:true}).waitFor();
  await page.getByLabel('模型 ID',{exact:true}).fill('fixture-one');await page.getByRole('button',{name:'保存并启用',exact:true}).click();
  await page.getByRole('switch',{name:'允许 授权测试 用于文献问答',exact:true}).waitFor();
  let provider=(await rpc('GET','/v0/generation-providers')).providers[0];
  check(provider.can_answer&&provider.document_qa_enabled,'SAVED_AND_ENABLED');check(await page.getByLabel('API Key',{exact:true}).inputValue()==='','KEY_INPUT_CLEARED');
  await nav.getByRole('button',{name:'问答',exact:true}).click();await page.getByLabel('生成模型',{exact:true}).selectOption(provider.id);
  async function send(question,onSubmitted){const before=(await rpc('GET','/v0/history/answers')).total;await input.fill(question);await wait(async()=>!await page.getByRole('button',{name:'发送问题',exact:true}).isDisabled());await input.press('Enter');await onSubmitted?.();await wait(async()=>(await rpc('GET','/v0/history/answers')).total===before+1);const id=(await rpc('GET','/v0/history/answers')).items[0].id;await wait(async()=>!['queued','running'].includes((await rpc('GET','/v0/answers/'+id)).status));await wait(async()=>await page.locator(`[data-run-id="${id}"]`).count()===1);return rpc('GET','/v0/answers/'+id);}
  check(await page.locator('.provider-consent').count()===0,'NO_PER_TURN_CONSENT');
  const first=await send('BERT authorization fixture first');const second=await send('BERT authorization fixture second');
  check(first.status==='completed'&&second.status==='completed'&&first.evidence.length>0&&second.evidence.length>0,'CONTINUOUS_QUESTIONS_WITH_ONE_GRANT');
  check(first.conversation_id===second.conversation_id,'SAME_CONVERSATION');
  check(calls.filter(c=>c.body).length===4,'ONLY_INTENDED_GENERATION_CALLS');
  for(const call of calls.filter(c=>c.body&&!c.body.messages[0].content.includes('entire claim'))){const data=JSON.parse(call.body.messages[1].content);check(!data.chunks&&data.excerpts.every(e=>e.quote.length<=1200)&&!JSON.stringify(data).includes('%PDF-'),'TEXT_EXCERPTS_ONLY');}
  await nav.getByRole('button',{name:'设置',exact:true}).click();if(stage==='C')await page.getByRole('button',{name:'模型服务',exact:true}).click();
  await page.getByRole('tab',{name:/^自定义兼容接口/}).click();
  await page.getByRole('switch',{name:'允许 授权测试 用于文献问答',exact:true}).uncheck();
  await wait(async()=>!(await rpc('GET','/v0/generation-providers')).providers[0].document_qa_enabled);
  const before=calls.length;let denied='';try{await rpc('POST','/v0/answers',{question:'BERT denied',version_ids:first.scope.map(d=>d.doc_version_id),mode:'generative',strategy:'keyword',provider_id:provider.id,provider_revision:provider.revision,allow_external:true});}catch(err){denied=err.message;}
  check(denied==='PROVIDER_DOCUMENT_QA_DISABLED'&&calls.length===before,'BACKEND_DENIES_FRONTEND_BOOLEAN');
  await page.getByRole('switch',{name:'允许 授权测试 用于文献问答',exact:true}).check();
  await wait(async()=>(await rpc('GET','/v0/generation-providers')).providers[0].document_qa_enabled);
  await page.getByRole('button',{name:'授权测试 · fixture-one',exact:true}).click();await page.getByLabel('模型 ID',{exact:true}).fill('fixture-two');await page.getByRole('button',{name:'保存连接',exact:true}).click();
  await wait(async()=>(await rpc('GET','/v0/generation-providers')).providers[0].model==='fixture-two');provider=(await rpc('GET','/v0/generation-providers')).providers[0];
  check(!provider.document_qa_enabled&&!provider.can_answer&&provider.configured,'MODEL_CHANGE_REQUIRES_NEW_GRANT');
  await page.getByRole('button',{name:'保存并启用',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/generation-providers')).providers[0].can_answer);
  check(!await page.evaluate(()=>[...Object.values(localStorage),...Object.values(sessionStorage)].join('').includes('fixture-authorization-secret')),'NO_SECRET_IN_FRONTEND_STORAGE');
  await page.screenshot({path:path.join(evidence,'A-provider.png'),fullPage:true});
  if(stage==='B'||stage==='C')await require('./browser_mvp03_routing.cjs')({page,rpc,nav,input,send,check,wait,calls,setDelay:value=>{delay=value;},setSupportStatus:value=>{supportStatus=value;},setPostFailure:value=>{postFailure=value;},stage,evidence});
  await page.evaluate(()=>globalThis.__testBroker('restart_engine'));await page.reload();await page.locator('.connection').filter({hasText:'本地引擎已连接'}).waitFor();
  provider=(await rpc('GET','/v0/generation-providers')).providers[0];check(provider.document_qa_enabled&&!provider.credential_available&&!provider.can_answer,'RESTART_GRANT_PERSISTS_SECRET_DOES_NOT');
  if(stage==='C')await require('./browser_mvp03_settings.cjs')({page,rpc,nav,check,wait,evidence});
  check(!errors.length,'NO_BROWSER_ERRORS');
  fs.writeFileSync(path.join(evidence,'MVP03-'+stage+'-browser.json'),JSON.stringify({status:'PASS',checks,engine:'REAL PROCESS',transport:'SIMULATED TAURI',api:'LOOPBACK FIXTURE ONLY',native_full_workflow:'NOT_EXECUTED'},null,2));
 }finally{await new Promise(resolve=>server.close(resolve));}
};
