/* Real frozen local candidate inference and PDF workflow; broker is simulated. */
const fs = require('node:fs');
const path = require('node:path');
module.exports = async function ({page,rpc,evidence}) {
  const outcome = {transport:'SIMULATED TAURI',real_engine:true,windows:false,scientific_quality:'NOT EVALUATED'};
  await page.getByRole('button',{name:'阅读',exact:true}).click();
  await page.getByRole('button',{name:'阅读批注',exact:true}).click();
  await page.getByLabel('阅读笔记',{exact:true}).fill('真实 PDF 的本地批注测试，不作为科学证据。');
  await page.getByRole('button',{name:'新增批注',exact:true}).click();
  await page.locator('.reading-notes article').getByText('真实 PDF 的本地批注测试，不作为科学证据。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  outcome.reading_note = true;

  await page.getByRole('button',{name:'设置与备份',exact:true}).click();
  await page.getByRole('button',{name:'选择或重新校验 OCR 语言目录',exact:true}).click();
  await page.getByText('eng + chi_sim 已校验；低文本页可显式重解析。OCR 文本仍需核对原件。',{exact:true}).waitFor({timeout:30000});
  outcome.ocr_configured=(await rpc('GET','/v0/ocr')).configured;
  await page.getByLabel('试验后端',{exact:true}).selectOption('sqlite-vec');
  await page.getByRole('button',{name:'选择本地模型并构建索引',exact:true}).click();
  await page.getByText('索引已就绪',{exact:true}).waitFor({timeout:90000});
  await page.getByRole('button',{name:'选择或重新校验生成模型',exact:true}).click();
  await page.getByText('Qwen2.5-1.5B-Instruct GGUF 已配置；尚未通过科研质量验收。',{exact:true}).waitFor({timeout:90000});
  await page.screenshot({path:path.join(evidence,'full-model-settings.png'),fullPage:true});
  outcome.embedding_configured=(await rpc('GET','/v0/index')).ready;
  outcome.generator_configured=(await rpc('GET','/v0/generator')).configured;

  await page.getByRole('button',{name:'来源检索',exact:true}).click();
  await page.getByLabel('检索方式',{exact:true}).selectOption('hybrid');
  await page.getByLabel('关键词或完整短语',{exact:true}).fill('BERT pretraining tasks');
  await page.getByRole('button',{name:'检索',exact:true}).click();
  await page.locator('.search-hits li').first().waitFor({timeout:90000});
  outcome.hybrid_hits=await page.locator('.search-hits li').count();
  await page.getByLabel('检索起始年份',{exact:true}).fill('2020');
  if(!await page.getByRole('button',{name:'检索',exact:true}).isDisabled())throw new Error('YEAR_FILTER_NOT_PREFILTERED');
  await page.getByLabel('检索起始年份',{exact:true}).fill('2019');
  await page.getByLabel('检索结束年份',{exact:true}).fill('2019');
  await page.getByLabel('检索标签筛选',{exact:true}).selectOption('预训练');
  await page.getByRole('button',{name:'检索',exact:true}).click();
  await page.locator('.search-hits li').first().waitFor();
  outcome.metadata_prefilter=true;

  await page.getByRole('button',{name:'证据问答',exact:true}).click();
  await page.getByLabel('本轮问题',{exact:true}).fill('BERT pretraining');
  await page.getByRole('button',{name:'提交问题',exact:true}).click();
  await page.locator('.answer-run .evidence-card').first().waitFor({timeout:30000});
  const card=page.locator('.answer-run .evidence-card').first();
  await card.getByLabel('复核备注',{exact:true}).fill('工程链路复核，不是科研金标准');
  await card.getByRole('button',{name:'确认依据',exact:true}).click();
  await card.getByText('人工确认',{exact:true}).waitFor();
  await page.setViewportSize({width:1900,height:1100});
  await card.getByRole('button',{name:'查看原文',exact:true}).click();
  await page.getByRole('region',{name:/原文来源/}).waitFor();
  await page.getByText('正在渲染页面…',{exact:true}).waitFor({state:'hidden'});
  const boxes=await page.evaluate(()=>['.workbench-panel','.workbench-results','.evidence-panel'].map(selector=>{const box=document.querySelector(selector).getBoundingClientRect();return {left:box.left,right:box.right,width:box.width};}));
  if(boxes[0].right>boxes[1].left||boxes[1].right>boxes[2].left||boxes[2].right>1900)throw new Error('THREE_PANE_LAYOUT_OVERLAP');
  await page.screenshot({path:path.join(evidence,'wide-evidence-three-pane.png'),fullPage:true});
  await page.setViewportSize({width:1000,height:900});
  await page.getByRole('dialog',{name:/原文来源/}).waitFor();
  await page.screenshot({path:path.join(evidence,'narrow-evidence-drawer.png'),fullPage:true});
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  await page.setViewportSize({width:1400,height:1000});
  outcome.responsive_three_pane=true;
  await page.getByLabel('检索策略',{exact:true}).selectOption('keyword_review');
  await page.getByLabel('处理模式',{exact:true}).selectOption('generative');
  await page.getByLabel('本轮问题',{exact:true}).fill('What are the two pre-training tasks used by BERT?');
  await page.getByRole('button',{name:'提交问题',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('select[aria-label="问题记录"] option').length>=2,null,{timeout:30000});
  for(let index=0;;index++){
    const run=(await rpc('GET','/v0/answers')).answers.find(run=>run.mode==='generative');
    if(run&&['completed','refused','failed'].includes(run.status)){outcome.generated_status=run.status;outcome.generated_error=run.error_code;outcome.claims=run.claims.length;outcome.relevance_review=Boolean(run.result?.relevance_review);if(!outcome.relevance_review)throw new Error('RELEVANCE_REVIEW_MISSING');if(run.status==='failed')throw new Error('GENERATION_FAILED:'+run.error_code);break;}
    if(index>180)throw new Error('GENERATION_TIMEOUT');
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  await page.getByRole('button',{name:'刷新',exact:true}).click();
  await page.screenshot({path:path.join(evidence,'full-answer-draft.png'),fullPage:true});

  await page.getByRole('button',{name:'Research 工作台',exact:true}).click();
  await page.getByLabel('研究问题',{exact:true}).fill('BERT 逐篇证据整理');
  await page.getByLabel('提取字段（逗号分隔，最多 20 项）',{exact:true}).fill('BERT, nonexistent-field');
  await page.getByRole('button',{name:'冻结范围并建计划',exact:true}).click();
  await page.getByRole('button',{name:'运行逐篇研究',exact:true}).click();
  await page.getByRole('button',{name:'核对数值与条件',exact:true}).first().waitFor({timeout:30000});
  await page.getByRole('button',{name:'核对数值与条件',exact:true}).first().click();
  await page.getByLabel('值 / 摘录',{exact:true}).fill('人工修订测试值（无科研结论含义）');
  await page.getByLabel('实验行 ID',{exact:true}).fill('test-experiment-1');
  await page.getByLabel('数据集',{exact:true}).fill('需人工核对');
  await page.getByRole('button',{name:'保存研究修订',exact:true}).click();
  await page.getByRole('dialog',{name:'编辑研究记录',exact:true}).waitFor({state:'hidden'});
  await page.getByText('人工修订测试值（无科研结论含义）',{exact:true}).waitFor();
  await page.getByRole('button',{name:'生成报告修订',exact:true}).click();
  await page.locator('.report-preview pre').waitFor();
  await page.getByRole('button',{name:'生成报告修订',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('select[aria-label="报告修订"] option').length===2);
  await page.getByRole('button',{name:'导出 Markdown 报告',exact:true}).click();
  for(let index=0;!globalThis.__exportTestPath;index++){if(index>50)throw new Error('EXPORT_TIMEOUT');await new Promise(resolve=>setTimeout(resolve,100));}
  const body=fs.readFileSync(globalThis.__exportTestPath,'utf8');
  if(!body.includes('未提取（非未报告）')||!body.includes('人工修订测试值'))throw new Error('REPORT_CONTENT_INVALID');
  const plans=(await rpc('GET','/v0/research')).plans;
  outcome.research_coverage=plans[0].coverage;
  outcome.research_chunks=plans[0].items.map(item=>({processed:item.processed_chunks,total:item.total_chunks}));
  outcome.report_revisions=plans[0].reports.length;
  outcome.exported_file=globalThis.__exportTestPath;
  await page.screenshot({path:path.join(evidence,'full-research-matrix-report.png'),fullPage:true});
  fs.writeFileSync(path.join(evidence,'browser-workbench.json'),JSON.stringify({status:'PASS',...outcome},null,2));
};
