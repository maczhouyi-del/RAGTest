/* Real browser events and real engine; native IME composition is a separate gate. */
const fs=require('node:fs'),path=require('node:path');
module.exports=async function({page,rpc,evidence,errors,stage}){
 page.setDefaultTimeout(45000);
 const checks=[];const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);};
 const wait=async test=>{for(let i=0;i<600;i++){if(await test())return;await page.waitForTimeout(150);}throw Error('ENGINE_WAIT_TIMEOUT');};
 await page.getByRole('button',{name:'导入文件',exact:true}).click();
 await wait(async()=>{const docs=(await rpc('GET','/v0/documents')).documents;return docs.length===2&&docs.every(d=>['ready','partial'].includes(d.parse_status));});
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'问答',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('select[aria-label="问答文献范围"]')?.options.length===3);
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
 check(errors.length===0,'NO_BROWSER_ERRORS');
 fs.writeFileSync(path.join(evidence,'stage-'+stage+'-browser.json'),JSON.stringify({status:'PASS',checks,native_IME:'NOT_EXECUTED',transport:'simulated Tauri; real engine'},null,2));
};
