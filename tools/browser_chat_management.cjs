/* Real isolated engine/PDF/index; simulated Tauri transport; loopback model fixture. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {once}=require('node:events');
module.exports=async function({page,rpc,evidence,errors,audit}) {
 page.setDefaultTimeout(20000);
 await page.context().grantPermissions(['clipboard-read','clipboard-write']);
 const checks=[],check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);console.log('PASS '+name);};
 const wait=async(fn)=>{for(let i=0;i<1000;i++){if(await fn())return;await page.waitForTimeout(100);}throw Error('CHAT_WAIT_TIMEOUT');};
 const nav=page.getByRole('navigation',{name:'主导航'}),input=page.getByLabel('你的问题',{exact:true});
 const chat=page.locator('.chat-scroll'),right=page.locator('.chat-evidence');
 await page.getByRole('button',{name:'导入文件',exact:true}).click();
 await wait(async()=>{const docs=(await rpc('GET','/v0/documents')).documents;return docs.length===2&&docs.every(doc=>['ready','partial'].includes(doc.parse_status));});
 const restartJob=await page.evaluate(()=>globalThis.__testBroker('test_seed_restart_job'));
 await page.evaluate(()=>globalThis.__testBroker('restart_engine',{force:true}));
 await page.reload();
 await nav.getByRole('button',{name:'文献',exact:true}).click();
 await wait(async()=>(await rpc('GET','/v0/jobs/'+restartJob)).status==='retry_wait');
 const cancelRestart=page.locator('.processing-queue').getByRole('button',{name:'取消建立检索索引',exact:true});
 await cancelRestart.waitFor();await cancelRestart.click();
 await wait(async()=>(await rpc('GET','/v0/jobs/'+restartJob)).status==='cancelled');
 check(true,'RESTART_RETRY_WAIT_HAS_REACHABLE_UI_CANCEL');
 const docs=(await rpc('GET','/v0/documents')).documents;
 const bert=docs.find(doc=>doc.title.includes('BERT')),dpr=docs.find(doc=>!doc.title.includes('BERT'));
 await page.evaluate(()=>globalThis.__testBroker('choose_embedding_model',{backend:'sqlite-vec'}));
 await wait(async()=>(await rpc('GET','/v0/index')).ready);
 const baseline=audit();check(baseline.vectors>0,'REAL_E5_INDEX_BUILT');
 await nav.getByRole('button',{name:'问答',exact:true}).click();
 async function send(question){const previous=(await rpc('GET','/v0/history/answers')).items[0]?.id;await input.fill(question);await page.getByRole('button',{name:'发送问题',exact:true}).click();await page.getByRole('heading',{name:question,exact:true}).last().waitFor();await wait(async()=>{const rows=(await rpc('GET','/v0/history/answers')).items;return rows[0]&&rows[0].id!==previous&&rows[0].question===question&&['completed','refused','failed'].includes(rows[0].status);});const id=(await rpc('GET','/v0/history/answers')).items[0].id;await wait(async()=>await page.locator(`[data-run-id="${id}"]`).count()>0);return rpc('GET','/v0/answers/'+id);}
 await page.getByLabel('问答文献范围',{exact:true}).selectOption(bert.doc_version_id);
 const first=await send('该文献中主要的贡献是什么');check(first.evidence.length>0,'BERT_EXTRACTIVE_EVIDENCE');
 await page.locator(`[data-run-id="${first.id}"]`).getByRole('button',{name:'复制问题',exact:true}).click();check(await page.evaluate(()=>navigator.clipboard.readText())===first.question,'QUESTION_COPY_EXACT');
 await page.getByLabel('问答文献范围',{exact:true}).selectOption(dpr.doc_version_id);
 const second=await send('dense passage retrieval');
 await wait(async()=>await right.getAttribute('data-answer-run')===second.id);
 check(await chat.locator('blockquote,.pipeline-diagnostics,.citation-cards,.claim-status').count()===0,'MAIN_CHAT_HAS_NO_DIAGNOSTICS_OR_QUOTES');
 check((await right.innerText()).includes(dpr.title)&&!(await right.locator('.turn-scope').innerText()).includes(bert.title),'SECOND_TURN_SCOPE_ISOLATED');
 await page.locator(`[data-run-id="${first.id}"] .turn-question`).click();
 await wait(async()=>await right.getAttribute('data-answer-run')===first.id);
 check((await right.locator('.turn-scope').innerText()).includes(bert.title)&&!(await right.locator('.turn-scope').innerText()).includes(dpr.title),'HISTORICAL_TURN_SCOPE_ISOLATED');
 await right.getByRole('button',{name:'打开证据 1',exact:true}).click();await page.getByRole('heading',{name:'原文核查',exact:true}).waitFor();await page.locator('canvas').first().waitFor();
 check(await page.locator('canvas').first().evaluate(node=>node.width>0&&node.height>0),'ORIGINAL_PDF_RENDERED');await page.getByRole('button',{name:'返回问答',exact:true}).click();
 const info=await send('当前文献库中拥有多少篇文献');await wait(async()=>await right.getAttribute('data-answer-run')===info.id);
 check((await right.innerText()).includes('未执行文献检索')&&!await right.locator('.turn-source').count(),'SYSTEM_INFO_HAS_NO_PAPER_CITATIONS');
 await page.locator(`[data-run-id="${info.id}"]`).getByRole('button',{name:'复制回答',exact:true}).click();check(await page.evaluate(()=>navigator.clipboard.readText())===info.result.text,'SYSTEM_ANSWER_COPY_EXACT');
 const conversation=info.conversation_id;
 async function menu(container,name){await container.locator('.conversation-menu-toggle').click();await container.getByRole('menuitem',{name,exact:true}).click();}
 let row=page.locator('.sidebar-history>.recent-conversations .conversation-row').filter({has:page.locator('.recent-conversation.selected')});
 await menu(row,'重命名');await page.getByLabel('对话名称',{exact:true}).fill('CHAT-01 管理测试');await page.getByRole('button',{name:'保存名称',exact:true}).click();
 await wait(async()=>(await rpc('GET','/v0/history/conversations')).items.some(item=>item.title==='CHAT-01 管理测试'));
 check((await rpc('GET',`/v0/conversations/${conversation}/turns`)).total===3,'RENAME_PRESERVES_TURNS');
 row=page.locator('.sidebar-history>.recent-conversations .conversation-row').filter({hasText:'CHAT-01 管理测试'});await menu(row,'归档');
 await wait(async()=>!(await rpc('GET','/v0/history/conversations')).items.some(item=>item.id===conversation));
 await page.locator('.sidebar-history>.recent-conversations').getByText('CHAT-01 管理测试',{exact:true}).waitFor({state:'hidden'});check(true,'ARCHIVE_REMOVED_RECENT');
 await page.getByRole('button',{name:'已归档对话',exact:true}).click();let dialog=page.getByRole('dialog',{name:'已归档对话',exact:true});
 await dialog.getByRole('button',{name:'恢复',exact:true}).waitFor();check(await dialog.getByRole('button',{name:'恢复',exact:true}).isVisible(),'RESTORE_DIRECTLY_VISIBLE');
 await dialog.getByRole('button',{name:'恢复',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/history/archived_conversations')).total===0);await dialog.getByRole('button',{name:'关闭',exact:true}).click();
 row=page.locator('.sidebar-history>.recent-conversations .conversation-row').filter({hasText:'CHAT-01 管理测试'});await menu(row,'归档');await page.getByRole('button',{name:'已归档对话',exact:true}).click();
 await dialog.getByRole('button',{name:/CHAT-01 管理测试/}).first().click();
 await page.getByText('此对话已归档。',{exact:false}).waitFor();check((await rpc('GET',`/v0/conversations/${conversation}/turns`)).items[0].evidence.length>0,'ARCHIVE_PRESERVES_CITATIONS');
 await page.getByRole('button',{name:'恢复后继续提问',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/history/conversations')).items.some(item=>item.id===conversation));
 check((await rpc('GET','/v0/history/archived_conversations')).total===0,'RESTORE_RECENT');
 // Configure an actual loopback HTTP provider. No cloud calls or real key.
 const calls=[];let delay=0;
 const server=http.createServer((req,res)=>{let raw='';req.on('data',part=>raw+=part);req.on('end',()=>{if(req.headers.authorization!=='Bearer local-protocol-fixture-key'){res.writeHead(401);res.end('{}');return;}calls.push(req.url);res.setHeader('Content-Type','application/json');if(req.method==='GET'){res.end(JSON.stringify({data:[{id:'chat-fixture',name:'Fixture Flash'},{id:'chat-fixture-pro',name:'Fixture Pro'},{id:'another-fixture'}]}));return;}const body=JSON.parse(raw);const support=body.messages[0].content.includes('entire claim');const result=support?{status:'supported',reason:'Local protocol fixture only'}:{claims:[{text:'CHAT-01 protocol answer',evidence:[{citation_id:'E1'}]}]};setTimeout(()=>res.end(JSON.stringify({choices:[{message:{content:JSON.stringify(result)}}]})),delay);});});server.listen(0,'127.0.0.1');await once(server,'listening');
 try {
  await nav.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('tab',{name:/^自定义兼容接口/}).click();
  await page.getByLabel('连接名称',{exact:true}).fill('CHAT-01 API');await page.getByLabel('接口地址（以 /v1 结尾）',{exact:true}).fill(`http://127.0.0.1:${server.address().port}/v1`);await page.getByLabel('API Key',{exact:true}).fill('local-protocol-fixture-key');await page.getByLabel('模型 ID',{exact:true}).fill('chat-fixture');await page.getByRole('button',{name:'保存并启用',exact:true}).click();
  await wait(async()=>(await rpc('GET','/v0/generation-providers')).providers[0]?.can_answer);
  const provider=(await rpc('GET','/v0/generation-providers')).providers[0];
  for(let i=0;i<3;i++){const rev=(await rpc('GET','/v0/generation-providers')).providers[0].revision;await page.getByRole('button',{name:'保存连接',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/generation-providers')).providers[0].revision>rev);}
  check((await rpc('GET','/v0/generation-providers')).providers.length===1,'REPEATED_SAVE_ONE_CONFIG');
  await page.getByRole('button',{name:'测试连接',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/generation-providers')).providers[0].connection_verified);
  const catalog=page.getByLabel('服务模型列表',{exact:true});await catalog.waitFor();check(await catalog.locator('option').count()===4,'FULL_MODEL_CATALOG_NOT_FILTERED_BY_CURRENT_ID');await catalog.selectOption('chat-fixture-pro');check(await page.getByLabel('模型 ID',{exact:true}).inputValue()==='chat-fixture-pro','CATALOG_SELECTION_UPDATES_MODEL_ID');await catalog.selectOption('chat-fixture');
  for(const mode of ['success-refresh','failure-refresh','success-callback','failure-callback']){
   await page.evaluate(mode=>globalThis.__testBroker('test_probe_fault',{mode}),mode);
   const button=page.getByRole('button',{name:'测试连接',exact:true});await button.click();
   await page.getByRole('alert').filter({hasText:'刷新连接状态失败'}).waitFor();
   await wait(async()=>await button.isEnabled());
   check(true,'PROBE_BUSY_CLEARED_'+mode.toUpperCase().replace('-','_'));
  }
  await page.evaluate(()=>globalThis.__testBroker('test_probe_fault',{mode:'unmount'}));
  await page.getByRole('button',{name:'测试连接',exact:true}).click();
  await nav.getByRole('button',{name:'问答',exact:true}).click();await page.waitForTimeout(1000);
  await nav.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('tab',{name:/^自定义兼容接口/}).click();
  await wait(async()=>await page.getByRole('button',{name:'测试连接',exact:true}).isEnabled());
  check(errors.length===0,'PROBE_UNMOUNT_NO_UNHANDLED_REJECTION');
  await nav.getByRole('button',{name:'问答',exact:true}).click();await page.getByLabel('生成模型',{exact:true}).selectOption(provider.id);await page.getByLabel('问答文献范围',{exact:true}).selectOption(bert.doc_version_id);
  delay=2500;await input.fill('BERT long running fixture');await page.getByRole('button',{name:'发送问题',exact:true}).click();
  await page.locator('[data-pending-question]').waitFor().catch(()=>{});
  await wait(async()=>{const e=await chat.evaluate(node=>{const last=node.querySelector('.conversation-turn:last-child');return last?Math.abs(last.getBoundingClientRect().top-node.getBoundingClientRect().top):999;});return e<20;});check(true,'NEW_QUESTION_SCROLLS_BEFORE_GENERATION');
  await wait(async()=>(await rpc('GET','/v0/history/answers')).items[0].question==='BERT long running fixture');
  const running=(await rpc('GET','/v0/history/answers')).items[0];
  let code='';try{await rpc('POST',`/v0/conversations/${conversation}/manage`,{action:'delete'});}catch(err){code=err.message;}
  check(code==='CONVERSATION_BUSY','RUNNING_DELETE_REFUSED');
  await chat.evaluate(node=>{node.scrollTop=0;});const top=await chat.evaluate(node=>node.scrollTop);const rightTop=await right.evaluate(node=>node.scrollTop);
  await wait(async()=>(await rpc('GET','/v0/answers/'+running.id)).status==='completed');await page.waitForTimeout(1500);
  check(Math.abs(await chat.evaluate(node=>node.scrollTop)-top)<2,'POLLING_AND_COMPLETION_DO_NOT_STEAL_SCROLL');
  check(Math.abs(await right.evaluate(node=>node.scrollTop)-rightTop)<2,'CHAT_SCROLL_DOES_NOT_SCROLL_RIGHT');
  await page.locator(`[data-run-id="${running.id}"] .turn-question`).click();await wait(async()=>await right.getAttribute('data-answer-run')===running.id);
  check((await right.innerText()).includes('CHAT-01 protocol answer')&&(await right.innerText()).includes('同一模型自检'),'CLAIMS_AND_SUPPORT_IN_RIGHT');
  check(await chat.locator('.answer-body').last().innerText()==='CHAT-01 protocol answer','GENERATED_BODY_PRESERVED');
  await page.locator(`[data-run-id="${running.id}"]`).getByRole('button',{name:'复制回答',exact:true}).click();check(await page.evaluate(()=>navigator.clipboard.readText())==='CHAT-01 protocol answer','MODEL_ANSWER_COPY_BODY_ONLY');
  // Populate genuine system-query turns to exercise cursor pagination without inference.
  for(let n=0;n<32;n++){const run=await rpc('POST','/v0/answers',{question:'你是什么模型',version_ids:[],mode:'extractive',strategy:'keyword',conversation_id:conversation});await wait(async()=>(await rpc('GET','/v0/answers/'+run.id)).status==='completed');}
  await page.reload();await page.locator('.recent-conversation').filter({hasText:'CHAT-01 管理测试'}).click();await wait(async()=>await chat.locator('[data-run-id]').count()===30);
  const lastTop=await chat.evaluate(node=>node.querySelector('.conversation-turn:last-child').getBoundingClientRect().top-node.getBoundingClientRect().top);
  check(Math.abs(lastTop)<20,'OPEN_HISTORY_LOCATES_LAST_TURN');
  await chat.evaluate(node=>{node.scrollTop=0;});const anchor=await chat.locator('[data-run-id]').first().getAttribute('data-run-id');
  await page.getByRole('button',{name:'加载更早消息',exact:true}).click();await wait(async()=>await chat.locator('[data-run-id]').count()===36);
  check(await chat.evaluate(node=>node.scrollTop)>0,'PREPEND_PRESERVES_VIEWPORT');
  const beforePoll=await chat.evaluate(node=>node.scrollTop);await page.waitForTimeout(1600);check(Math.abs(await chat.evaluate(node=>node.scrollTop)-beforePoll)<2,'OLD_MESSAGES_NOT_RESET_BY_POLL');
  check(!!anchor,'STABLE_TURN_IDS');
  // Repeat whole engine startup; no migration/init/refresh may create providers.
  for(let n=0;n<3;n++){
    await page.evaluate(()=>globalThis.__testBroker('restart_engine'));await page.reload();await page.locator('.connection').filter({hasText:/本地引擎(?:已连接|部分可用)/}).waitFor();
    const rows=(await rpc('GET','/v0/generation-providers')).providers;check(rows.length===1&&rows[0].id===provider.id&&!rows[0].credential_available,'RESTART_'+n+'_ONE_CONFIG_NO_SECRET');
    await nav.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('tab',{name:/^自定义兼容接口/}).click();await wait(async()=>await page.getByLabel('模型 ID',{exact:true}).inputValue()==='chat-fixture');
    await page.getByRole('button',{name:'保存连接',exact:true}).click();await page.waitForTimeout(150);await page.reload();
    await nav.getByRole('button',{name:'问答',exact:true}).click();await page.getByRole('button',{name:'新会话',exact:true}).click();
    check(await page.getByLabel('生成模型',{exact:true}).locator('option').count()===3,'SELECTOR_'+n+'_NO_DUPLICATES');
  }
  // Delete only our test conversation, after explicit UI confirmation; another remains.
  await page.locator('.recent-conversation').filter({hasText:'CHAT-01 管理测试'}).click();await wait(async()=>await chat.locator('[data-run-id]').count()===30);
  row=page.locator('.sidebar-history>.recent-conversations .conversation-row').filter({hasText:'CHAT-01 管理测试'});await menu(row,'删除');
  await page.getByRole('alertdialog',{name:'删除对话确认'}).getByRole('button',{name:'取消',exact:true}).click();check((await rpc('GET',`/v0/conversations/${conversation}/turns`)).total===36,'CANCEL_DELETE_PRESERVES');
  await menu(row,'删除');await page.getByRole('alertdialog',{name:'删除对话确认'}).getByRole('button',{name:'确认删除',exact:true}).click();
  await wait(async()=>!(await rpc('GET','/v0/history/conversations')).items.some(item=>item.id===conversation));check(await chat.locator('[data-run-id]').count()===0,'DELETE_CURRENT_RETURNS_HOME');
  const after=audit();check(after.vector_sha256===baseline.vector_sha256&&after.index_builds===baseline.index_builds,'DELETE_AND_RESTART_PRESERVE_REAL_VECTORS');check((await rpc('GET','/v0/documents')).documents.length===2,'DELETE_PRESERVES_PDFS');check((await rpc('GET','/v0/history/conversations')).total>=1,'DELETE_PRESERVES_OTHER_CONVERSATIONS');
  const archiveId=(await rpc('GET','/v0/history/conversations')).items[0].id;await rpc('POST',`/v0/conversations/${archiveId}/manage`,{action:'archive'});
  await page.evaluate(()=>globalThis.__testBroker('restart_engine'));await page.reload();check((await rpc('GET','/v0/history/archived_conversations')).items.some(item=>item.id===archiveId),'ARCHIVE_SURVIVES_RESTART');
  check(!(await rpc('GET','/v0/history/conversations')).items.some(item=>item.id===conversation),'DELETE_SURVIVES_RESTART');
  check(!audit().secret_in_db,'NO_KEY_IN_SQLITE');
  await page.getByRole('button',{name:'新会话',exact:true}).click();await send('你是什么模型');
  for(const width of [1400,1000,720]){await page.setViewportSize({width,height:900});await page.waitForTimeout(100);check(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+2),'BOUNDED_LAYOUT_'+width);await page.screenshot({path:path.join(evidence,'chat-'+width+'.png'),fullPage:true});}
  await page.waitForTimeout(1100);
  const countTurns=()=>fs.readdirSync(evidence).filter(name=>name.startsWith('browser-commands-')&&name.endsWith('.jsonl')).reduce((total,name)=>total+fs.readFileSync(path.join(evidence,name),'utf8').split('\n').filter(Boolean).map(line=>JSON.parse(line)).filter(record=>record.command==='conversation_turns').length,0);
  const settledReads=countTurns();await page.waitForTimeout(2200);
  check(countTurns()===settledReads,'COMPLETED_CONVERSATION_STOPS_FULL_EVIDENCE_POLLING');
  check(!errors.length,'NO_BROWSER_ERRORS');
  fs.writeFileSync(path.join(evidence,'CHAT-01-browser.json'),JSON.stringify({status:'PASS',checks,transport:'SIMULATED TAURI',engine:'REAL PROCESS',model:'LOOPBACK FIXTURE',cloud_calls:0,before:baseline,after},null,2));
 }finally{await new Promise(resolve=>server.close(resolve));}
};
