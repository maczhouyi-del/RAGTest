import { invoke, isTauri } from "@tauri-apps/api/core";

export interface Health {
  system_question_forms?:Record<string,string[]>;
  status: "starting" | "ready" | "degraded";
  sidecar_version: string;
  schema_version: string;
  capabilities: string[];
  disabled_reasons: string[];
}
export interface DocumentRow {
  document_id: string;
  doc_version_id: string;
  title: string;
  file_sha256: string;
  size_bytes: number;
  parse_status: string;
  authors: string[];
  year: number | null;
  doi: string | null;
  venue: string;
  tags: string[];
  metadata_revision: number;
  metadata_origin: "manual" | "automatic" | null;
  abstract:string;
  metadata_origins:Record<string,"automatic"|"manual"|"confirmed">;
  metadata_candidates:Record<string,{id:string;value:string|string[]|number;source_page:number|null;source_excerpt:string|null;extraction_method:string;review_status:string}>;
  metadata_pending:boolean;
  metadata_extraction:{status:string;error_code:string|null};
  project_ids: string[];
  duplicate_candidates: string[];
}
export interface Project { id: string; name: string; document_count: number; created_at: string }
export interface MetadataInput {
  doc_version_id?:string;abstract?:string;field_actions?:Record<string,string>;
  expected_revision: number; title: string; authors: string[]; year: number | null;
  doi: string | null; venue: string; tags: string[];
}
export interface Job {
  job_id: string;
  label?: string;
  type: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  error_code: string | null;
  result_ref: string | null;
  updated_at: string;
}
export interface Snapshot {
  health: Health;
  documents: DocumentRow[];
  jobs: Job[];
  projects: Project[];
  workspace?: {label: string; warning: string; directory?: string};
  index?: IndexStatus;
  generator?: GeneratorStatus;
  ocr?: ParsingCandidateStatus;
  docling?: ParsingCandidateStatus;
}
export interface IndexStatus {configured: boolean; ready: boolean; visible_chunks: number; indexed_chunks: number; backend: string | null; model: string | null; generation: string | null; candidate_only: boolean}
export async function chooseEmbeddingModel(backend: string): Promise<{job_id: string} | null> {requireDesktop(); return invoke("choose_embedding_model", {backend});}
export interface BackupRecord {id: string; kind: "backup" | "restored"; label: string; document_count: number; embedding_count: number; manifest_sha256: string; created_at: string}
export async function listBackups(): Promise<{records: BackupRecord[]}> {requireDesktop(); return invoke("list_backups");}
export async function createBackup(): Promise<{job_id: string} | null> {requireDesktop(); return invoke("choose_backup_directory");}
export async function restoreBackup(): Promise<{job_id: string} | null> {requireDesktop(); return invoke("choose_restore_directories");}
export async function activateRestoredWorkspace(identifier: string): Promise<void> {requireDesktop(); return invoke("activate_restored_workspace", {identifier});}
export async function retryJob(jobId: string): Promise<void> {requireDesktop(); return invoke("retry_job", {jobId});}

function requireDesktop() {
  if (!isTauri()) throw new Error("DESKTOP_REQUIRED");
}
export async function snapshot(): Promise<Snapshot> {
  requireDesktop();
  return invoke<Snapshot>("workspace_snapshot");
}
export async function importPdf(projectId: string | null = null): Promise<{ job_id: string; status: string } | {jobs:Job[]} | null> {
  requireDesktop();
  return invoke("choose_pdf_and_import", {projectId});
}

export async function prepareMvp(versionIds:string[]):Promise<{job_id:string}>{requireDesktop();return invoke("prepare_mvp",{versionIds});}
export async function readMvpAnswer(answerId:string):Promise<AnswerRun>{requireDesktop();return invoke("read_mvp_answer",{answerId});}
export async function restartEngine(): Promise<void> {
  requireDesktop();
  return invoke("restart_engine");
}
export async function cancelJob(jobId: string): Promise<void> {
  requireDesktop();
  return invoke("cancel_job", { jobId });
}

