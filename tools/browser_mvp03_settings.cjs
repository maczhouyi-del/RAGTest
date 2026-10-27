/* Category isolation, real E5 index, restart, backup/restore. No native dialogs certified. */
const path=require('node:path'),fs=require('node:fs');
module.exports=async function({page,rpc,nav,check,wait,evidence,audit}){
 const names=['模型服务','检索与索引','文献解析','工作区与数据','备份与恢复','高级与诊断'];
 const navigation=()=>page.getByRole('navigation',{name:'设置分类'});
 async function category(name){await navigation().getByRole('button',{name,exact:true}).click();await page.getByRole('region',{name,exact:true}).waitFor();}
 await nav.getByRole('button',{name:'设置',exact:true}).click();
 for(const name of names){
  await category(name);
  check(await page.locator('.settings-category-content').count()===1,'SINGLE_CATEGORY_'+name);
  check(await page.getByRole('button',{name:'创建备份',exact:true}).count()===(name==='备份与恢复'?1:0),'BACKUPS_ONLY_IN_BACKUP_CATEGORY_'+name);
  check(await page.getByRole('tablist',{name:'生成模型类型'}).count()===(name==='模型服务'?1:0),'GENERATION_ONLY_IN_MODEL_CATEGORY_'+name);
  check(await page.getByRole('button',{name:'选择 E5 目录并建立索引',exact:true}).count()===(name==='检索与索引'?1:0),'INDEX_ONLY_IN_INDEX_CATEGORY_'+name);
  await page.screenshot({path:path.join(evidence,'C-category-'+names.indexOf(name)+'.png'),fullPage:true});
 }
 await category('模型服务');await page.getByRole('tab',{name:/^自定义兼容接口/}).click();
 const grant=await rpc('GET','/v0/generation-providers');
 check(grant.providers[0].document_qa_enabled&&!grant.providers[0].can_answer,'CATEGORY_REAL_GRANT_AND_MISSING_CREDENTIALS');
 await page.getByRole('switch',{name:'允许 授权测试 用于文献问答',exact:true}).waitFor();
 check(await page.getByRole('switch',{name:'允许 授权测试 用于文献问答',exact:true}).isChecked(),'GRANT_DISPLAY_AFTER_CATEGORY_SWITCH');
 await page.getByRole('tab',{name:/^本地模型/}).click();await page.getByRole('button',{name:'选择本地生成模型目录',exact:true}).click();
 await wait(async()=>(await rpc('GET','/v0/generator')).configured);
 await category('文献解析');
 check(await page.getByRole('button',{name:'选择或重新校验 OCR 语言目录',exact:true}).count()===1&&await page.getByRole('button',{name:'选择或重新校验布局与表格目录',exact:true}).count()===1,'PARSING_ACTIONS_PRESERVED');
 check(await page.getByRole('button',{name:'选择或重新校验生成模型',exact:true}).count()===0,'PARSING_CATEGORY_NO_DUPLICATE_GENERATOR');
 await category('工作区与数据');
 check(await page.getByRole('heading',{name:'文献身份与文件版本',exact:true}).count()===1&&await page.getByRole('heading',{name:'文献停用与撤稿标记',exact:true}).count()===1,'IDENTITY_AND_LIFECYCLE_PRESERVED');
 const oldRoot=await page.locator('#workspace-directory').inputValue();
 await category('检索与索引');await page.getByLabel('默认检索策略',{exact:true}).selectOption('hybrid');
 await page.getByRole('button',{name:'选择 E5 目录并建立索引',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/index')).ready);
 const indexed=audit();check(indexed.vectors>0&&!indexed.secret_in_db,'REAL_E5_PERSISTENCE_NO_SECRET');
 await category('模型服务');await page.getByRole('tab',{name:/^本地模型/}).click();await page.getByText('资源已配置',{exact:true}).waitFor();
 await category('检索与索引');
 check(await page.getByLabel('默认检索策略',{exact:true}).inputValue()==='hybrid','CATEGORY_SWITCH_RETAINS_STRATEGY');
 check((await rpc('GET','/v0/index')).ready,'CATEGORY_SWITCH_RETAINS_INDEX');
 await nav.getByRole('button',{name:'问答',exact:true}).click();await page.getByLabel('生成模型',{exact:true}).selectOption('local');
 await nav.getByRole('button',{name:'设置',exact:true}).click();await category('高级与诊断');
 await page.getByText(/Qwen\/Qwen2.5-1.5B-Instruct-GGUF/).first().waitFor();
 check(await page.getByRole('region',{name:'高级与诊断'}).getByText('文献问答已启用',{exact:false}).count()>0,'DIAGNOSTICS_REAL_PROVIDER_GRANT');
 check(audit().vector_sha256===indexed.vector_sha256&&audit().index_builds===indexed.index_builds,'GENERATION_SWITCH_NO_REEMBEDDING');
 // Browser events exercise the layout at minimum desktop width, not a native OS window.
 await page.setViewportSize({width:720,height:900});
 for(const name of names){
  await category(name);
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('.settings-layout,.settings-category-content')].every(el=>el.scrollWidth<=el.clientWidth+1)),'NARROW_LAYOUT_'+name);
  if(name==='模型服务'){await page.getByRole('tab',{name:/^自定义兼容接口/}).click();check(await page.evaluate(()=>document.querySelector('.settings-category-content').scrollWidth<=document.querySelector('.settings-category-content').clientWidth+1),'NARROW_API_FORM');}
  await page.screenshot({path:path.join(evidence,'C-narrow-'+names.indexOf(name)+'.png'),fullPage:true});
 }
 await page.setViewportSize({width:1586,height:992});
 const docs=(await rpc('GET','/v0/documents')).documents;
 const conversations=(await rpc('GET','/v0/history/conversations')).items;
 const turns=await Promise.all(conversations.map(c=>rpc('GET',`/v0/conversations/${c.id}/turns`)));
 await page.evaluate(()=>globalThis.__testBroker('restart_engine'));await page.reload();await page.locator('.connection').filter({hasText:/本地引擎(?:已连接|部分可用)/}).waitFor();
 check((await rpc('GET','/v0/index')).ready&&audit().vector_sha256===indexed.vector_sha256,'RESTART_INDEX_PERSISTS');
 check(JSON.stringify(docs)===JSON.stringify((await rpc('GET','/v0/documents')).documents),'RESTART_METADATA_PERSISTS');
 await nav.getByRole('button',{name:'设置',exact:true}).click();await category('备份与恢复');
 await page.getByRole('button',{name:'创建备份',exact:true}).click();await page.getByText('已完成备份',{exact:true}).waitFor();
 await page.getByRole('button',{name:'从备份恢复副本',exact:true}).click();await page.getByRole('button',{name:'使用此恢复副本',exact:true}).waitFor();
 await wait(async()=>!(await rpc('GET','/v0/jobs')).jobs.some(job=>['queued','running','retry_wait'].includes(job.status)));
 const restored=(await rpc('GET','/v0/backups')).records.find(record=>record.kind==='restored');
 const target=await rpc('GET',`/v0/internal/restored-workspaces/${restored.id}`);
 await page.getByRole('button',{name:'使用此恢复副本',exact:true}).click();
 await wait(async()=>{try{await category('工作区与数据');return await page.locator('#workspace-directory').inputValue()===target.data_root;}catch{return false;}});
 check(target.data_root!==oldRoot,'RESTORE_NEW_WORKSPACE_ORIGINAL_PRESERVED');
 check(JSON.stringify(docs)===JSON.stringify((await rpc('GET','/v0/documents')).documents),'BACKUP_RESTORE_DOCUMENTS_METADATA_PROVENANCE');
 const restoredTurns=await Promise.all(conversations.map(c=>rpc('GET',`/v0/conversations/${c.id}/turns`)));
 check(JSON.stringify(turns)===JSON.stringify(restoredTurns),'BACKUP_RESTORE_ALL_CONVERSATIONS_EVIDENCE');
 const provider=(await rpc('GET','/v0/generation-providers')).providers[0];
 check(provider.document_qa_enabled&&!provider.credential_available&&!provider.can_answer,'BACKUP_RESTORE_AUTH_WITHOUT_SECRET');
 check(audit().vector_sha256===indexed.vector_sha256&&!audit().secret_in_db,'BACKUP_RESTORE_VECTOR_BYTES_NO_SECRET');
 await category('检索与索引');await page.getByRole('button',{name:'选择 E5 目录并建立索引',exact:true}).click();await wait(async()=>(await rpc('GET','/v0/index')).ready);
 const rebuilt=audit();check(rebuilt.active_index.new_embeddings===0&&rebuilt.active_index.reused_embeddings===indexed.vectors,'RESTORED_INDEX_REUSES_VECTORS');
 await nav.getByRole('button',{name:'问答',exact:true}).click();check(await page.getByLabel('生成模型',{exact:true}).inputValue()==='extractive','RESTORE_NO_EXTERNAL_AUTO_SELECTION');
 fs.writeFileSync(path.join(evidence,'C-index-persistence.json'),JSON.stringify({indexed,rebuilt,documents:docs.length,conversations:conversations.length,turns:turns.reduce((sum,c)=>sum+c.total,0)},null,2));
};
