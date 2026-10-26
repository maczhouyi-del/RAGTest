/* Browser UI with a simulated Tauri transport and a REAL frozen engine.
 * This does not test native dialogs, Tauri permissions, or Windows installation.
 */
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const readline = require('node:readline');
const { once } = require('node:events');

async function main() {
  const { chromium } = require(path.join(process.env.RAGSYSTEM_PLAYWRIGHT_DIR, 'playwright'));
  const root = path.resolve(__dirname, '..');
  const evidence = path.join(root, process.env.RAGSYSTEM_EVIDENCE_DIR || 'docs/engineering/evidence/P0-implementation-2026-10-24');
  const p1 = process.env.RAGSYSTEM_P1_SMOKE === '1';
  const round3 = process.env.RAGSYSTEM_MVP03_STAGE;
  const round2 = process.env.RAGSYSTEM_MVP_ROUND2_STAGE;
  const reference = process.env.RAGSYSTEM_UI_REFERENCE_SMOKE === '1';
  const mvp = process.env.RAGSYSTEM_MVP_SMOKE === '1' || reference || !!round2 || !!round3;
  fs.mkdirSync(evidence, {recursive: true});
  let dataRoot = path.join(root, '.tools/test-data', 'browser-' + crypto.randomUUID());
  let token = crypto.randomBytes(32).toString('hex');
  const binary = path.join(root, 'apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin');
  const engineCommand=process.env.RAGSYSTEM_BROWSER_SOURCE_ENGINE==='1'?path.join(root,'engine/.venv/bin/python'):binary;
  const engineArgs=process.env.RAGSYSTEM_BROWSER_SOURCE_ENGINE==='1'?['-m','ragsystem']:[];
  const startEngine=()=>spawn(engineCommand,engineArgs,{stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONPATH:path.join(root,'engine')}});
  let child = startEngine();
  let browser, server, page;
  const errors = [];
  try {
    const lines = readline.createInterface({input: child.stdout});
    const handshake = once(lines, 'line');
    child.stdin.write(JSON.stringify({protocol_version: '0.1.0', token, data_root: dataRoot}) + '\n');
    const [line] = await Promise.race([handshake, new Promise((_, reject) => setTimeout(() => reject(new Error('HANDSHAKE_TIMEOUT')), 25000))]);
    let { port } = JSON.parse(line);
    const rpc = (method, endpoint, body, connection) => new Promise((resolve,reject)=>{
      const target=connection??{port,token};
      const encoded=body===undefined?undefined:JSON.stringify(body);
      const request=http.request({hostname:'127.0.0.1',port:target.port,path:endpoint,method,agent:false,headers:{'X-RAG-Session':target.token,'Content-Type':'application/json','Connection':'close',...(encoded?{'Content-Length':Buffer.byteLength(encoded)}:{})}},response=>{
        const chunks=[];let bytes=0;
        response.on('data',chunk=>{bytes+=chunk.length;if(bytes>16*1024*1024){response.destroy(new Error('TEST_REPLY_LIMIT'));return;}chunks.push(chunk);});
        response.on('error',reject);
        response.on('end',()=>{try{const raw=Buffer.concat(chunks).toString();const result=raw.startsWith('{')?JSON.parse(raw):{code:'HTTP_'+response.statusCode};if(response.statusCode>=400)reject(new Error(result.code??'HTTP_'+response.statusCode));else resolve(result);}catch(error){reject(error);}});
      });
      request.setTimeout(30000,()=>request.destroy(new Error('TEST_REQUEST_TIMEOUT:'+endpoint)));
      request.on('error',error=>{fs.appendFileSync(path.join(evidence,'browser-transport-errors.jsonl'),JSON.stringify({method,endpoint,code:error.code,message:error.message,time:new Date().toISOString()})+'\n');reject(error);});
      if(encoded)request.write(encoded);request.end();
    });
    for (let attempt = 0; ; attempt++) {
      try {await rpc('GET', '/v0/health'); break;}
      catch (error) {if (attempt > 60) throw error; await new Promise(resolve => setTimeout(resolve, 100));}
    }
    const dist = path.join(root, 'apps/desktop/dist');
    server = http.createServer((request, response) => {
      const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
      const file = path.resolve(dist, '.' + (pathname === '/' ? '/index.html' : pathname));
      if (!file.startsWith(dist + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {response.writeHead(404); response.end(); return;}
      const mime = {'.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css'}[path.extname(file)] || 'application/octet-stream';
      response.writeHead(200, {'Content-Type': mime, 'Content-Security-Policy': "default-src 'self'; script-src 'self'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'"});
      fs.createReadStream(file).pipe(response);
    });
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    const base = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({headless: true, args: ['--disable-background-networking']});
    const context = await browser.newContext({viewport: {width: 1400, height: 1000}});
    await context.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort());
    page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const broker = async (command, args = {}) => {
      fs.appendFileSync(path.join(evidence,'browser-commands-'+path.basename(dataRoot)+'.jsonl'),JSON.stringify({command,time:new Date().toISOString()})+'\n');
      if (command === 'restart_engine') {
        child.stdin.end();await once(child,'exit');
        token=crypto.randomBytes(32).toString('hex');child=startEngine();
        const readiness=once(readline.createInterface({input:child.stdout}),'line');
        child.stdin.write(JSON.stringify({protocol_version:'0.1.0',token,data_root:dataRoot})+'\n');
        const [startup]=await Promise.race([readiness,new Promise((_,reject)=>setTimeout(()=>reject(Error('RESTART_HANDSHAKE_TIMEOUT')),25000))]);port=JSON.parse(startup).port;
        for(let i=0;;i++){try{await rpc('GET','/v0/health');break;}catch(error){if(i>100)throw error;await new Promise(resolve=>setTimeout(resolve,50));}}
        return;
      }
      if (command === 'workspace_snapshot') {
        const health=await rpc('GET','/v0/health'),docs=await rpc('GET','/v0/documents'),jobs=await rpc('GET','/v0/jobs'),projects=await rpc('GET','/v0/projects'),index=await rpc('GET','/v0/index'),generator=await rpc('GET','/v0/generator'),ocr=await rpc('GET','/v0/ocr'),docling=await rpc('GET','/v0/docling');
        return {health, documents: docs.documents, jobs: jobs.jobs, projects: projects.projects, index, generator, ocr, docling, workspace: {label: path.basename(dataRoot), warning: '', directory:dataRoot}};
      }
      if (command === 'prepare_mvp') return rpc('POST','/v0/mvp/prepare',{version_ids:args.versionIds,idempotency_key:crypto.randomUUID()});
      if (command === 'read_mvp_answer') return rpc('GET',`/v0/answers/${args.answerId}`);
      if (command === 'list_generation_providers') return rpc('GET','/v0/generation-providers');
      if (command === 'save_generation_provider') return rpc('POST','/v0/generation-providers',args.body);
      if (command === 'preview_generation_provider') return rpc('POST','/v0/generation-provider-probe',args.body);
      if (command === 'authorize_generation_provider') return rpc('POST',`/v0/generation-providers/${args.identifier}/authorization`,{expected_revision:args.expectedRevision,enabled:args.enabled});
      if (command === 'probe_generation_provider') return rpc('POST',`/v0/generation-providers/${args.identifier}/probe`);
      if (command === 'workbench_snapshot') {
        const scope = args.projectId ? 'project_id=' + args.projectId + '&' : '';
        const answers=await rpc('GET','/v0/history/answers?'+scope),research=await rpc('GET','/v0/history/research?'+scope),generator=await rpc('GET','/v0/generator');
        const answerId=args.answerId||answers.items[0]?.id,planId=args.planId||research.items[0]?.id;
        return {answer_index:answers,research_index:research,answers:answerId?[await rpc('GET',`/v0/answers/${answerId}?${scope}`)]:[],plans:planId?[await rpc('GET',`/v0/research/${planId}?${scope}paper_offset=${args.paperOffset??0}&observation_offset=${args.observationOffset??0}`)]:[],generator};
      }
      if (command === 'history_page') return rpc('GET',`/v0/history/${args.kind}?cursor=${args.cursor}`+(args.projectId?'&project_id='+args.projectId:''));
      if (command === 'read_research_report') return rpc('GET',`/v0/reports/${args.reportId}`);
      if (command === 'lifecycle_snapshot') return rpc('GET','/v0/lifecycle');
      if (command === 'update_document_lifecycle') return rpc('POST',`/v0/documents/${args.documentId}/lifecycle`,args.body);
      if (command === 'list_document_tables') return rpc('GET',`/v0/documents/${args.versionId}/tables?offset=${args.offset??0}`);
      if (command === 'read_table_candidate') return rpc('GET',`/v0/tables/${args.tableId}?row_offset=${args.rowOffset??0}`);
      if (command === 'review_table_candidate') return rpc('POST',`/v0/tables/${args.tableId}/review`,args.body);
      if (command === 'inspect_document_parse') return rpc('GET', `/v0/documents/${args.versionId}/parse-diagnostics`);
      if (command === 'identity_snapshot') return rpc('GET', '/v0/document-merges');
      if (command === 'merge_document_versions') return rpc('POST', '/v0/document-merges', args.body);
      if (command === 'undo_document_merge') return rpc('POST', `/v0/document-merges/${args.mergeId}/undo`);
      if (command === 'list_annotations') return rpc('GET', `/v0/documents/${args.versionId}/annotations`);
      if (command === 'save_annotation') return rpc('POST', `/v0/documents/${args.versionId}/annotations`, args.body);
      if (command === 'create_conversation') return rpc('POST','/v0/conversations');
      if (command === 'conversation_turns') return rpc('GET',`/v0/conversations/${args.conversationId}/turns?cursor=${args.cursor}`);
      if (command === 'ask_question') return rpc('POST', '/v0/answers', args.body);
      if (command === 'create_research_plan') return rpc('POST', '/v0/research', args.body);
      if (command === 'run_research_plan') return rpc('POST', `/v0/research/${args.planId}/run`);
      if (command === 'review_evidence') return rpc('POST', `/v0/reviews/${args.targetId}`, args.body);
      if (command === 'edit_observation') return rpc('POST', `/v0/research/${args.planId}/observations/${args.evidenceId}`, args.body);
      if (command === 'create_research_report') return rpc('POST', `/v0/research/${args.planId}/reports`);
      if (command === 'export_research_report') {
        const report = await rpc('GET', `/v0/reports/${args.reportId}`);
        const file = path.join(root,'.tools/test-data','export-'+crypto.randomUUID()+'.md');
        fs.writeFileSync(file, report.export_body??report.body, {flag:'wx'});
        globalThis.__exportTestPath = file;
        return {saved:true,label:path.basename(file)};
      }
      if (command === 'choose_embedding_model' || command === 'choose_generator_model' || command === 'choose_ocr_model' || command === 'choose_docling_model') {
        const embedding = command === 'choose_embedding_model';
        const ocr = command === 'choose_ocr_model';
        const docling = command === 'choose_docling_model';
        const directory = path.join(root,'.tools/models',docling ? 'docling-heron-tableformer-fast-candidates' : ocr ? 'tessdata-fast-65727574dfcd264acbb0c3e07860e4e9e9b22185' : embedding ? 'intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3' : 'qwen2.5-1.5b-instruct-gguf-91cad51170dc346986eccefdc2dd33a9da36ead9');
        const grant = await rpc('POST','/v0/internal/directory-grants',{path:directory,purpose:docling?'docling':ocr?'ocr':embedding?'embedding':'generator'});
        return rpc('POST',docling?'/v0/docling':ocr?'/v0/ocr':embedding?'/v0/index':'/v0/generator',{model_grant_id:grant.directory_grant_id,idempotency_key:crypto.randomUUID(),...(embedding?{backend:args.backend}:{})});
      }
      if (command === 'list_backups') return rpc('GET', '/v0/backups');
      if (command === 'retry_job') return rpc('POST', `/v0/jobs/${args.jobId}/retry`);
      if (command === 'choose_backup_directory' || command === 'choose_restore_directories') {
        const parent = path.join(root, '.tools/test-data/browser-backups-' + crypto.randomUUID());
        fs.mkdirSync(parent);
        const isRestore = command === 'choose_restore_directories';
        const grant = await rpc('POST', '/v0/internal/directory-grants', {path: parent, purpose: isRestore ? 'restore_parent' : 'backup_parent'});
        let source;
        if (isRestore) {
          const record = (await rpc('GET', '/v0/backups')).records.find(row => row.kind === 'backup');
          if (!globalThis.__backupTestPaths?.has(record?.id)) throw new Error('NO_TEST_BACKUP_PATH');
          source = await rpc('POST', '/v0/internal/directory-grants', {path: globalThis.__backupTestPaths.get(record.id), purpose: 'snapshot'});
        }
        const result = await rpc('POST', '/v0/backups', {parent_grant_id: grant.directory_grant_id, source_grant_id: source?.directory_grant_id ?? null, idempotency_key: crypto.randomUUID()});
        if (!isRestore) {
          for (let index=0; index<100; index++) {
            const records = (await rpc('GET', '/v0/backups')).records;
            const record = records.find(row => row.kind === 'backup' && fs.existsSync(path.join(parent, row.label)));
            if (record) {globalThis.__backupTestPaths ??= new Map(); globalThis.__backupTestPaths.set(record.id, path.join(parent, record.label)); break;}
            await new Promise(resolve => setTimeout(resolve, 50));
          }
        }
        return result;
      }
      if (command === 'activate_restored_workspace') {
        const restored = await rpc('GET', `/v0/internal/restored-workspaces/${args.identifier}`);
        // Match native activation: authenticate the new process before retiring
        // the prior process. Keep test RPC assertions behind the visible UI swap.
        const nextToken=crypto.randomBytes(32).toString('hex');
        const next=startEngine();
        try {
          const readiness=once(readline.createInterface({input:next.stdout}),'line');
          next.stdin.write(JSON.stringify({protocol_version:'0.1.0',token:nextToken,data_root:restored.data_root})+'\n');
          const [startup]=await Promise.race([readiness,new Promise((_,reject)=>setTimeout(()=>reject(new Error('ACTIVATION_HANDSHAKE_TIMEOUT')),25000))]);
          const nextPort=JSON.parse(startup).port;
          for(let index=0;;index++){try{await rpc('GET','/v0/health',undefined,{port:nextPort,token:nextToken});break;}catch(error){if(index>100)throw error;await new Promise(resolve=>setTimeout(resolve,50));}}
          child.stdin.end(); await once(child,'exit');
          child=next; token=nextToken;port=nextPort;dataRoot=restored.data_root;
        } catch(error) {next.stdin.end();next.kill();throw error;}
        return;
      }
      if (command === 'choose_pdf_and_import' && mvp) {
        const grants=[];for(const name of ['N19-1423.pdf','2020.emnlp-main.550.pdf','N19-1423.pdf']){const grant=await rpc('POST','/v0/internal/file-grants',{path:path.join(root,'tests/fixtures/public',name)});grants.push(grant.file_grant_id);}return rpc('POST','/v0/import-batches',{file_grant_ids:grants,idempotency_key:crypto.randomUUID()});
      }
      if (command === 'choose_pdf_and_import') {
        const grant = await rpc('POST', '/v0/internal/file-grants', {path: path.join(root, 'tests/fixtures/public/N19-1423.pdf')});
        return rpc('POST', '/v0/imports', {file_grant_id: grant.file_grant_id, idempotency_key: crypto.randomUUID(), project_id: args.projectId ?? null});
      }
      if (command === 'create_project') return rpc('POST', '/v0/projects', {name: args.name});
      if (command === 'set_project_document') return rpc('POST', `/v0/projects/${args.projectId}/documents/${args.documentId}`, {linked: args.linked});
      if (command === 'update_document_metadata') return rpc('POST', `/v0/documents/${args.documentId}/metadata`, args.metadata);
      if (command === 'read_document') {
        const document = await rpc('GET', `/v0/documents/${args.versionId}/file`);
        if (!/^[a-f0-9]{64}$/.test(document.file_sha256)) throw new Error('SOURCE_HASH_INVALID');
        const bytes = fs.readFileSync(path.join(dataRoot, 'papers', document.file_sha256 + '.pdf'));
        if (crypto.createHash('sha256').update(bytes).digest('hex') !== document.file_sha256) throw new Error('SOURCE_HASH_INVALID');
        return {document, pdf_bytes: Array.from(bytes)};
      }
      if (command === 'parse_document') return rpc('POST', `/v0/documents/${args.versionId}/parse`, {idempotency_key: crypto.randomUUID(),use_ocr:args.useOcr??false,use_docling:args.useDocling??false,auto_enhance:args.autoEnhance??false,page_numbers:args.pageNumbers??null});
      if (command === 'search_sources') return rpc('POST', '/v0/search', {query: args.query, strategy: args.strategy ?? 'fts_only', authorized_doc_version_ids: args.versionIds, k: 20, project_id: args.projectId ?? null,filters:args.filters??null});
      if (command === 'read_source') {
        const anchor = await rpc('GET', `/v0/source-anchors/${args.sourceId}`);
        if (!/^[a-f0-9]{64}$/.test(anchor.file_sha256)) throw new Error('SOURCE_HASH_INVALID');
        const bytes = fs.readFileSync(path.join(dataRoot, 'papers', anchor.file_sha256 + '.pdf'));
        if (crypto.createHash('sha256').update(bytes).digest('hex') !== anchor.file_sha256) throw new Error('SOURCE_HASH_INVALID');
        return {anchor, pdf_bytes: Array.from(bytes)};
      }
      throw new Error('TEST_BROKER_COMMAND_NOT_IMPLEMENTED');
    };
    let brokerChain=Promise.resolve();
    await page.exposeFunction('__testBroker',(command,args)=>{const result=brokerChain.then(()=>broker(command,args));brokerChain=result.catch(()=>undefined);return result;});
    await page.addInitScript(() => {globalThis.isTauri = true; globalThis.__TAURI_INTERNALS__ = {invoke: (command, args) => globalThis.__testBroker(command, args)};});
    await page.goto(base);
    const audit=()=>{const script=`import sqlite3,json,hashlib,sys
c=sqlite3.connect(sys.argv[1]); c.execute('BEGIN'); h=hashlib.sha256()
for row in c.execute('SELECT id,vector_bytes FROM embedding_records ORDER BY id'): h.update(row[0].encode()); h.update(row[1])
a=c.execute("SELECT value_json FROM app_settings WHERE key='active_index'").fetchone()
print(json.dumps({'vector_sha256':h.hexdigest(),'vectors':c.execute('SELECT count(*) FROM embedding_records').fetchone()[0],'index_builds':c.execute("SELECT count(*) FROM jobs WHERE type='embed_batch'").fetchone()[0],'active_index':json.loads(a[0]) if a else None,'secret_in_db':any(any(secret in line for secret in ['local-protocol-fixture-key','fixture-authorization-secret']) for line in c.iterdump())}))`;const output=require('node:child_process').spawnSync(path.join(root,'engine/.venv/bin/python'),['-c',script,path.join(dataRoot,'data/research.db')],{encoding:'utf8'});if(output.status!==0)throw Error('SQLITE_AUDIT_FAILED');return JSON.parse(output.stdout);};
    if(mvp){
      await page.locator('.connection').filter({hasText:'本地引擎已连接'}).waitFor();
      if(round3)await require('./browser_mvp03.cjs')({page,rpc,root,evidence,errors,stage:round3,audit});
      else if(round2)await require('./browser_round2.cjs')({page,rpc,root,evidence,errors,stage:round2,audit});
      else if(reference)await require('./browser_reference.cjs')({page,rpc,root,evidence,errors});
      else await require('./browser_mvp.cjs')({page,rpc,root,evidence,errors});
    }else{
    await page.locator('.sidebar-note').filter({hasText: '本地引擎已连接'}).waitFor();
    async function createProject(name) {
      await page.getByRole('button', {name: '新建项目', exact: true}).click();
      await page.getByLabel('项目名称', {exact: true}).fill(name);
      await page.getByRole('button', {name: '创建项目', exact: true}).click();
      await page.getByRole('heading', {name: '这个项目还没有文献'}).waitFor();
    }
    if (p1) await createProject('项目甲');
    await page.getByRole('button', {name: /导入 PDF/}).click();
    await page.getByText('N19-1423.pdf', {exact: true}).waitFor();
    if (p1) {
      await page.getByRole('button', {name: '阅读', exact: true}).click();
      await page.getByRole('heading', {name: 'PDF 阅读 · 第 1 页'}).waitFor();
      await page.getByText('正在渲染页面…', {exact: true}).waitFor({state: 'hidden'});
      await page.getByRole('button', {name: '下一页'}).click();
      await page.getByRole('heading', {name: 'PDF 阅读 · 第 2 页'}).waitFor();
      await page.getByLabel('跳转页码', {exact: true}).fill('16');
      await page.getByRole('button', {name: '跳转', exact: true}).click();
      await page.getByRole('heading', {name: 'PDF 阅读 · 第 16 页'}).waitFor();
      if (!await page.getByRole('button', {name: '下一页'}).isDisabled()) throw new Error('PAGE_BOUNDARY_NOT_ENFORCED');
      await page.getByLabel('阅读缩放').selectOption('1.25');
      await page.getByText('正在渲染页面…', {exact: true}).waitFor({state: 'hidden'});
      await page.screenshot({path: path.join(evidence, 'p1-unparsed-reader.png')});
      await page.getByRole('button', {name: '关闭', exact: true}).click();
      if ((await rpc('GET', '/v0/documents')).documents[0].parse_status !== 'not_started') throw new Error('READER_REQUIRED_PARSE');
      await createProject('项目乙');
      await page.getByLabel('当前项目', {exact: true}).selectOption({label: '项目甲 (1)'});
      await page.getByRole('button', {name: '详情', exact: true}).click();
      await page.getByRole('checkbox', {name: '项目乙', exact: true}).check();
      await page.getByRole('button', {name: '保存元数据', exact: true}).waitFor();
      await page.getByLabel('题名', {exact: true}).fill('人工维护的 BERT');
      await page.getByLabel('作者（每行一位）').fill('Jacob Devlin\nMing-Wei Chang');
      await page.getByLabel('年份', {exact: true}).fill('2019');
      await page.getByLabel('DOI', {exact: true}).fill('https://doi.org/10.18653/v1/N19-1423');
      await page.getByLabel('标签（逗号分隔）').fill('预训练，阅读中');
      await page.getByRole('button', {name: '保存元数据', exact: true}).click();
      await page.getByRole('dialog').waitFor({state: 'hidden'});
      await page.getByText('人工维护的 BERT', {exact: true}).waitFor();
      await page.getByLabel('筛选文献').fill('预训练');
      await page.getByRole('button', {name: '阅读', exact: true}).waitFor();
      await page.getByLabel('筛选文献').fill('');
      await page.getByLabel('当前项目', {exact: true}).selectOption({label: '项目乙 (1)'});
      const docs = (await rpc('GET', '/v0/documents')).documents;
      if (docs.length !== 1 || docs[0].project_ids.length !== 2 || docs[0].metadata_revision !== 1) throw new Error('P1_PERSISTENCE_ASSERTION_FAILED');
    }
    await page.getByRole('button', {name: '解析', exact: true}).click();
    await page.getByText('已解析', {exact: true}).waitFor({timeout: 30000});
    await page.screenshot({path: path.join(evidence, 'browser-library-preview.png'), fullPage: true});
    await page.getByRole('button', {name: '来源检索', exact: true}).click();
    await page.getByLabel('关键词或完整短语').fill('BERT');
    await page.getByRole('button', {name: '检索', exact: true}).click();
    await page.getByRole('button', {name: '查看原文'}).first().click();
    await page.getByRole('dialog').waitFor();
    await page.waitForFunction(() => {const canvas = document.querySelector('.pdf-page canvas'); return canvas && canvas.width > 100 && canvas.getContext('2d').getImageData(10,10,1,1).data[3] > 0;}, null, {timeout: 30000});
    await page.screenshot({path: path.join(evidence, 'browser-source-preview.png'), fullPage: true});
    if (p1) {
      await page.getByRole('button', {name: '关闭', exact: true}).click();
      await page.reload();
      await page.getByText('人工维护的 BERT', {exact: true}).waitFor();
      await page.getByRole('button', {name: '详情', exact: true}).click();
      if (await page.getByLabel('DOI', {exact: true}).inputValue() !== '10.18653/v1/n19-1423') throw new Error('METADATA_RELOAD_FAILED');
      if (!await page.getByRole('checkbox', {name: '项目甲', exact: true}).isChecked() || !await page.getByRole('checkbox', {name: '项目乙', exact: true}).isChecked()) throw new Error('MEMBERSHIP_RELOAD_FAILED');
      await page.screenshot({path: path.join(evidence, 'p1-metadata-preview.png')});
      if (process.env.RAGSYSTEM_WORKBENCH_SMOKE === '1') {
        await page.getByRole('button', {name:'关闭',exact:true}).click();
        await require('./browser_workbench.cjs')({page,rpc,root,evidence});
        if(process.env.RAGSYSTEM_HISTORY_SMOKE==='1')await require('./browser_history_lifecycle.cjs')({page,rpc,root,evidence});
        await page.getByRole('button',{name:'文献库',exact:false}).click();
        await page.getByRole('button',{name:'详情',exact:true}).click();
      }
      if (process.env.RAGSYSTEM_DOCLING_SMOKE === '1') {
        await page.getByRole('button',{name:'关闭',exact:true}).click();
        await require('./browser_docling.cjs')({page,rpc,root,evidence});
        await page.getByRole('button',{name:'文献库',exact:false}).click();
        await page.getByRole('button',{name:'详情',exact:true}).click();
      }
      if (process.env.RAGSYSTEM_BACKUP_SMOKE === '1') {
        await page.getByRole('button', {name: '关闭', exact: true}).click();
        await page.getByRole('button', {name: '设置与备份', exact: true}).click();
        await page.getByRole('button', {name: '创建备份', exact: true}).click();
        await page.getByText('已完成备份', {exact: true}).waitFor();
        await page.getByRole('button', {name: '从备份恢复副本', exact: true}).click();
        await page.getByRole('button', {name: '使用此恢复副本', exact: true}).waitFor();
        const restoreRecord=(await rpc('GET','/v0/backups')).records.find(row=>row.kind==='restored');
        const restoreTarget=await rpc('GET',`/v0/internal/restored-workspaces/${restoreRecord.id}`);
        await page.getByRole('button', {name: '使用此恢复副本', exact: true}).click();
        await page.getByText(`当前工作区：${path.basename(restoreTarget.data_root)}`,{exact:true}).waitFor({timeout:60000});
        await page.getByRole('button', {name: '文献库', exact: false}).click();
        await page.getByText('人工维护的 BERT', {exact: true}).waitFor();
        const restoredDocs = (await rpc('GET', '/v0/documents')).documents;
        if (restoredDocs.length !== 1 || restoredDocs[0].project_ids.length !== 2) throw new Error('RESTORED_DATA_LOST');
        if(process.env.RAGSYSTEM_DOCLING_SMOKE==='1'){
          const restoredTable=await rpc('GET',`/v0/tables/${globalThis.__doclingReviewedTableId}`);
          if(restoredTable.review.status!=='uncertain'||restoredTable.review.revision!==1)throw new Error('RESTORED_TABLE_REVIEW_LOST');
        }
        await page.screenshot({path: path.join(evidence, 'restored-workspace.png')});
      }
    }
    }
    if (errors.length) throw new Error('BROWSER_PAGE_ERRORS:' + errors.join(','));
    fs.writeFileSync(path.join(evidence, reference?'browser-ui-reference-smoke.json':mvp?(process.env.RAGSYSTEM_MVP_EXTRACTIVE_SMOKE==='1'?'browser-mvp-extractive-smoke.json':'browser-mvp-smoke.json'):'browser-smoke.json'), JSON.stringify({status: 'PASS', mvp_workflow:mvp, data_root: dataRoot, real_frozen_engine: process.env.RAGSYSTEM_BROWSER_SOURCE_ENGINE!=='1', transport: 'SIMULATED TAURI BRIDGE', native_dialogs_tested: false, full_native_e2e: false, windows_tested: false, p1_workflow: p1, workbench_workflow:process.env.RAGSYSTEM_WORKBENCH_SMOKE==='1', page_errors: errors, assertions: round3?['See MVP03-'+round3+'-browser.json']:round2?['See stage-'+round2+'-browser.json; real process; no native IME certification']:reference?['reference layouts/real states','batch import/dedup/parse','document filters/details','real E5/RRF/extractive answer','scope isolation','PDF source/review persistence/return','API consent/session key','backup/restore','responsive 1586/1200/720']:mvp?['three tabs/default QA','batch PDF/dedup/automatic parse','real E5/sqlite-vec index',process.env.RAGSYSTEM_MVP_EXTRACTIVE_SMOKE==='1'?'real cited extractive answer':'real cited local generation','SHA-verified PDF rendering','history reload','backup/restore persistence']:['real import shown', 'real parse shown', 'real FTS hits', 'SHA-verified PDF canvas rendered', ...(p1 ? ['project create/switch', 'project-targeted import', 'unparsed PDF reading/page jump/zoom', 'same original in two projects', 'metadata persisted across reload', 'DOI normalization', 'tag filter'] : [])]}, null, 2));
    console.log('BROWSER_UI_SMOKE: PASS; real engine process, simulated Tauri transport; not native/Windows acceptance');
  } catch (error) {
    const stamp = Date.now();
    if (page && !page.isClosed()) {
      await page.screenshot({path: path.join(evidence, `browser-failure-${stamp}.png`), fullPage: true});
      fs.writeFileSync(path.join(evidence, `browser-failure-${stamp}.json`), JSON.stringify({error: error.message, page_errors: errors, body: await page.locator('body').innerText()}, null, 2));
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    if (server) server.close();
    child.stdin.end();
    await Promise.race([once(child, 'exit'), new Promise(resolve => setTimeout(resolve, 10000))]);
    if (child.exitCode === null) child.kill();
  }
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