export interface SearchHit {doc_version_id: string; chunk_id: string; source_anchor_id: string; page_number: number; preview: string; rank: number; location_confidence: string}
export interface SourceFile {evidence_quote?: string; anchor: {source_anchor_id: string; doc_version_id: string; file_sha256: string; page_number: number; location_level: string; reason_if_degraded?:string}; pdf_bytes: number[]}
export interface DocumentFile {document: {doc_version_id: string; file_sha256: string; title: string; page_number?:number}; pdf_bytes: number[]}
export type ReaderFile = SourceFile | DocumentFile;
export async function parseDocument(versionId: string, useOcr=false, useDocling=false, options?:{autoEnhance?:boolean;pageNumbers?:number[]|null}) {
  requireDesktop(); return invoke("parse_document", {versionId,useOcr,useDocling,autoEnhance:options?.autoEnhance??false,pageNumbers:options?.pageNumbers??null});
}
export async function searchSources(query: string, versionIds: string[], projectId: string | null = null, strategy = "keyword", filters?:{tag:string|null;year_from:number|null;year_to:number|null}): Promise<{results: SearchHit[]}> {
  requireDesktop(); return invoke("search_sources", {query, versionIds, projectId, strategy, filters:filters??null});
}
export async function readSource(sourceId: string): Promise<SourceFile> {
  requireDesktop(); return invoke("read_source", {sourceId});
}
export async function readDocument(versionId: string): Promise<DocumentFile> {
  requireDesktop(); return invoke("read_document", {versionId});
}
export async function createProject(name: string): Promise<Project> {
  requireDesktop(); return invoke("create_project", {name});
}
export async function setProjectDocument(projectId: string, documentId: string, linked: boolean): Promise<void> {
  requireDesktop(); return invoke("set_project_document", {projectId, documentId, linked});
}
export async function updateMetadata(documentId: string, metadata: MetadataInput): Promise<DocumentRow> {
  requireDesktop(); return invoke("update_document_metadata", {documentId, metadata});
}

