/* Protocol fixture only. It does not certify an external model's answers. */
const http=require('node:http');
const {once}=require('node:events');
module.exports=async function({page,rpc}){
  const calls=[];
  const server=http.createServer((request,response)=>{
    let input='';request.on('data',chunk=>input+=chunk);request.on('end',()=>{
      calls.push(request.url);
      response.setHeader('Content-Type','application/json');
      if(request.method==='GET'){response.end(JSON.stringify({data:[{id:'protocol-fixture'}]}));return;}
      const body=JSON.parse(input),support=body.messages[0].content.includes('entire claim');
      const result=support?{status:'supported',reason:'Protocol fixture only; no scientific assessment'}:{claims:[{text:'Protocol fixture draft',evidence:[{citation_id:'E1'}]}]};
      response.end(JSON.stringify({choices:[{message:{content:JSON.stringify(result)}}]}));
    });
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  try{
    const nav=page.getByRole('navigation',{name:'主导航'});
    await nav.getByRole('button',{name:'设置',exact:true}).click();
    await page.getByLabel('连接名称',{exact:true}).fill('Protocol Fixture');
    await page.getByLabel('接口地址（以 /v1 结尾）',{exact:true}).fill(`http://127.0.0.1:${server.address().port}/v1`);
    await page.getByLabel('API Key',{exact:true}).fill('local-protocol-fixture-key');
    await page.getByRole('button',{name:'获取模型列表',exact:true}).click();
    await page.getByText('模型列表已获取，请选择模型后保存。API 密钥需重新输入。',{exact:true}).waitFor();
    if(await page.getByLabel('API Key',{exact:true}).inputValue()!=='')throw new Error('PROBE_KEY_NOT_CLEARED');
    await page.getByLabel('模型 ID',{exact:true}).fill('protocol-fixture');
    await page.getByLabel('API Key',{exact:true}).fill('local-protocol-fixture-key');
    await page.getByRole('button',{name:'保存连接',exact:true}).click();
    await page.getByRole('button',{name:'Protocol Fixture · protocol-fixture',exact:true}).waitFor();
    if(await page.getByLabel('API Key',{exact:true}).inputValue()!=='')throw new Error('SAVE_KEY_NOT_CLEARED');
    const connection=(await rpc('GET','/v0/generation-providers')).providers[0];
    const before=(await rpc('GET','/v0/index')).generation;
    await nav.getByRole('button',{name:'问答',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('select[aria-label="生成模型"] option')].some(item=>item.textContent.includes('Protocol Fixture')));
    await page.getByLabel('生成模型',{exact:true}).selectOption(connection.id);
    await page.getByLabel('你的问题',{exact:true}).fill('BERT protocol fixture');
    if(!await page.getByRole('button',{name:'发送问题',exact:true}).isDisabled())throw new Error('CONSENT_NOT_REQUIRED');
    const consent=page.getByRole('checkbox',{name:/允许本次请求/});
    await consent.check();
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.getByRole('heading',{name:'BERT protocol fixture',exact:true}).waitFor();
    await page.getByText('Protocol fixture draft',{exact:true}).waitFor();
    if(await consent.isChecked())throw new Error('CONSENT_NOT_RESET');
    if((await rpc('GET','/v0/index')).generation!==before)throw new Error('MODEL_CHANGE_REBUILT_INDEX');
    if(calls.filter(url=>url==='/v1/chat/completions').length!==2)throw new Error('API_PROTOCOL_NOT_EXECUTED');
    return {status:'PASS',scope:'protocol fixture only',catalog:true,key_cleared:true,consent_required:true,consent_reset:true,index_unchanged:true};
  }finally{await new Promise(resolve=>server.close(resolve));}
};
