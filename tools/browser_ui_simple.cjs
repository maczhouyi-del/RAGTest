/* UI-02 visual/interaction checks. Real isolated engine/PDF/E5; simulated Tauri. */
const fs=require('node:fs'),path=require('node:path');
module.exports=async function({page,rpc,evidence,errors,stage}) {
 const checks=[],screenshots=[];
 const check=(ok,name)=>{if(!ok)throw Error('UI02_'+name);checks.push(name);console.log('PASS UI02_'+name);};
 const nav=page.getByRole('navigation',{name:'主导航'});
 const category=async name=>{await page.getByRole('navigation',{name:'设置分类'}).getByRole('button',{name,exact:true}).click();await page.getByRole('region',{name,exact:true}).waitFor();};
 async function wait(fn){for(let i=0;i<600;i++){if(await fn())return;await page.waitForTimeout(100);}throw Error('UI02_WAIT_TIMEOUT');}
 async function shot(name){await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(100);const file=`ui02-${name}.png`;await page.screenshot({path:path.join(evidence,file),fullPage:true});screenshots.push(file);}
 async function fit(width,name){
  await page.setViewportSize({width,height:900});await page.waitForTimeout(100);
  const overflow=await page.evaluate(()=>{
   const selectors=['.studio-main','.welcome-page','.library-page','.settings-layout','.settings-category-content','.chat-page','.chat-center','.chat-composer','.chat-evidence','.source-page','.source-inspector'];
   return {page:document.documentElement.scrollWidth>innerWidth+1||document.documentElement.scrollHeight>innerHeight+1||document.querySelector('.studio').scrollTop!==0||document.querySelector('.studio-main').scrollTop!==0||document.querySelector('.studio-sidebar').scrollTop!==0||[...document.querySelectorAll('.settings-categories,.source-page')].some(el=>el.scrollTop!==0),
    containers:selectors.flatMap(selector=>[...document.querySelectorAll(selector)].filter(el=>el.getBoundingClientRect().width>0&&el.scrollWidth>el.clientWidth+2).map(()=>selector))};
  });
  check(!overflow.page&&!overflow.containers.length,`FIT_${name}_${width}_${overflow.containers.join(',')}`);
  await shot(`${name}-${width}`);
 }
 if(stage==='empty'){
  await page.getByRole('heading',{name:'文献库还是空的',exact:true}).waitFor();
  check(await page.locator('.welcome-page button').count()===1,'EMPTY_ONE_ACTION');
  check((await nav.getByRole('button').allTextContents()).join(',')==='问答,文献,设置','THREE_NAV_ENTRIES');
  for(const width of [1440,1024,720,390])await fit(width,'empty');
  await page.getByRole('button',{name:'导入文件',exact:true}).focus();
  check(await page.getByRole('button',{name:'导入文件',exact:true}).evaluate(el=>el===document.activeElement&&getComputedStyle(el).outlineStyle!=='none'),'KEYBOARD_FOCUS_VISIBLE');
  await page.setViewportSize({width:1440,height:900});
 }
 if(stage==='populated'){
  const evidencePanel=page.locator('.chat-evidence');
  check(await evidencePanel.locator('.turn-source').count()>0,'CITATIONS_VISIBLE');
  check(await evidencePanel.locator('.turn-scope').count()===1&&await evidencePanel.locator('.pipeline-diagnostics').count()===1,'ONE_SCOPE_AND_TRACE_PER_TURN');
  check(await evidencePanel.locator('.turn-scope').evaluate(el=>!el.open),'SCOPE_COLLAPSED');
  check(await evidencePanel.locator('.pipeline-diagnostics').evaluate(el=>!el.open),'DIAGNOSTICS_COLLAPSED');
  check(await evidencePanel.evaluate(el=>el.querySelector('.turn-sources').compareDocumentPosition(el.querySelector('.turn-scope'))&Node.DOCUMENT_POSITION_FOLLOWING),'CITATIONS_BEFORE_SCOPE');
  await evidencePanel.locator('.pipeline-diagnostics>summary').focus();await page.keyboard.press('Enter');
  check(await evidencePanel.locator('.pipeline-diagnostics').evaluate(el=>el.open),'DIAGNOSTICS_KEYBOARD_OPEN');
  await page.keyboard.press('Enter');
  await evidencePanel.evaluate(el=>{el.scrollTop=0;});
  for(const width of [1440,1024,720,390])await fit(width,'chat');
  await nav.getByRole('button',{name:'文献',exact:true}).click();
  await page.getByLabel('筛选文献',{exact:true}).fill('no-match-ui02');
  await page.getByRole('heading',{name:'没有符合筛选条件的文献',exact:true}).waitFor();
  await page.getByRole('button',{name:'清除筛选',exact:true}).click();
  check(await page.locator('.paper-table tbody tr').count()===2,'CLEAR_FILTER_RESTORES_DOCUMENTS');
  await page.locator('.paper-title').first().click();
  check(await page.getByRole('button',{name:'阅读 PDF',exact:true}).isVisible(),'READ_ACTION_REACHABLE');
  check(await page.locator('.paper-detail').evaluate(el=>{const button=[...el.querySelectorAll('button')].find(b=>b.textContent==='阅读 PDF');return button.getBoundingClientRect().bottom<=el.getBoundingClientRect().bottom;}),'READ_ACTION_IN_VIEW');
  await page.locator('.metadata-provenance>summary').click();
  check(await page.locator('.metadata-summary').isVisible(),'METADATA_PROVENANCE_REACHABLE');
  await page.locator('.metadata-provenance>summary').click();
  for(const width of [1440,1024,720,390])await fit(width,'library');
  await page.getByRole('button',{name:'关闭论文详情',exact:true}).click();
  await nav.getByRole('button',{name:'设置',exact:true}).click();
  const names=['模型服务','检索与索引','文献解析','工作区与数据','备份与恢复','高级与诊断'];
  for(const width of [1440,720,390]){
   await page.setViewportSize({width,height:900});
   for(const name of names){await category(name);await fit(width,'settings-'+names.indexOf(name));}
   await category('模型服务');await page.getByRole('tab',{name:'自定义兼容接口',exact:true}).click();
   check(await page.getByLabel('API Key',{exact:true}).isVisible(),'CREDENTIAL_INPUT_'+width);
   check(await page.getByRole('button',{name:'保存并启用',exact:true}).isVisible(),'AUTHORIZATION_ACTION_'+width);
   await fit(width,'settings-api');
  }
  await page.setViewportSize({width:1440,height:900});
  await category('模型服务');await page.getByRole('tab',{name:'本地模型',exact:true}).click();
  await page.getByRole('tab',{name:'本地模型',exact:true}).focus();await page.keyboard.press('ArrowRight');
  check(await page.getByRole('tab',{name:'DeepSeek',exact:true}).evaluate(el=>el===document.activeElement&&el.getAttribute('aria-selected')==='true'),'MODEL_TAB_ARROW_KEYS');
  await page.keyboard.press('Home');
  check(await page.getByRole('tab',{name:'本地模型',exact:true}).getAttribute('aria-selected')==='true','MODEL_TAB_HOME');
  check(await page.getByRole('tabpanel').getAttribute('aria-labelledby')==='model-tab-local','MODEL_PANEL_LABELED');
  await nav.getByRole('button',{name:'问答',exact:true}).click();
 }
 if(stage==='source'){
  await page.getByRole('radio',{name:'已核对',exact:true}).check();
  await page.getByLabel('核查备注',{exact:true}).fill('UI-02 交互验证，非科研金标。');
  await page.getByRole('button',{name:'保存核查',exact:true}).click();
  await page.getByText('核查记录已保存，模型自检状态保持独立。',{exact:true}).waitFor();
  check(true,'REVIEW_SAVED');
  for(const width of [1440,1024,720,390])await fit(width,'source');
  await page.setViewportSize({width:1440,height:900});
 }
 if(stage==='recovery'){
  await page.setViewportSize({width:1440,height:900});await nav.getByRole('button',{name:'设置',exact:true}).click();
  await category('工作区与数据');const oldRoot=await page.locator('#workspace-directory').inputValue();
  const docs=(await rpc('GET','/v0/documents')).documents;
  await category('备份与恢复');await page.getByRole('button',{name:'创建备份',exact:true}).click();
  await page.getByText('已完成备份',{exact:true}).waitFor();
  await page.getByRole('button',{name:'从备份恢复副本',exact:true}).click();
  await page.getByRole('button',{name:'使用此恢复副本',exact:true}).waitFor();
  await wait(async()=>!(await rpc('GET','/v0/jobs')).jobs.some(job=>['queued','running'].includes(job.status)));
  await shot('backup-ready');
  await page.getByRole('button',{name:'使用此恢复副本',exact:true}).click();
  await page.getByRole('region',{name:'模型服务',exact:true}).waitFor();
  await category('工作区与数据');
  await wait(async()=>await page.locator('#workspace-directory').inputValue()!==oldRoot);
  check(JSON.stringify(docs)===JSON.stringify((await rpc('GET','/v0/documents')).documents),'RESTORE_METADATA_UNCHANGED');
  check(!(await rpc('GET','/v0/generation-providers')).providers.some(p=>p.credential_available),'RESTORE_NO_SECRET');
  check(!errors.length,'NO_BROWSER_ERRORS');
 }
 fs.writeFileSync(path.join(evidence,`UI02-${stage}.json`),JSON.stringify({status:'PASS',checks,screenshots,engine:'REAL PROCESS',transport:'SIMULATED TAURI',scientific_quality:'NOT EVALUATED',windows:'NOT EXECUTED'},null,2));
};