const errors: Record<string, string> = {
  MAGPIE_LOCAL_ONLY: "Magpie 连接目前仅支持本机地址，路径须为 /v1。",
  MAGPIE_IDENTITY_INVALID: "目标服务未通过 Magpie 身份检查，请核对地址与端口。",
  PROVIDER_DOCUMENT_QA_DISABLED: "此模型服务尚未允许用于文献问答，请在设置中保存并启用；配置变更后需重新确认。",
  PROVIDER_CONSENT_REQUIRED: "请先确认允许向所选服务发送本次问题与检索片段。",
  PROVIDER_CHANGED: "模型连接已更新，请重新选择连接并确认本次发送范围。",
  PROVIDER_CREDENTIALS_REQUIRED: "当前引擎会话尚未配置此连接，请在设置中重新输入密钥并保存。",
  PROVIDER_ENDPOINT_INVALID: "接口地址无效。远程接口必须使用 HTTPS，地址以 /v1 结尾且不含凭据或查询参数。",
  PROVIDER_CATALOG_UNSUPPORTED: "服务不支持模型目录，请手动输入模型 ID；兼容性尚未验证。",
  PROVIDER_PARAMETER_UNSUPPORTED: "服务拒绝了生成参数。请检查模型是否支持 Chat Completions，并在接口兼容设置中调整 JSON 模式及输出预算参数。",
  PROVIDER_NOAUTH_LOCAL_ONLY: "无需认证模式仅支持本机自定义兼容服务，远程服务必须使用凭据。",
  PROVIDER_DRAFT_EXPIRED: "会话凭据草稿已过期或地址已变化，请重新输入密钥并检查连接。",
  METADATA_CANDIDATE_CHANGED: "自动候选已变化，请重新打开文献详情核对。",
  METADATA_EXTRACTION_FAILED: "元数据提取失败，原件与正文仍然可用，可重试该任务。",
  CONVERSATION_BUSY: "当前会话已有问答正在执行，请等待完成。",
  PROVIDER_KEY_INVALID: "密钥格式无效，请检查是否包含换行。",
  PROVIDER_AUTH_FAILED: "模型服务拒绝了认证，请核对当前会话密钥。",
  PROVIDER_UNAVAILABLE: "无法连接模型服务，请确认地址与服务状态后重试。",
  PROVIDER_TIMEOUT: "模型服务响应超时，请稍后重试。",
  PROVIDER_HTTP_ERROR: "模型服务返回错误，请检查服务端状态和接口兼容性。",
  PROVIDER_RESPONSE_INVALID: "模型服务返回了不兼容的数据格式。",
  PROVIDER_REDIRECT_FORBIDDEN: "模型服务请求被重定向，已停止发送。请填写最终接口地址。",
  PROVIDER_RESPONSE_LIMIT: "模型服务返回数据过大，本次请求已停止。",
  EMBEDDING_CONTEXT_LIMIT: "文本超过向量模型长度限制，未进行截断索引；请重新解析为较短片段。",
  INDEX_REBUILD_REQUIRED: "本地索引已变化或校验失败，请在文献页更新索引。已有向量会复用。",
  PREPARATION_PARTIAL: "部分文献准备失败，其他文献仍可使用。请查看失败任务并重试。",
  PREPARATION_FAILED: "文献准备未完成。原件已保留，请稍后重试。",
  DESKTOP_REQUIRED: "请在桌面应用中打开。浏览器预览无法访问本地文献。",
  SIDECAR_NOT_PACKAGED: "本地引擎尚未打包，请先按开发说明构建 Sidecar。",
  ENGINE_TIMEOUT: "本地组件加载或查询超时。任务记录仍保留，请稍后查看任务状态；无需直接重启。",
  ENGINE_UNAVAILABLE: "本地引擎没有响应。你可以重启引擎后重试。",
  ENGINE_START_FAILED: "本地引擎启动失败，请检查本轮构建与诊断记录。",
  ENGINE_PROTOCOL_MISMATCH: "桌面端与本地引擎协议版本不一致。",
  FILE_NOT_ALLOWED: "无法授权这个文件，请选择本机的普通 PDF 文件。",
  NOT_PDF: "所选文件没有有效的 PDF 文件头。",
  PDF_TOO_LARGE: "PDF 超过当前单文件 64 MiB 的处理上限。",
  SOURCE_CHANGED: "授权后文件内容发生变化，请重新选择文件。",
  OBJECT_CORRUPT: "已保存原件的校验不通过，导入已停止并保留诊断信息。",
  WORKER_BUSY: "已有任务正在处理，请稍后重试。",
  SESSION_INVALID: "引擎会话已失效，请重启引擎。",
  OCR_NOT_CONFIGURED: "请先在设置中选择已批准的离线 OCR 语言目录。",
  OCR_MODEL_HASH_MISMATCH: "OCR 语言数据校验失败，旧解析仍保留。请重新选择已批准资源。",
  OCR_MODEL_NOT_AVAILABLE: "OCR 语言数据不可用，请重新选择包含 eng 和 chi_sim 的目录。",
  OCR_RUNTIME_NOT_PACKAGED: "当前引擎未包含 OCR 候选运行时，请使用完整本地构建。",
  OCR_FINGERPRINT_CHANGED: "OCR 运行时指纹变化，请在设置中重新校验。",
  OCR_LOAD_FAILED: "OCR 候选加载失败，请检查任务与本地诊断记录。",
  PDF_EXTRACTION_FAILED: "PDF 提取失败。原件已保留，任务错误可查。",
  EMBEDDING_NOT_CONFIGURED: "尚未配置本地向量模型。",
  PROJECT_NAME_EXISTS: "已有同名项目，请换一个名称或选择已有项目。",
  INVALID_PROJECT: "项目名称需为 1–100 个字符。",
  PROJECT_NOT_FOUND: "项目不存在，请刷新项目列表。",
  METADATA_CONFLICT: "元数据已被其他操作更新。请关闭详情后重新打开，再核对修改。",
  INVALID_METADATA: "元数据格式不正确，请检查题名、作者、年份和 DOI。",
  DOCLING_NOT_CONFIGURED: "请先在设置中校验已批准的布局与表格资源目录。",
  DOCLING_MODEL_NOT_AVAILABLE: "布局与表格资源不完整，请重新选择固定候选目录。",
  DOCLING_MODEL_HASH_MISMATCH: "布局与表格资源校验失败，未启用该候选。",
  DOCLING_FINGERPRINT_CHANGED: "布局与表格运行时或模型指纹变化，请重新校验配置。",
  DOCLING_RUNTIME_NOT_PACKAGED: "当前引擎未包含可选布局与表格运行时，请使用完整本地试验构建。",
  DOCLING_PAGE_LIMIT: "布局与表格候选当前最多处理 40 页；原件和旧解析已保留。",
  DOCLING_PIXEL_LIMIT: "页面尺寸超过布局候选的资源上限，旧解析已保留。",
  DOCLING_CONVERSION_INCOMPLETE: "布局转换未完整结束，旧解析仍保留；可查看任务诊断。",
  DOCLING_STRUCTURE_INVALID: "候选表格结构无效，未替换旧解析。",
  DOCLING_STRUCTURE_LIMIT: "候选结构超过当前资源上限，未替换旧解析。",
  PDF_WORKER_TIMEOUT: "解析或模型校验超过当前时间上限，旧资料已保留；可在其他任务结束后重试。",
  PDF_WORKER_LOG_LIMIT: "解析进程输出过量，已停止并保留有界诊断。",
  PARSER_OPTIONS_CONFLICT: "请选择原文、OCR、布局表格或自动候选中的一种解析方式。",
  INVALID_PARSE_PAGES: "页码必须在 1–500 内，不重复，每次最多 40 页。",
  PARTIAL_PARSE_NEEDS_BASE: "请先完成一次全文解析，再更新指定页。",
  PARSE_PUBLICATION_CHANGED: "解析结果已被另一任务更新，旧资料仍保留，请刷新后新建任务。",
  PARSER_FINGERPRINT_CHANGED: "排队期间解析配置变化，请重新提交解析任务。",
  INVALID_SEARCH: "请输入有意义的关键词或问题。",
  INVALID_REQUEST: "输入格式不正确，请检查各字段。",
  SCOPE_FILTER_CHANGED: "文献元数据或筛选范围已有变化，请刷新后重新检索。",
  SCOPE_NOT_AVAILABLE: "文献范围已变化，请刷新后重新检索。",
  NOT_FOUND: "文献或来源已不可用，请刷新列表。",
  IDENTITY_CONFLICT: "版本或项目关联已有变化，归并或撤销未执行。请刷新并人工核对。",
  ANNOTATION_CONFLICT: "批注已有新修订，请刷新后重新编辑。",
  SOURCE_PAGE_INVALID: "页码超出该 PDF 的实际范围。",
  GENERATOR_NOT_CONFIGURED: "请先选择已批准的本地生成模型，或使用原文摘录模式。",
  DUPLICATE_PAPER_VERSIONS: "同一篇论文选择了多个 PDF 版本。逐篇 Research 每篇只能选一个版本，请核对范围。",
  INVALID_CURSOR: "历史游标无效，请重新打开工作台。",
  INVALID_PAGE: "研究分页范围无效，请返回该计划的第一页。",
  LIFECYCLE_CONFLICT: "文献状态或版本已有变化，请刷新后重新核对。",
  INVALID_LIFECYCLE: "请选择有效状态并填写变更原因。",
  SCOPE_IDENTITY_CHANGED: "冻结后文献身份已变化，请重新核对文件版本并新建研究计划。",
  INSUFFICIENT_EVIDENCE: "本轮证据不足以形成受支持的回答。可补充文献、调整范围，或进入逐篇研究。",
  MODEL_WORKER_FAILED: "本地生成进程异常退出，资料和检查点已保留。可重试或使用摘录模式。",
  MODEL_TIMEOUT: "本地生成超时，进程已停止；资料和检查点已保留。",
  ENGINE_RESTARTED: "上次引擎中断，旧任务已隔离。可按任务类型重试或继续研究计划。",
  MODEL_RERANK_INVALID: "相关性复核返回无效排序，结果未发布。可改用不含模型复核的检索策略。",
  MODEL_OUTPUT_INVALID: "模型没有返回有效结构，草稿未发布。可以重试或改用摘录模式。",
  MODEL_CITATION_INVALID: "模型引用不属于本轮原文或引文不匹配，草稿已拒绝发布。",
  MODEL_CONTEXT_LIMIT: "输入超出当前候选模型的上下文限制，请缩小范围或使用摘录模式。",
  MODEL_FINGERPRINT_CHANGED: "本地模型运行时或指纹变化，请重新校验配置。",
  SCOPE_STALE: "冻结范围的解析批次已经变化，请重新创建研究计划或问题。",
  RESEARCH_REQUIRED: "这个问题需要逐篇覆盖。当前问答仅检索局部来源，请缩小问题范围，不能据此推断全库结论。",
  REVIEW_CONFLICT: "该研究记录已有新修订，请关闭编辑器并刷新后重新核对。",
  EXPORT_EXISTS: "目标文件已经存在，请选择一个新文件名。",
  EXPORT_PATH_INVALID: "请选择工作区之外、普通本机目录内的新报告文件。",
  EXPORT_WRITE_FAILED: "报告写入失败，中间文件已保留，请检查空间或权限。",
  BATCH_LIMIT: "每批最多选择 32 个 PDF。",
  MODEL_RUNTIME_NOT_PACKAGED: "当前引擎未包含本地推理依赖，请使用完整本地试验构建。",
  MODEL_NOT_AVAILABLE: "配置的本地模型不可用，请重新选择已批准的模型目录。",
  MODEL_HASH_MISMATCH: "模型文件校验不通过，未启用该资源。",
  MODEL_UNSUPPORTED: "当前仅接入了已批准固定版本的 multilingual-e5-small 候选。",
  NO_PARSED_DOCUMENTS: "请先导入并解析文献，再建立向量索引。",
  INDEX_SCOPE_CHANGED: "索引构建期间文献范围变化，旧索引仍保留，请重试。",
  DIRECTORY_NOT_ALLOWED: "请选择本机的普通目录；符号链接、网络目录或不可访问的位置不能授权。",
  DIRECTORY_CHANGED: "授权目录发生变化，请重新选择。",
  BACKUP_MANIFEST_INVALID: "备份清单或数据库校验不通过，恢复已停止。",
  BACKUP_HASH_MISMATCH: "备份文件校验不通过，未覆盖当前资料。",
  BACKUP_IO_FAILED: "备份或恢复失败，请检查磁盘空间和目录权限；中间文件已保留。",
  RESTORE_INCOMPLETE: "恢复副本不完整，不能切换工作区。",
  WORKSPACE_CHANGED: "工作区已经切换，请在当前工作区重新操作。",
  CONFIG_SAVE_FAILED: "工作区设置保存失败，当前资料库仍保留。",
  RESELECT_FILE_REQUIRED: "该任务尚无完整原件，请重新选择原 PDF 导入。",
  REAUTHORIZE_REQUIRED: "请重新选择备份或恢复目录来重试此操作。",
  ATTEMPT_LIMIT: "已达到此任务的重试上限，请检查原因后重新发起操作。",
  JOB_NOT_RETRYABLE: "该任务当前不能重试。",
  RESTORED_JOB_REQUIRES_REVIEW: "此任务来自备份快照，请核对后重试；它当前没有在运行。",
};
export function errorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : String(error);
  return errors[code] ?? `操作未完成（${code.slice(0, 100)}）。`;
}

