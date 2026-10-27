/* Real browser events and real engine; native IME composition is a separate gate. */
const fs=require('node:fs'),path=require('node:path');
module.exports=async function({page,rpc,evidence,errors,stage,audit}){
 page.setDefaultTimeout(45000);
 const combination={};
 async function settingsCategory(name){const button=page.getByRole('navigation',{name:'设置分类'}).getByRole('button',{name,exact:true});if(await button.count())await button.click();}
 const checks=[];const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);};
 const wait=async test=>{for(let i=0;i<2000;i++){if(await test())return;await page.waitForTimeout(150);}throw Error('ENGINE_WAIT_TIMEOUT');};
 await page.getByRole('button',{name:'导入文件',exact:true}).click();
 await wait(async()=>{const docs=(await rpc('GET','/v0/documents')).documents;return docs.length===2&&docs.every(d=>['ready','partial'].includes(d.parse_status));});
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'问答',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('select[aria-label="问答文献范围"]')?.options.length===3);
 if(stage==='E'){
  const nav=page.getByRole('navigation',{name:'主导航'});
  await nav.getByRole('button',{name:'设置',exact:true}).click();
  await settingsCategory('检索与索引');
  await page.getByRole('button',{name:'选择 E5 目录并建立索引',exact:true}).click();
  await wait(async()=>(await rpc('GET','/v0/index')).ready);
  combination.beforeRestart=audit();check(combination.beforeRestart.vectors>0,'REAL_E5_PERSISTENT_VECTORS');
  await settingsCategory('模型服务');
  await page.getByRole('button',{name:'选择本地生成模型目录',exact:true}).click();
  await wait(async()=>(await rpc('GET','/v0/generator')).configured);
  const original=(await rpc('GET','/v0/documents')).documents;
  await page.evaluate(()=>globalThis.__testBroker('restart_engine'));await page.reload();
  await page.locator('.connection').filter({hasText:/本地引擎(?:已连接|部分可用)/}).waitFor();
  const reopened=(await rpc('GET','/v0/documents')).documents;
  combination.afterRestart=audit();check(combination.beforeRestart.vector_sha256===combination.afterRestart.vector_sha256&&combination.beforeRestart.index_builds===combination.afterRestart.index_builds,'PROCESS_RESTART_INDEX_UNCHANGED');
  check(JSON.stringify(original)===JSON.stringify(reopened),'PROCESS_RESTART_METADATA_UNCHANGED');
  check((await rpc('GET','/v0/index')).ready,'PROCESS_RESTART_INDEX_READY');
  await nav.getByRole('button',{name:'问答',exact:true}).click();
  await wait(async()=>!await page.getByLabel('检索策略',{exact:true}).locator('option[value="hybrid"]').isDisabled());
  await page.getByLabel('检索策略',{exact:true}).selectOption('hybrid');
 }
 const input=page.getByLabel('你的问题',{exact:true});
 const count=async()=>(await rpc('GET','/v0/history/answers')).total;
 await input.fill('   ');await input.press('Enter');await page.waitForTimeout(100);check(await count()===0,'WHITESPACE_NO_SEND');
 await input.fill('BERT');await input.press('Shift+Enter');await input.type('pre-training');check((await input.inputValue()).includes('\n'),'SHIFT_ENTER_NEWLINE');check(await count()===0,'SHIFT_ENTER_NO_SEND');
 await input.dispatchEvent('compositionstart');await input.press('Enter');check(await count()===0,'COMPOSING_NO_SEND');await input.dispatchEvent('compositionend');
 await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',keyCode:229});check(await count()===0,'LEGACY_IME_NO_SEND');
 await input.dispatchEvent('keydown',{key:'Enter',isComposing:true});check(await count()===0,'NATIVE_COMPOSING_FLAG_NO_SEND');
 await input.fill('BERT pre-training');await page.getByRole('button',{name:'发送问题',exact:true}).waitFor({state:'visible'});check(!await page.getByRole('button',{name:'发送问题',exact:true}).isDisabled(),'SUBMIT_READY');await input.press('Enter');await input.press('Enter');await input.press('Enter');
 await wait(async()=>await count()===1);await page.getByRole('heading',{name:'BERT pre-training',exact:true}).waitFor();
 await wait(async()=>!(await rpc('GET','/v0/jobs')).jobs.some(j=>['queued','running'].includes(j.status)));
 check(await count()===1,'ENTER_AND_RAPID_KEYS_ONE_RUN');
 if(stage!=='A'){
  const conversation=(await rpc('GET','/v0/history/conversations')).items[0];
  for(const question of ['这两种任务有何区别？','作者验证了它们的重要性吗？']){
   await wait(async()=>!await page.getByRole('button',{name:'发送问题',exact:true}).isDisabled()||await input.inputValue()==='');
   await input.fill(question);await wait(async()=>!await page.getByRole('button',{name:'发送问题',exact:true}).isDisabled());await input.press('Enter');
   await page.getByRole('heading',{name:question,exact:true}).waitFor();
   await wait(async()=>!(await rpc('GET','/v0/jobs')).jobs.some(j=>['queued','running'].includes(j.status)));
  }
  check((await rpc('GET','/v0/history/conversations')).total===1,'THREE_TURNS_ONE_CONVERSATION');
  check((await rpc('GET',`/v0/conversations/${conversation.id}/turns`)).total===3,'THREE_TURNS_PERSISTED');
  await page.reload();await page.locator('.recent-conversation').first().click();
  await page.waitForFunction(()=>document.querySelectorAll('.conversation-turn').length===3);
  check(await page.locator('.conversation-turn').count()===3,'RELOAD_WHOLE_CONVERSATION');
  for(const turn of await page.locator('.conversation-turn').all()){
    const citation=turn.getByRole('button',{name:/查看引用 1/});
    await citation.first().click();await page.getByRole('heading',{name:'原文核查',exact:true}).waitFor();
    await page.getByRole('button',{name:'返回问答',exact:true}).click();
  }
  check(true,'EACH_TURN_SOURCE_OPENED');
 }
 if(['C','D','E'].includes(stage)){
  const nav=page.getByRole('navigation',{name:'主导航'});
  await nav.getByRole('button',{name:'设置',exact:true}).click();
  for(const [vendor,url] of [['DeepSeek','https://api.deepseek.com/v1'],['OpenAI','https://api.openai.com/v1']]){
   await page.getByRole('tab',{name:new RegExp('^'+vendor)}).click();
   check(await page.getByLabel('接口地址（以 /v1 结尾）',{exact:true}).inputValue()===url,vendor+'_PRESET');
  }
  const protocol=await require('./browser_mvp_provider.cjs')({page,rpc});
  check(protocol.status==='PASS','API_PROTOCOL_AND_DRAFT_SECRET_SAVE');
 }
 if(stage==='E'){
  const nav=page.getByRole('navigation',{name:'主导航'});
  await nav.getByRole('button',{name:'问答',exact:true}).click();
  await page.getByLabel('生成模型',{exact:true}).selectOption('local');
  await input.fill('BERT pre-training tasks');await wait(async()=>!await page.getByRole('button',{name:'发送问题',exact:true}).isDisabled());await input.press('Enter');
  await wait(async()=>(await rpc('GET','/v0/history/answers')).total===5);
  await wait(async()=>!(await rpc('GET','/v0/jobs')).jobs.some(job=>['queued','running'].includes(job.status)));
  const localId=(await rpc('GET','/v0/history/answers')).items[0].id;
  const local=await rpc('GET','/v0/answers/'+localId);
  combination.localQwen={status:local.status,error_code:local.error_code,claims:local.claims.length,evidence:local.evidence.length,model_history:local.model_history};
  check(local.model_history.some(item=>item.fingerprint.model==='Qwen/Qwen2.5-1.5B-Instruct-GGUF'),'REAL_LOCAL_QWEN_INVOKED');
  check(['completed','refused'].includes(local.status),'LOCAL_QWEN_VALID_STRUCTURED_RESULT_OR_REFUSAL');
  combination.afterProviders=audit();check(combination.afterProviders.vector_sha256===combination.beforeRestart.vector_sha256&&combination.afterProviders.index_builds===combination.beforeRestart.index_builds,'MODEL_SWITCH_NO_EMBEDDING_RECOMPUTE');
 }
 if(['D','E'].includes(stage)){
  await wait(async()=>(await rpc('GET','/v0/documents')).documents.every(doc=>doc.metadata_extraction.status==='completed'));
  const doc=(await rpc('GET','/v0/documents')).documents.find(doc=>doc.title.startsWith('BERT:'));
  check(doc.authors.length===4&&doc.year===2019&&doc.abstract.includes('We introduce')&&!doc.doi,'REAL_PDF_AUTOMATIC_METADATA');
  const nav=page.getByRole('navigation',{name:'主导航'});
  await nav.getByRole('button',{name:'文献',exact:true}).click();await page.getByRole('button',{name:doc.title,exact:true}).click();
  check(await page.locator('.paper-detail input').count()===0,'DETAIL_DEFAULT_READ_ONLY');
  await page.getByRole('button',{name:'发表年份来源 · 第 1 页',exact:true}).click();
  await page.getByRole('heading',{name:'PDF 阅读',exact:true}).waitFor();await page.getByRole('button',{name:'返回文献',exact:true}).click();
  await page.getByRole('button',{name:'编辑与核对',exact:true}).click();
  await page.getByLabel('题名',{exact:true}).fill('BERT 人工核对题名');
  await page.getByRole('button',{name:'保留并确认发表年份',exact:true}).click();
  await page.getByRole('button',{name:'保存元数据',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByRole('button',{name:'BERT 人工核对题名',exact:true}).waitFor();
  const parseCount=(await rpc('GET','/v0/jobs')).jobs.filter(job=>job.type==='parse_page').length;
  await page.getByRole('button',{name:'重新解析',exact:true}).click();
  await wait(async()=>{const jobs=(await rpc('GET','/v0/jobs')).jobs;return jobs.filter(job=>job.type==='parse_page').length>parseCount&&!jobs.some(job=>['queued','running'].includes(job.status));});
  const saved=(await rpc('GET','/v0/documents')).documents.find(item=>item.doc_version_id===doc.doc_version_id);
  check(saved.title==='BERT 人工核对题名'&&saved.metadata_origins.title==='manual'&&saved.metadata_origins.year==='confirmed','MANUAL_METADATA_SURVIVES_REPARSE');
  check(Object.keys(saved.metadata_candidates).length===5,'CANDIDATE_PROVENANCE_RETAINED');
  await page.screenshot({path:path.join(evidence,'stage-'+stage+'-metadata.png'),fullPage:true});
 }
 if(stage==='E'){
  const docs=(await rpc('GET','/v0/documents')).documents;
  const conversations=(await rpc('GET','/v0/history/conversations')).items;
  const turns=await rpc('GET',`/v0/conversations/${conversations[0].id}/turns`);
  const before=audit();
  await page.evaluate(()=>globalThis.__testBroker('restart_engine'));await page.reload();
  await page.locator('.connection').filter({hasText:/本地引擎(?:已连接|部分可用)/}).waitFor();
  const restarted=await rpc('GET',`/v0/conversations/${conversations[0].id}/turns`);
  fs.writeFileSync(path.join(evidence,'E-restart-comparison-'+Date.now()+'.json'),JSON.stringify({turns,restarted,combination},null,2));
  check(JSON.stringify(turns)===JSON.stringify(restarted),'ENGINE_RESTART_ALL_TURNS_PERSIST');
  check(JSON.stringify(docs)===JSON.stringify((await rpc('GET','/v0/documents')).documents),'MANUAL_AND_PROVENANCE_SURVIVE_ENGINE_RESTART');
  check(!(await rpc('GET','/v0/generation-providers')).providers[0].credential_available,'RESTART_NO_API_SECRET');
  const nav=page.getByRole('navigation',{name:'主导航'});await nav.getByRole('button',{name:'设置',exact:true}).click();
  await settingsCategory('备份与恢复');
  await page.getByRole('button',{name:'创建备份',exact:true}).click();await page.getByText('已完成备份',{exact:true}).waitFor();
  await page.getByRole('button',{name:'从备份恢复副本',exact:true}).click();await page.getByRole('button',{name:'使用此恢复副本',exact:true}).waitFor();
  await wait(async()=>!(await rpc('GET','/v0/jobs')).jobs.some(job=>['queued','running','retry_wait'].includes(job.status)));
  const restoreRecord=(await rpc('GET','/v0/backups')).records.find(item=>item.kind==='restored');
  const restoredTarget=await rpc('GET',`/v0/internal/restored-workspaces/${restoreRecord.id}`);
  await page.getByRole('button',{name:'使用此恢复副本',exact:true}).click();
  await wait(async()=>{await settingsCategory('工作区与数据');return await page.locator('#workspace-directory').inputValue()===restoredTarget.data_root;});
  check(JSON.stringify(docs)===JSON.stringify((await rpc('GET','/v0/documents')).documents),'BACKUP_RESTORE_METADATA_AND_PROVENANCE');
  const restored=await rpc('GET',`/v0/conversations/${conversations[0].id}/turns`);
  check(JSON.stringify(turns)===JSON.stringify(restored),'BACKUP_RESTORE_ALL_TURNS_AND_CITATIONS');
  combination.afterRestore=audit();check(combination.afterRestore.vector_sha256===before.vector_sha256,'BACKUP_RESTORE_VECTOR_BYTES');
  check(!combination.afterRestore.secret_in_db,'NO_SESSION_SECRET_IN_BACKUP');
  await settingsCategory('检索与索引');
  await page.getByRole('button',{name:'选择 E5 目录并建立索引',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/index')).ready);
  combination.rebuilt=audit();check(combination.rebuilt.active_index.new_embeddings===0&&combination.rebuilt.active_index.reused_embeddings===before.vectors,'RESTORED_DERIVED_INDEX_REUSES_ALL_VECTORS');
  await nav.getByRole('button',{name:'问答',exact:true}).click();check(await page.getByLabel('生成模型',{exact:true}).inputValue()==='extractive','WORKSPACE_CHANGE_NO_EXTERNAL_AUTO_SELECTION');
  await wait(async()=>!await page.getByLabel('检索策略',{exact:true}).locator('option[value="hybrid"]').isDisabled());
  await page.locator('.recent-conversation').first().click();await page.waitForFunction(()=>document.querySelectorAll('.conversation-turn').length===5);
  await page.screenshot({path:path.join(evidence,'stage-E-conversation.png'),fullPage:true});
  await page.getByRole('button',{name:'新会话',exact:true}).click();
  await page.getByRole('heading',{name:'从文献出发，找到有据可查的答案',exact:true}).waitFor();
  check((await rpc('GET','/v0/history/conversations')).total===2,'EXPLICIT_NEW_CONVERSATION_CREATED');
  check(await page.locator('.conversation-turn').count()===0,'NEW_CONVERSATION_EMPTY_AND_ISOLATED');
  check((await rpc('GET',`/v0/conversations/${conversations[0].id}/turns`)).total===5,'NEW_CONVERSATION_PRESERVES_OLD_TURNS');
 }
 check(errors.length===0,'NO_BROWSER_ERRORS');
 fs.writeFileSync(path.join(evidence,'stage-'+stage+'-browser.json'),JSON.stringify({status:'PASS',checks,combination,native_IME:'NOT_EXECUTED',transport:'simulated Tauri; real engine'},null,2));
};
