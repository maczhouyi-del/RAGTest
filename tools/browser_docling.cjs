/* Real frozen candidate + PDF; native transport/dialogs are simulated. */
const fs=require('node:fs');
const path=require('node:path');
module.exports=async function({page,rpc,evidence}){
  await page.getByRole('button',{name:'设置与备份',exact:true}).click();
  await page.getByRole('button',{name:'选择或重新校验布局与表格目录',exact:true}).click();
  await page.getByText('Heron / TableFormer fast 已校验，可在文献详情显式增强解析。表格结构仍需对照原件核对。',{exact:true}).waitFor({timeout:120000});
  await page.getByRole('button',{name:'文献库',exact:false}).click();
  await page.getByRole('button',{name:'详情',exact:true}).click();
  await page.getByRole('button',{name:'使用本地布局与表格增强解析',exact:true}).click();
  const version=(await rpc('GET','/v0/documents')).documents[0].doc_version_id;
  let tables;
  for(let i=0;i<600;i++){
    tables=await rpc('GET',`/v0/documents/${version}/tables`);
    if(tables.total>0)break;
    const jobs=(await rpc('GET','/v0/jobs')).jobs;
    const latest=jobs.find(job=>job.type==='parse_page');
    if(latest?.status==='failed')throw new Error('DOCLING_PARSE_FAILED:'+latest.error_code);
    if(i===599)throw new Error('DOCLING_PARSE_TIMEOUT');
    await new Promise(resolve=>setTimeout(resolve,300));
  }
  // Parsing is asynchronous: reopening reads the newly published ParseRun.
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  await page.getByRole('button',{name:'详情',exact:true}).click();
  await page.getByLabel('选择表格候选',{exact:true}).waitFor();
  const coverage=await rpc('GET',`/v0/documents/${version}/parse-diagnostics`);
  const warnings=coverage.pages.filter(p=>p.error_code||coverage.needs_ocr_pages.includes(p.page_number)).length;
  if(warnings===0)throw new Error('EXPECTED_REAL_PARTIAL_LAYOUT_WARNING');
  await page.getByText(`${coverage.pages.length} 页有处理记录；${warnings} 页存在解析错误或质量警告。`,{exact:true}).waitFor();
  const table=tables.tables.find(table=>table.source_pages.includes(7));
  if(!table)throw new Error('EXPECTED_REAL_TABLE_PAGE_MISSING');
  await page.getByLabel('选择表格候选',{exact:true}).selectOption(table.id);
  await page.locator('.table-scroll tbody tr').first().waitFor();
  await page.getByLabel('表格结构复核备注',{exact:true}).fill('真实候选工程核对：逐格列归属与科学数值尚需对照原件。');
  await page.getByRole('button',{name:'人工记录不确定',exact:true}).click();
  await page.getByText(/修订 1/, {exact:false}).first().waitFor();
  await page.screenshot({path:path.join(evidence,'docling-table-review.png'),fullPage:true});
  await page.getByRole('button',{name:'对照 PDF 第 7 页',exact:true}).click();
  await page.getByRole('heading',{name:'PDF 阅读 · 第 7 页',exact:true}).waitFor();
  await page.getByText('正在渲染页面…',{exact:true}).waitFor({state:'hidden'});
  await page.screenshot({path:path.join(evidence,'docling-table-original-page7.png'),fullPage:true});
  await page.locator('.pdf-overlay').getByRole('button',{name:'关闭',exact:true}).click();
  const stages=[];
  const beforeReview=await rpc('GET',`/v0/tables/${table.id}`);
  await page.getByRole('checkbox',{name:'只更新指定页（未改动页的引用与表格复核保留）',exact:true}).check();
  for(const [number,button] of [[6,'使用本地布局与表格增强解析'],[8,'按质量信号自动候选解析']]){
    const before=await rpc('GET',`/v0/documents/${version}/parse-diagnostics`);
    await page.getByLabel('指定重解析页码',{exact:true}).fill(String(number));
    await page.getByRole('button',{name:button,exact:true}).click();
    let diagnostics;
    for(let i=0;i<1000;i++){
      diagnostics=await rpc('GET',`/v0/documents/${version}/parse-diagnostics`);
      if(diagnostics.publication_revision>before.publication_revision)break;
      if(diagnostics.runs[0]?.status==='failed')throw new Error('SELECTIVE_PARSE_FAILED:'+diagnostics.runs[0].error_code);
      if(i===999)throw new Error('SELECTIVE_PARSE_TIMEOUT');
      await new Promise(resolve=>setTimeout(resolve,300));
    }
    const afterReview=await rpc('GET',`/v0/tables/${table.id}`);
    if(JSON.stringify(beforeReview)!==JSON.stringify(afterReview))throw new Error('UNTOUCHED_TABLE_REVIEW_CHANGED');
    if(diagnostics.pages.length!==16||diagnostics.runs[0].page_count!==1)throw new Error('SELECTIVE_COVERAGE_INVALID');
    if(number===8&&(diagnostics.runs[0].routing.length!==1||diagnostics.runs[0].attempts.length!==2))throw new Error('AUTO_ROUTING_NOT_RECORDED');
    stages.push({page:number,diagnostics});
  }
  await page.screenshot({path:path.join(evidence,'quality-routing-pages.png'),fullPage:true});
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  globalThis.__doclingReviewedTableId=table.id;
  const review=await rpc('GET',`/v0/tables/${table.id}`);
  if(review.review.status!=='uncertain'||review.review.revision!==1)throw new Error('TABLE_REVIEW_NOT_PERSISTED');
  fs.writeFileSync(path.join(evidence,'browser-docling.json'),JSON.stringify({status:'PASS',transport:'SIMULATED TAURI BRIDGE',actual_frozen_engine:true,version_id:version,table_count:tables.total,review,stages,scientific_quality:'BLOCKED: no human scientific gold set',windows_tested:false},null,2));
};