export type ParsingCandidateStatus=Omit<GeneratorStatus,"loaded">;
export interface GeneratorStatus {configured: boolean; loaded: boolean; fingerprint: Record<string, unknown> | null; candidate_only: boolean}
export interface ScopeDocument {document_id?: string; doc_version_id: string; file_sha256: string; title: string; parse_run_ids: string[]; parse_status: string}
export interface Evidence {table_candidates?:{table_id:string;cell_id:string;row_start:number;column_start:number}[];text_origin?:string;id: string; source_anchor_id: string; quote: string; anchor_json: string; human_status: string; review_note: string; reviews?: {id:string;status:string;note:string;created_at:string}[]; current_source_status: string}
export interface Claim {id: string; text: string; evidence_ids: string[]; source_status: string; model_support: string; comparability: string; human_status: string}
export interface ModelAttempt {job_id: string; created_at: string; fingerprint: Record<string,unknown>}
export interface AnswerRun {model_history?: ModelAttempt[];id: string; conversation_id: string; question: string; status: string; mode: string; strategy: string; error_code: string | null; scope: ScopeDocument[]; claims: Claim[]; evidence: Evidence[]; result: {intent?:string;retrieval_status?:string;text?:string;system_topic?:string;configuration?:Record<string,unknown>;relevance_review?:Record<string,unknown>|null; kind: string; coverage: string; support_checks?: {claim_id: string; status: string; reason: string}[]} | null}
export interface Observation {model_fingerprint?: Record<string,unknown> | null;field: string; value: string; unit: string; evidence_id: string; experiment_id: string; conditions_status: string; meaning_status: string; value_origin: string; conditions: Record<string,string>; revision: number}
export interface ResearchItem {observation_count?:number;observation_offset?:number;observation_next_offset?:number|null;field_counts?:Record<string,number>;doc_version_id: string; status: string; processed_chunks: number; total_chunks: number; error_code: string | null; observations: Observation[]}
export interface Report {source_warnings?:{doc_version_id:string;state:string;parse_changed?:boolean}[];id: string; revision: number; body: string; created_at: string}
export interface ResearchPlan {scope_count?:number;paper_offset?:number;paper_list?:{doc_version_id:string;title:string}[];source_warnings?:{doc_version_id:string;state:string;note:string}[];model_history?: ModelAttempt[];id: string; question: string; status: string; mode: string; scope: ScopeDocument[]; scope_warnings?: {doc_version_id:string;title:string;code:string}[]; fields: string[]; items: ResearchItem[]; evidence: Evidence[]; reports: Omit<Report,"body">[]; coverage: Record<string,number>}
export interface HistoryEntry {id:string;question:string;status:string;mode:string;created_at:string;conversation_id?:string}
export interface HistoryPage {items:HistoryEntry[];next_cursor:string|null;total:number}
export interface WorkbenchSnapshot {answer_index:HistoryPage;research_index:HistoryPage;answers: AnswerRun[]; plans: ResearchPlan[]; generator: GeneratorStatus}
export async function workbenchSnapshot(projectId: string | null, selection?:{answerId:string|null;planId:string|null;paperOffset:number;observationOffset:number}): Promise<WorkbenchSnapshot> {requireDesktop();return invoke("workbench_snapshot",{projectId,...selection});}
export async function chooseGeneratorModel(): Promise<{job_id: string} | null> {requireDesktop(); return invoke("choose_generator_model");}
export async function askQuestion(body: {question: string; version_ids: string[]; project_id: string | null; mode: string; strategy: string; conversation_id: string | null; provider_id?: string | null; allow_external?: boolean; provider_revision?: number; per_paper_limit?: number}): Promise<{id: string; conversation_id: string}> {requireDesktop();return invoke("ask_question",{body});}
export async function createResearchPlan(body: {question: string; fields: string[]; version_ids: string[]; project_id: string | null; mode: string}): Promise<{id: string}> {requireDesktop();return invoke("create_research_plan",{body});}
export async function runResearchPlan(planId: string): Promise<{job_id: string}> {requireDesktop();return invoke("run_research_plan",{planId});}
export async function reviewEvidence(targetId: string,status: string,note: string): Promise<void> {requireDesktop();return invoke("review_evidence",{targetId,body:{status,note}});}
export async function editObservation(planId: string, observation: Observation, body: Omit<Observation,"field"|"value_origin"|"evidence_id"|"revision"|"model_fingerprint">): Promise<void> {requireDesktop();return invoke("edit_observation",{planId,evidenceId:observation.evidence_id,body:{...body,expected_revision:observation.revision}});}
export async function createResearchReport(planId: string): Promise<Report> {requireDesktop();return invoke("create_research_report",{planId});}
export async function exportResearchReport(reportId: string): Promise<{saved: boolean; label: string} | null> {requireDesktop();return invoke("export_research_report",{reportId});}

export interface MergeRecord {id: string; source_id: string; target_id: string; source_title: string; target_title: string; status: string; created_at: string}
export async function identitySnapshot(): Promise<{records: MergeRecord[]}> {requireDesktop(); return invoke("identity_snapshot");}
export async function mergeDocumentVersions(sourceId: string,targetId: string,expectedVersionIds: string[]): Promise<MergeRecord> {requireDesktop();return invoke("merge_document_versions",{body:{source_id:sourceId,target_id:targetId,expected_version_ids:expectedVersionIds}});}
export async function undoDocumentMerge(mergeId: string): Promise<void> {requireDesktop();return invoke("undo_document_merge",{mergeId});}
export interface Annotation {id: string; doc_version_id: string; page_number: number; note: string; revision: number; history: {revision:number;note:string;created_at:string}[]}
export async function listAnnotations(versionId:string): Promise<{annotations:Annotation[]}> {requireDesktop();return invoke("list_annotations",{versionId});}
export async function saveAnnotation(versionId:string,body:{annotation_id:string|null;source_anchor_id:string|null;expected_revision:number;page_number:number;note:string}): Promise<void> {requireDesktop();return invoke("save_annotation",{versionId,body});}

export interface ParseDiagnostics {publication_revision:number;unlocated_items:number;runs:{id:string;status:string;page_count:number|null;error_code:string|null;created_at:string;parser_configuration?:Record<string,unknown>|null;attempts?:{id:string;method:string;status:string;page_numbers_json:string;error_code:string|null}[];routing?:Record<string,unknown>[]}[];pages:{page_number:number;quality:string;error_code:string|null;text_chars:number}[];needs_ocr_pages:number[];ocr_configured:boolean;docling_configured:boolean}
export async function inspectDocumentParse(versionId:string): Promise<ParseDiagnostics> {requireDesktop();return invoke("inspect_document_parse",{versionId});}

export async function chooseOcrModel(): Promise<{job_id:string}|null> {requireDesktop();return invoke("choose_ocr_model");}

export async function chooseDoclingModel(): Promise<{job_id:string}|null> {requireDesktop();return invoke("choose_docling_model");}
export interface TableSummary {id:string;page_number:number|null;source_pages:number[];row_count:number;column_count:number;ordinal:number}
export interface TableCandidate extends Omit<TableSummary,"ordinal"> {doc_version_id:string;parse_run_id:string;cells:{id:string;row_start:number;row_end:number;column_start:number;column_end:number;text:string;column_header:0|1;row_header:0|1}[];row_offset:number;next_row_offset:number|null;review:{revision:number;status:string;note:string};review_history:{revision:number;status:string;note:string;created_at:string}[]}
export async function listDocumentTables(versionId:string,offset=0):Promise<{tables:TableSummary[];total:number;next_offset:number|null;parse_run_id:string|null}>{requireDesktop();return invoke("list_document_tables",{versionId,offset});}
export async function readTableCandidate(tableId:string,rowOffset=0):Promise<TableCandidate>{requireDesktop();return invoke("read_table_candidate",{tableId,rowOffset});}
export async function reviewTableCandidate(tableId:string,body:{expected_revision:number;status:string;note:string}):Promise<TableCandidate>{requireDesktop();return invoke("review_table_candidate",{tableId,body});}

export interface LifecycleRecord {document_id:string;title:string;state:string;revision:number;note:string;origin:string;versions:{doc_version_id:string;file_sha256:string;visibility:string}[];history:{revision:number;created_at:string;before_json:string;after_json:string}[]}
export async function lifecycleSnapshot():Promise<{records:LifecycleRecord[]}>{requireDesktop();return invoke("lifecycle_snapshot");}
export async function updateDocumentLifecycle(documentId:string,body:{expected_revision:number;state:string;note:string}):Promise<LifecycleRecord>{requireDesktop();return invoke("update_document_lifecycle",{documentId,body});}

export async function historyPage(kind:string,projectId:string|null,cursor:string):Promise<HistoryPage>{requireDesktop();return invoke("history_page",{kind,projectId,cursor});}
export async function readResearchReport(reportId:string):Promise<Report>{requireDesktop();return invoke("read_research_report",{reportId});}

export interface GenerationConnection {id:string; name:string; kind:"api"|"magpie"; base_url:string; model:string; revision:number; configured:boolean;can_answer:boolean;document_qa_enabled:boolean;authorization_revision:number|null;saved:boolean;vendor:"custom"|"deepseek"|"openai"|"magpie";auth_mode:"bearer"|"none";output_mode:string;token_parameter:string;credential_available:boolean;connection_verified:boolean;generation_verified:boolean;last_error:string|null}
export async function generationConnections():Promise<{providers:GenerationConnection[]}>{requireDesktop();return invoke("list_generation_providers");}
export async function saveGenerationConnection(body:{id:string|null;name:string;kind:string;base_url:string;model:string;expected_revision:number;api_key:string;vendor?:string;auth_mode?:string;output_mode?:string;token_parameter?:string;credential_token?:string|null;enable_for_documents?:boolean|null}):Promise<GenerationConnection>{requireDesktop();return invoke("save_generation_provider",{body});}
export async function probeGenerationConnection(identifier:string):Promise<{models:{id:string;name:string}[]}>{requireDesktop();return invoke("probe_generation_provider",{identifier});}

export async function previewGenerationConnection(body:{kind:string;base_url:string;api_key:string;auth_mode?:string}):Promise<{models:{id:string;name:string}[];credential_token:string;connection_verified:boolean;warning:string|null}>{requireDesktop();return invoke("preview_generation_provider",{body});}

export interface ConversationTurns {items:AnswerRun[];total:number;next_cursor:string|null;conversation:{id:string;title:string}}
export async function createConversation():Promise<{id:string}>{requireDesktop();return invoke("create_conversation");}
export async function conversationTurns(conversationId:string,cursor=""):Promise<ConversationTurns>{requireDesktop();return invoke("conversation_turns",{conversationId,cursor});}

export async function authorizeGenerationConnection(identifier:string,expectedRevision:number,enabled:boolean):Promise<GenerationConnection>{requireDesktop();return invoke("authorize_generation_provider",{identifier,expectedRevision,enabled});}
