mod sidecar;

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sidecar::Sidecar;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;

struct Bridge {
    engine: Mutex<Option<Sidecar>>,
    root: Mutex<PathBuf>,
    preference: PathBuf,
    warning: String,
    recovering: AtomicBool,
    start_allowed: AtomicBool,
}

impl Bridge {
    fn current_root(&self) -> Result<PathBuf, String> {
        self.root
            .lock()
            .map(|root| root.clone())
            .map_err(|_| "ENGINE_LOCK_FAILED".into())
    }
    fn with_engine<T>(
        &self,
        action: impl FnOnce(&Sidecar) -> Result<T, String>,
    ) -> Result<T, String> {
        let mut engine = self.engine.lock().map_err(|_| "ENGINE_LOCK_FAILED")?;
        if let Some(current) = engine.as_mut() {
            if !current.is_running()? {
                engine.take();
                self.start_allowed.store(false, Ordering::SeqCst);
                return Err("ENGINE_EXITED".into());
            }
        }
        if engine.is_none() {
            if !self.start_allowed.load(Ordering::SeqCst) { return Err("ENGINE_UNAVAILABLE".into()); }
            match Sidecar::start(&self.current_root()?) {
                Ok(current) => *engine = Some(current),
                Err(error) => {self.start_allowed.store(false, Ordering::SeqCst); return Err(error);}
            }
        }
        action(engine.as_ref().ok_or("ENGINE_UNAVAILABLE")?)
    }

    fn recover_engine(&self, force: bool) -> Result<(), String> {
        if self.recovering.swap(true, Ordering::SeqCst) {return Err("ENGINE_RECOVERING".into());}
        let result = (|| {
            let mut engine = self.engine.lock().map_err(|_| "ENGINE_LOCK_FAILED")?;
            if let Some(current) = engine.as_mut() {
                if current.is_running()? && !force {
                    // A live but unhealthy process may be completing work. Never kill on a health timeout.
                    current.request("GET", "/v0/health", None).map_err(|_| "ENGINE_HEALTH_FAILED")?;
                    return Ok(());
                }
            }
            if let Some(mut old) = engine.take() {old.stop();}
            self.start_allowed.store(false, Ordering::SeqCst);
            *engine = Some(Sidecar::start(&self.current_root()?)?);
            self.start_allowed.store(true, Ordering::SeqCst);
            Ok(())
        })();
        self.recovering.store(false, Ordering::SeqCst);
        result
    }
}

#[tauri::command]
async fn workspace_snapshot(state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            let health = engine.request("GET", "/v0/health", None)?;
            let documents = engine.request("GET", "/v0/documents", None)?;
            let jobs = engine.request("GET", "/v0/jobs", None)?;
            let projects = engine.request("GET", "/v0/projects", None)?;
            let index = engine.request("GET", "/v0/index", None)?;
            let generator = engine.request("GET", "/v0/generator", None)?;
            let ocr = engine.request("GET", "/v0/ocr", None)?;
            let docling = engine.request("GET", "/v0/docling", None)?;
            let root = bridge.current_root()?;
            Ok(json!({"health":health,"documents":documents["documents"],"jobs":jobs["jobs"],"projects":projects["projects"],"index":index,"generator":generator,"ocr":ocr,"docling":docling,"workspace":{"label":root.file_name().and_then(|s|s.to_str()).unwrap_or("RAGSystem"),"warning":bridge.warning,"directory":root.to_string_lossy()}}))
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn choose_pdf_and_import(
    app: tauri::AppHandle,
    project_id: Option<String>,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    if project_id.as_ref().is_some_and(|id| !valid_job_id(id)) {
        return Err("INVALID_PROJECT".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let selected_root = bridge.current_root()?;
        let selected = app.dialog().file().add_filter("PDF", &["pdf"]).blocking_pick_files();
        let Some(files) = selected else {return Ok(None);};
        if files.len() > 32 || files.is_empty() {return Err("BATCH_LIMIT".into());}
        bridge.with_engine(|engine| {
            if bridge.current_root()? != selected_root {return Err("WORKSPACE_CHANGED".into());}
            let paths = files.into_iter().map(|file| file.into_path().map_err(|_| "FILE_NOT_ALLOWED".to_string())).collect::<Result<Vec<_>, _>>()?;
            import_selected_paths(paths, project_id, |path, body| engine.request("POST", path, Some(body))).map(Some)
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

fn import_selected_paths(paths: Vec<PathBuf>, project_id: Option<String>, mut request: impl FnMut(&str, Value) -> Result<Value, String>) -> Result<Value, String> {
    let batch = request("/v0/internal/file-grants/batch", json!({"paths": paths}))?;
    let grants = batch["grants"].as_array().ok_or("ENGINE_PROTOCOL_MISMATCH")?.iter().map(|row| row["file_grant_id"].clone()).collect::<Vec<_>>();
    if grants.len() != paths.len() || grants.iter().any(|id| id.as_str().is_none_or(|id| id.is_empty())) {return Err("ENGINE_PROTOCOL_MISMATCH".into());}
    let result = (|| {
        if grants.len() == 1 {
            request("/v0/imports", json!({"file_grant_id":grants[0],"idempotency_key":random_key()?,"project_id":project_id}))
        } else {
            request("/v0/import-batches", json!({"file_grant_ids":grants,"idempotency_key":random_key()?,"project_id":project_id}))
        }
    })();
    if result.is_err() {
        // The engine ignores already-consumed grants; never touch task-owned descriptors.
        request("/v0/internal/file-grants/revoke", json!({"file_grant_ids":grants})).map_err(|_| "GRANT_CLEANUP_FAILED")?;
    }
    result
}

#[tauri::command]
async fn restart_engine(force: Option<bool>, state: State<'_, Arc<Bridge>>) -> Result<(), String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.recover_engine(force.unwrap_or(false))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

fn valid_job_id(id: &str) -> bool {
    id.len() == 36
        && id.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
}

#[tauri::command]
async fn cancel_job(job_id: String, state: State<'_, Arc<Bridge>>) -> Result<(), String> {
    if !valid_job_id(&job_id) {
        return Err("INVALID_JOB_ID".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request("POST", &format!("/v0/jobs/{job_id}/cancel"), None)?;
            Ok(())
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn parse_document(
    version_id: String,
    use_ocr: Option<bool>,
    use_docling: Option<bool>,
    auto_enhance: Option<bool>,
    page_numbers: Option<Vec<u16>>,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&version_id) {
        return Err("INVALID_DOCUMENT_ID".into());
    }
    if let Some(ref pages) = page_numbers {
        if pages.is_empty()
            || pages.len() > 40
            || pages.iter().any(|n| *n == 0 || *n > 500)
            || pages
                .iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                != pages.len()
        {
            return Err("INVALID_PARSE_PAGES".into());
        }
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            let mut entropy = [0u8; 16];
            getrandom::fill(&mut entropy).map_err(|_| "ENTROPY_UNAVAILABLE")?;
            let key: String = entropy.iter().map(|b| format!("{b:02x}")).collect();
            engine.request(
                "POST",
                &format!("/v0/documents/{version_id}/parse"),
                Some(json!({"idempotency_key":key,"use_ocr":use_ocr.unwrap_or(false),"use_docling":use_docling.unwrap_or(false),"auto_enhance":auto_enhance.unwrap_or(false),"page_numbers":page_numbers})),
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn search_sources(
    query: String,
    filters: Option<Value>,
    version_ids: Vec<String>,
    project_id: Option<String>,
    strategy: Option<String>,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    let strategy = strategy.unwrap_or("fts_only".into());
    if !["fts_only", "keyword", "vector_exact", "hybrid"].contains(&strategy.as_str()) {
        return Err("INVALID_SEARCH".into());
    }
    if query.len() > 20000
        || version_ids.is_empty()
        || version_ids.len() > 1000
        || version_ids.iter().any(|id| !valid_job_id(id))
        || project_id.as_ref().is_some_and(|id| !valid_job_id(id))
    {
        return Err("INVALID_SEARCH".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || bridge.with_engine(|engine|
        engine.request("POST", "/v0/search", Some(json!({"query":query,"strategy":strategy,"authorized_doc_version_ids":version_ids,"k":20,"project_id":project_id,"filters":filters})))
    )).await.map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn read_source(source_id: String, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    if !valid_job_id(&source_id) {
        return Err("INVALID_SOURCE_ID".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            let anchor = engine.request("GET", &format!("/v0/source-anchors/{source_id}"), None)?;
            let hash = anchor["file_sha256"]
                .as_str()
                .ok_or("ENGINE_PROTOCOL_MISMATCH")?;
            let bytes = verified_pdf_bytes(&bridge.current_root()?, hash)?;
            Ok(json!({"anchor":anchor,"pdf_bytes":bytes}))
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

fn verified_pdf_bytes(root: &std::path::Path, hash: &str) -> Result<Vec<u8>, String> {
    if hash.len() != 64
        || !hash
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err("ENGINE_PROTOCOL_MISMATCH".into());
    }
    let path = root.join("papers").join(format!("{hash}.pdf"));
    if std::fs::symlink_metadata(&path)
        .map_err(|_| "OBJECT_CORRUPT")?
        .file_type()
        .is_symlink()
    {
        return Err("OBJECT_CORRUPT".into());
    }
    let file = std::fs::File::open(path).map_err(|_| "OBJECT_CORRUPT")?;
    let mut bytes = Vec::new();
    file.take(64 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "OBJECT_CORRUPT")?;
    if bytes.len() > 64 * 1024 * 1024 || format!("{:x}", Sha256::digest(&bytes)) != hash {
        return Err("OBJECT_CORRUPT".into());
    }
    Ok(bytes)
}

#[tauri::command]
async fn create_project(name: String, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    if name.trim().is_empty() || name.chars().count() > 100 {
        return Err("INVALID_PROJECT".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request("POST", "/v0/projects", Some(json!({"name":name})))
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn set_project_document(
    project_id: String,
    document_id: String,
    linked: bool,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&project_id) || !valid_job_id(&document_id) {
        return Err("INVALID_DOCUMENT_ID".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                &format!("/v0/projects/{project_id}/documents/{document_id}"),
                Some(json!({"linked":linked})),
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn update_document_metadata(
    document_id: String,
    metadata: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&document_id) || !metadata.is_object() || metadata.to_string().len() > 16000 {
        return Err("INVALID_METADATA".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                &format!("/v0/documents/{document_id}/metadata"),
                Some(metadata),
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn read_document(version_id: String, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    if !valid_job_id(&version_id) {
        return Err("INVALID_DOCUMENT_ID".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            let document =
                engine.request("GET", &format!("/v0/documents/{version_id}/file"), None)?;
            let hash = document["file_sha256"]
                .as_str()
                .ok_or("ENGINE_PROTOCOL_MISMATCH")?;
            let bytes = verified_pdf_bytes(&bridge.current_root()?, hash)?;
            Ok(json!({"document":document,"pdf_bytes":bytes}))
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

fn random_key() -> Result<String, String> {
    let mut bytes = [0u8; 16];
    getrandom::fill(&mut bytes).map_err(|_| "ENTROPY_UNAVAILABLE")?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

fn valid_restored_root(path: &std::path::Path, identifier: &str) -> bool {
    if !valid_job_id(identifier)
        || !path.is_absolute()
        || path.file_name().and_then(|v| v.to_str())
            != Some(&format!("ragsystem-restored-{identifier}"))
    {
        return false;
    }
    if path.ancestors().any(|p| {
        std::fs::symlink_metadata(p)
            .map(|m| m.file_type().is_symlink())
            .unwrap_or(true)
    }) {
        return false;
    }
    let identity = std::fs::read(path.join("workspace-identity.json"))
        .ok()
        .and_then(|v| serde_json::from_slice::<Value>(&v).ok());
    identity == Some(json!({"restore_id":identifier})) && path.join("data/research.db").is_file()
}

#[tauri::command]
async fn retry_job(job_id: String, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    if !valid_job_id(&job_id) {
        return Err("INVALID_JOB_ID".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge
            .with_engine(|engine| engine.request("POST", &format!("/v0/jobs/{job_id}/retry"), None))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn list_backups(state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("GET", "/v0/backups", None))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

fn directory_grant(engine: &Sidecar, path: PathBuf, purpose: &str) -> Result<Value, String> {
    if !path.is_absolute() {
        return Err("DIRECTORY_NOT_ALLOWED".into());
    }
    engine.request(
        "POST",
        "/v0/internal/directory-grants",
        Some(json!({"path":path,"purpose":purpose})),
    )
}

#[tauri::command]
async fn choose_backup_directory(
    app: tauri::AppHandle,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let root = bridge.current_root()?;
        let Some(selected) = app.dialog().file().set_title("选择备份保存目录").blocking_pick_folder() else {return Ok(None);};
        let path = selected.into_path().map_err(|_|"DIRECTORY_NOT_ALLOWED")?;
        bridge.with_engine(|engine| {
            if bridge.current_root()? != root {return Err("WORKSPACE_CHANGED".into());}
            let grant = directory_grant(engine, path, "backup_parent")?;
            Ok(Some(engine.request("POST", "/v0/backups", Some(json!({"parent_grant_id":grant["directory_grant_id"],"idempotency_key":random_key()?})))?))
        })
    }).await.map_err(|_|"ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn choose_restore_directories(
    app: tauri::AppHandle,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let root = bridge.current_root()?;
        let Some(source) = app.dialog().file().set_title("选择包含 manifest.json 的备份文件夹").blocking_pick_folder() else {return Ok(None);};
        let Some(parent) = app.dialog().file().set_title("选择恢复副本的父目录（不会覆盖已有目录）").blocking_pick_folder() else {return Ok(None);};
        let source = source.into_path().map_err(|_|"DIRECTORY_NOT_ALLOWED")?;
        let parent = parent.into_path().map_err(|_|"DIRECTORY_NOT_ALLOWED")?;
        bridge.with_engine(|engine| {
            if bridge.current_root()? != root {return Err("WORKSPACE_CHANGED".into());}
            let source = directory_grant(engine, source, "snapshot")?;
            let parent = directory_grant(engine, parent, "restore_parent")?;
            Ok(Some(engine.request("POST", "/v0/backups", Some(json!({"source_grant_id":source["directory_grant_id"],"parent_grant_id":parent["directory_grant_id"],"idempotency_key":random_key()?})))?))
        })
    }).await.map_err(|_|"ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn activate_restored_workspace(
    identifier: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<(), String> {
    if !valid_job_id(&identifier) {
        return Err("INVALID_DOCUMENT_ID".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let mut engine = bridge.engine.lock().map_err(|_| "ENGINE_LOCK_FAILED")?;
        let old_root = bridge.current_root()?;
        if engine.is_none() {
            *engine = Some(Sidecar::start(&old_root)?);
        }
        let restored = engine.as_ref().ok_or("ENGINE_UNAVAILABLE")?.request(
            "GET",
            &format!("/v0/internal/restored-workspaces/{identifier}"),
            None,
        )?;
        let path = PathBuf::from(
            restored["data_root"]
                .as_str()
                .ok_or("ENGINE_PROTOCOL_MISMATCH")?,
        );
        if !valid_restored_root(&path, &identifier) {
            return Err("RESTORE_INCOMPLETE".into());
        }
        let mut replacement = Sidecar::start(&path)?;
        let persist = || -> Result<(), String> {
            let parent = bridge.preference.parent().ok_or("CONFIG_SAVE_FAILED")?;
            std::fs::create_dir_all(parent).map_err(|_| "CONFIG_SAVE_FAILED")?;
            let temporary = parent.join(format!("workspace-{}.json.tmp", random_key()?));
            let mut output = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&temporary)
                .map_err(|_| "CONFIG_SAVE_FAILED")?;
            output
                .write_all(
                    json!({"data_root":path,"restore_id":identifier})
                        .to_string()
                        .as_bytes(),
                )
                .map_err(|_| "CONFIG_SAVE_FAILED")?;
            output.sync_all().map_err(|_| "CONFIG_SAVE_FAILED")?;
            std::fs::rename(temporary, &bridge.preference).map_err(|_| "CONFIG_SAVE_FAILED")?;
            Ok(())
        };
        if let Err(error) = persist() {
            replacement.stop();
            return Err(error);
        }
        if let Some(mut old) = engine.take() {
            old.stop();
        }
        *bridge.root.lock().map_err(|_| "ENGINE_LOCK_FAILED")? = path;
        *engine = Some(replacement);
        Ok(())
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn choose_embedding_model(
    backend: String,
    app: tauri::AppHandle,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    if !["sqlite-vec", "lancedb"].contains(&backend.as_str()) {
        return Err("VECTOR_BACKEND_INVALID".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let root = bridge.current_root()?;
        let Some(path) = app.dialog().file().set_title("选择已批准的 multilingual-e5-small 本地模型目录").blocking_pick_folder() else {return Ok(None);};
        let path = path.into_path().map_err(|_|"DIRECTORY_NOT_ALLOWED")?;
        bridge.with_engine(|engine| {
            if bridge.current_root()? != root {return Err("WORKSPACE_CHANGED".into());}
            let grant = directory_grant(engine, path, "embedding")?;
            Ok(Some(engine.request("POST", "/v0/index", Some(json!({"backend":backend,"model_grant_id":grant["directory_grant_id"],"idempotency_key":random_key()?})))?))
        })
    }).await.map_err(|_|"ENGINE_TASK_FAILED")?
}

fn history_scope(project_id: Option<&str>) -> Result<String, String> {
    if project_id.is_some_and(|id| !valid_job_id(id)) {
        return Err("INVALID_PROJECT".into());
    }
    Ok(project_id
        .map(|id| format!("project_id={id}&"))
        .unwrap_or_default())
}

#[tauri::command]
async fn workbench_snapshot(
    project_id: Option<String>,
    answer_id: Option<String>,
    plan_id: Option<String>,
    paper_offset: Option<u32>,
    observation_offset: Option<u32>,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    let scope = history_scope(project_id.as_deref())?;
    if answer_id.as_ref().is_some_and(|id| !valid_job_id(id))
        || plan_id.as_ref().is_some_and(|id| !valid_job_id(id))
    {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            let answers = engine.request("GET", &format!("/v0/history/answers?{scope}limit=30"), None)?;
            let research = engine.request("GET", &format!("/v0/history/research?{scope}limit=30"), None)?;
            let answer = answer_id.as_deref().or_else(||answers["items"][0]["id"].as_str()).map(|id|engine.request("GET", &format!("/v0/answers/{id}?{scope}"), None)).transpose()?;
            let plan = plan_id.as_deref().or_else(||research["items"][0]["id"].as_str()).map(|id|engine.request("GET", &format!("/v0/research/{id}?{scope}paper_offset={}&observation_offset={}",paper_offset.unwrap_or(0),observation_offset.unwrap_or(0)), None)).transpose()?;
            let generator = engine.request("GET", "/v0/generator", None)?;
            Ok(json!({"answers":answer.into_iter().collect::<Vec<_>>(),"plans":plan.into_iter().collect::<Vec<_>>(),"answer_index":answers,"research_index":research,"generator":generator}))
        })
    }).await.map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn history_page(
    kind: String,
    project_id: Option<String>,
    cursor: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !["answers", "research", "conversations"].contains(&kind.as_str())
        || cursor.len() > 512
        || !cursor
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return Err("INVALID_REQUEST".into());
    }
    let scope = history_scope(project_id.as_deref())?;
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "GET",
                &format!("/v0/history/{kind}?{scope}cursor={cursor}&limit=30"),
                None,
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn read_research_report(
    report_id: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&report_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge
            .with_engine(|engine| engine.request("GET", &format!("/v0/reports/{report_id}"), None))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn create_conversation(state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || bridge.with_engine(|engine| engine.request("POST", "/v0/conversations", None)))
        .await.map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn conversation_turns(conversation_id: String, cursor: String, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    if !valid_job_id(&conversation_id) || cursor.len()>512 || !cursor.bytes().all(|b| b.is_ascii_alphanumeric() || b==b'-' || b==b'_') { return Err("INVALID_REQUEST".into()); }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || bridge.with_engine(|engine| engine.request("GET", &format!("/v0/conversations/{conversation_id}/turns?cursor={cursor}&limit=30"), None)))
        .await.map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn ask_question(body: Value, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("POST", "/v0/answers", Some(body)))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn create_research_plan(body: Value, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("POST", "/v0/research", Some(body)))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn run_research_plan(
    plan_id: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&plan_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request("POST", &format!("/v0/research/{plan_id}/run"), None)
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn review_evidence(
    target_id: String,
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&target_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request("POST", &format!("/v0/reviews/{target_id}"), Some(body))
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn edit_observation(
    plan_id: String,
    evidence_id: String,
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&plan_id) || !valid_job_id(&evidence_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                &format!("/v0/research/{plan_id}/observations/{evidence_id}"),
                Some(body),
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn create_research_report(
    plan_id: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&plan_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request("POST", &format!("/v0/research/{plan_id}/reports"), None)
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn export_research_report(
    report_id: String,
    app: tauri::AppHandle,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    if !valid_job_id(&report_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let root = bridge.current_root()?;
        let Some(file) = app.dialog().file().set_title("导出研究报告（创建新文件）").set_file_name("research-report.md").add_filter("Markdown", &["md"]).blocking_save_file() else {return Ok(None);};
        let path = file.into_path().map_err(|_|"EXPORT_PATH_INVALID")?;
        if !path.is_absolute() || path.ancestors().any(|part|part.is_symlink()) || path.starts_with(&root) {return Err("EXPORT_PATH_INVALID".into());}
        bridge.with_engine(|engine| {
            if bridge.current_root()? != root {return Err("WORKSPACE_CHANGED".into());}
            let report = engine.request("GET", &format!("/v0/reports/{report_id}"), None)?;
            let body = report["export_body"].as_str().or_else(||report["body"].as_str()).ok_or("ENGINE_PROTOCOL_MISMATCH")?;
            let mut stream = std::fs::OpenOptions::new().write(true).create_new(true).open(&path).map_err(|err|if err.kind()==std::io::ErrorKind::AlreadyExists {"EXPORT_EXISTS"} else {"EXPORT_WRITE_FAILED"})?;
            stream.write_all(body.as_bytes()).and_then(|_|stream.sync_all()).map_err(|_|"EXPORT_WRITE_FAILED")?;
            Ok(Some(json!({"saved":true,"label":path.file_name().and_then(|s|s.to_str()).unwrap_or("report.md")})))
        })
    }).await.map_err(|_|"ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn choose_generator_model(
    app: tauri::AppHandle,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let root = bridge.current_root()?;
        let Some(path) = app.dialog().file().set_title("选择已批准的 Qwen GGUF 候选目录").blocking_pick_folder() else {return Ok(None);};
        let path = path.into_path().map_err(|_|"DIRECTORY_NOT_ALLOWED")?;
        bridge.with_engine(|engine| {
            if bridge.current_root()? != root {return Err("WORKSPACE_CHANGED".into());}
            let grant = directory_grant(engine, path, "generator")?;
            Ok(Some(engine.request("POST", "/v0/generator", Some(json!({"model_grant_id":grant["directory_grant_id"],"idempotency_key":random_key()?})))?))
        })
    }).await.map_err(|_|"ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn choose_ocr_model(
    app: tauri::AppHandle,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let root = bridge.current_root()?;
        let Some(path) = app.dialog().file().set_title("选择已批准的 tessdata_fast eng/chi_sim 目录").blocking_pick_folder() else {return Ok(None);};
        let path = path.into_path().map_err(|_|"DIRECTORY_NOT_ALLOWED")?;
        bridge.with_engine(|engine| {
            if bridge.current_root()? != root {return Err("WORKSPACE_CHANGED".into());}
            let grant = directory_grant(engine, path, "ocr")?;
            Ok(Some(engine.request("POST", "/v0/ocr", Some(json!({"model_grant_id":grant["directory_grant_id"],"idempotency_key":random_key()?})))?))
        })
    }).await.map_err(|_|"ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn lifecycle_snapshot(state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("GET", "/v0/lifecycle", None))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn choose_docling_model(
    app: tauri::AppHandle,
    state: State<'_, Arc<Bridge>>,
) -> Result<Option<Value>, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        let root = bridge.current_root()?;
        let Some(path) = app.dialog().file().set_title("选择已批准的 Docling Heron / TableFormer 资源根目录").blocking_pick_folder() else {return Ok(None);};
        let path = path.into_path().map_err(|_|"DIRECTORY_NOT_ALLOWED")?;
        bridge.with_engine(|engine| {
            if bridge.current_root()? != root {return Err("WORKSPACE_CHANGED".into());}
            let grant = directory_grant(engine, path, "docling")?;
            Ok(Some(engine.request("POST", "/v0/docling", Some(json!({"model_grant_id":grant["directory_grant_id"],"idempotency_key":random_key()?})))?))
        })
    }).await.map_err(|_|"ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn list_document_tables(
    version_id: String,
    offset: u16,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&version_id) || offset > 200 {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "GET",
                &format!("/v0/documents/{version_id}/tables?offset={offset}"),
                None,
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn read_table_candidate(
    table_id: String,
    row_offset: u16,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&table_id) || row_offset > 1000 {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "GET",
                &format!("/v0/tables/{table_id}?row_offset={row_offset}"),
                None,
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn review_table_candidate(
    table_id: String,
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&table_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request("POST", &format!("/v0/tables/{table_id}/review"), Some(body))
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn update_document_lifecycle(
    document_id: String,
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&document_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                &format!("/v0/documents/{document_id}/lifecycle"),
                Some(body),
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn identity_snapshot(state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("GET", "/v0/document-merges", None))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn merge_document_versions(
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("POST", "/v0/document-merges", Some(body)))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn undo_document_merge(
    merge_id: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&merge_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                &format!("/v0/document-merges/{merge_id}/undo"),
                None,
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn list_annotations(
    version_id: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&version_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "GET",
                &format!("/v0/documents/{version_id}/annotations"),
                None,
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn save_annotation(
    version_id: String,
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&version_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                &format!("/v0/documents/{version_id}/annotations"),
                Some(body),
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn inspect_document_parse(
    version_id: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&version_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "GET",
                &format!("/v0/documents/{version_id}/parse-diagnostics"),
                None,
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn prepare_mvp(
    version_ids: Vec<String>,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if version_ids.is_empty()
        || version_ids.len() > 1000
        || version_ids.iter().any(|id| !valid_job_id(id))
        || version_ids
            .iter()
            .collect::<std::collections::BTreeSet<_>>()
            .len()
            != version_ids.len()
    {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                "/v0/mvp/prepare",
                Some(json!({"version_ids":version_ids,"idempotency_key":random_key()?})),
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn read_mvp_answer(
    answer_id: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&answer_id) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge
            .with_engine(|engine| engine.request("GET", &format!("/v0/answers/{answer_id}"), None))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn list_generation_providers(state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("GET", "/v0/generation-providers", None))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn save_generation_provider(
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !body.is_object() || body.to_string().len() > 16000 {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| engine.request("POST", "/v0/generation-providers", Some(body)))
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn preview_generation_provider(
    body: Value,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !body.is_object() || body.to_string().len() > 16000 {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request("POST", "/v0/generation-provider-probe", Some(body))
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn authorize_generation_provider(identifier: String, expected_revision: u64, enabled: bool, state: State<'_, Arc<Bridge>>) -> Result<Value, String> {
    if !valid_job_id(&identifier) || expected_revision==0 { return Err("INVALID_REQUEST".into()); }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || bridge.with_engine(|engine| engine.request("POST", &format!("/v0/generation-providers/{identifier}/authorization"), Some(json!({"expected_revision":expected_revision,"enabled":enabled})))))
      .await.map_err(|_| "ENGINE_TASK_FAILED")?
}

#[tauri::command]
async fn probe_generation_provider(
    identifier: String,
    state: State<'_, Arc<Bridge>>,
) -> Result<Value, String> {
    if !valid_job_id(&identifier) {
        return Err("INVALID_REQUEST".into());
    }
    let bridge = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        bridge.with_engine(|engine| {
            engine.request(
                "POST",
                &format!("/v0/generation-providers/{identifier}/probe"),
                None,
            )
        })
    })
    .await
    .map_err(|_| "ENGINE_TASK_FAILED")?
}

pub fn run() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let root = app.path().local_data_dir()?.join("RAGSystem");
            let root = if cfg!(debug_assertions) {
                std::env::var_os("RAGSYSTEM_DEV_DATA_ROOT")
                    .map(PathBuf::from)
                    .unwrap_or(root)
            } else {
                root
            };
            if !root.is_absolute() {
                return Err("INVALID_DATA_ROOT".into());
            }
            let preference = app.path().app_config_dir()?.join("workspace.json");
            let saved = std::fs::read(&preference)
                .ok()
                .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok());
            let mut warning = String::new();
            let root = if std::env::var_os("RAGSYSTEM_DEV_DATA_ROOT").is_some()
                && cfg!(debug_assertions)
            {
                root
            } else if let Some(saved) = saved {
                let candidate = saved["data_root"].as_str().map(PathBuf::from);
                if let Some(path) = candidate.filter(|path| {
                    valid_restored_root(path, saved["restore_id"].as_str().unwrap_or(""))
                }) {
                    path
                } else {
                    warning = "保存的恢复副本不可用，当前已打开默认工作区。".into();
                    root
                }
            } else {
                root
            };
            app.manage(Arc::new(Bridge {
                engine: Mutex::new(None),
                root: Mutex::new(root),
                preference,
                warning,
                recovering: AtomicBool::new(false),
                start_allowed: AtomicBool::new(true),
            }));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            preview_generation_provider,
            list_generation_providers,
            save_generation_provider,
            probe_generation_provider,
            authorize_generation_provider,
            prepare_mvp,
            read_mvp_answer,
            workspace_snapshot,
            choose_pdf_and_import,
            restart_engine,
            cancel_job,
            parse_document,
            search_sources,
            read_source,
            create_project,
            set_project_document,
            update_document_metadata,
            read_document,
            retry_job,
            list_backups,
            choose_backup_directory,
            choose_restore_directories,
            activate_restored_workspace,
            choose_embedding_model,
            workbench_snapshot,
            history_page,
            read_research_report,
            ask_question,
            create_conversation,
            conversation_turns,
            create_research_plan,
            run_research_plan,
            review_evidence,
            edit_observation,
            create_research_report,
            export_research_report,
            choose_generator_model,
            choose_ocr_model,
            choose_docling_model,
            list_document_tables,
            read_table_candidate,
            review_table_candidate,
            identity_snapshot,
            lifecycle_snapshot,
            update_document_lifecycle,
            merge_document_versions,
            undo_document_merge,
            list_annotations,
            save_annotation,
            inspect_document_parse
        ])
        .build(tauri::generate_context!())
        .expect("DESKTOP_START_FAILED");
    application.run(|app, event| {
        if let tauri::RunEvent::Exit = event {
            let bridge = app.state::<Arc<Bridge>>();
            if let Ok(mut engine) = bridge.engine.lock() {
                if let Some(mut sidecar) = engine.take() {
                    sidecar.stop();
                }
            };
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};
    fn test_bridge(root: PathBuf) -> Bridge {
        Bridge { engine: Mutex::new(None), root: Mutex::new(root.clone()), preference: root.join("test-preference.json"), warning: String::new(), recovering: AtomicBool::new(false), start_allowed: AtomicBool::new(true) }
    }

    #[test]
    fn recovery_preserves_live_process_replaces_crashed_process_and_data() {
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).ancestors().nth(3).unwrap().join(".tools/test-data").join(format!("recovery-中文 空格-{stamp}"));
        let bridge = test_bridge(root);
        bridge.with_engine(|engine| engine.request("POST", "/v0/projects", Some(json!({"name":"Recovery persistence"})))).unwrap();
        let (pid, base, token) = bridge.engine.lock().unwrap().as_ref().unwrap().test_identity();
        bridge.recover_engine(false).unwrap();
        bridge.engine.lock().unwrap().as_mut().unwrap().test_set_base("http://127.0.0.1:1".into());
        assert_eq!(bridge.recover_engine(false).unwrap_err(), "ENGINE_HEALTH_FAILED");
        bridge.engine.lock().unwrap().as_mut().unwrap().test_set_base(base.clone());
        assert_eq!(pid, bridge.engine.lock().unwrap().as_ref().unwrap().test_identity().0);
        bridge.recovering.store(true, Ordering::SeqCst);
        assert_eq!(bridge.recover_engine(false).unwrap_err(), "ENGINE_RECOVERING");
        bridge.recovering.store(false, Ordering::SeqCst);
        bridge.engine.lock().unwrap().as_mut().unwrap().test_crash();
        assert_eq!(bridge.with_engine(|_| Ok(())).unwrap_err(), "ENGINE_EXITED");
        bridge.recover_engine(false).unwrap();
        let (_, next_base, _) = bridge.engine.lock().unwrap().as_ref().unwrap().test_identity();
        let response = reqwest::blocking::Client::builder().no_proxy().build().unwrap().get(format!("{next_base}/v0/health")).header("X-RAG-Session", token).send().unwrap();
        assert_eq!(response.status(), reqwest::StatusCode::UNAUTHORIZED);
        let projects = bridge.with_engine(|engine| engine.request("GET", "/v0/projects", None)).unwrap();
        assert!(projects["projects"].as_array().unwrap().iter().any(|row| row["name"] == "Recovery persistence"));
        assert!(!base.is_empty());
        bridge.recover_engine(false).unwrap();
        bridge.engine.lock().unwrap().take().unwrap().stop();
    }

    #[test]
    fn recovery_start_failure_is_retryable_without_rebuilding_database() {
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root = std::env::temp_dir().join(format!("ragsystem-start-failure-{stamp}"));
        std::fs::create_dir(&root).unwrap();
        let blocked = root.join("blocked"); std::fs::write(&blocked, b"keep").unwrap();
        let bridge = test_bridge(blocked.clone());
        assert!(bridge.recover_engine(false).is_err());
        assert!(bridge.engine.lock().unwrap().is_none());
        assert!(!bridge.start_allowed.load(Ordering::SeqCst));
        assert_eq!(std::fs::read(&blocked).unwrap(), b"keep");
        *bridge.root.lock().unwrap() = root.join("new-test-workspace");
        bridge.recover_engine(false).unwrap();
        bridge.engine.lock().unwrap().take().unwrap().stop();
    }

    #[test]
    fn batch_import_failure_revokes_only_grants_returned_for_this_selection() {
        let mut calls = Vec::new();
        let result = import_selected_paths(vec![PathBuf::from("/test/a.pdf"), PathBuf::from("/test/b.pdf")], None, |path, body| {
            calls.push((path.to_string(), body.clone()));
            match path {
                "/v0/internal/file-grants/batch" => Ok(json!({"grants":[{"file_grant_id":"first"},{"file_grant_id":"second"}]})),
                "/v0/import-batches" => Err("WORKER_BUSY".into()),
                "/v0/internal/file-grants/revoke" => Ok(json!({"revoked":2})),
                _ => panic!("unexpected endpoint"),
            }
        });
        assert_eq!(result.unwrap_err(), "WORKER_BUSY");
        assert_eq!(calls.len(), 3);
        assert_eq!(calls[2].1["file_grant_ids"], json!(["first", "second"]));
        let mut calls = 0;
        let failed = import_selected_paths(vec![PathBuf::from("/test/a.pdf")], None, |_, _| {calls += 1; Err("NOT_PDF".into())});
        assert_eq!(failed.unwrap_err(), "NOT_PDF");
        assert_eq!(calls, 1);
    }

    #[test]
    fn rejects_route_injection() {
        assert!(valid_job_id("12345678-1234-4321-1234-123456789abc"));
        assert!(!valid_job_id("../../health"));
        assert!(!valid_job_id("12345678-1234-4321-1234-123456789ab/"));
    }

    #[test]
    fn reader_rejects_path_injection_and_tampered_original() {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
            .unwrap()
            .join(".tools/test-data")
            .join(format!("rust-reader-{stamp}"));
        std::fs::create_dir_all(root.join("papers")).unwrap();
        let bytes = b"%PDF-1.4 synthetic hash boundary fixture";
        let hash = format!("{:x}", Sha256::digest(bytes));
        let path = root.join("papers").join(format!("{hash}.pdf"));
        std::fs::write(&path, bytes).unwrap();
        assert_eq!(verified_pdf_bytes(&root, &hash).unwrap(), bytes);
        assert_eq!(
            verified_pdf_bytes(&root, "../../private").unwrap_err(),
            "ENGINE_PROTOCOL_MISMATCH"
        );
        std::fs::write(&path, b"modified fixture").unwrap();
        assert_eq!(
            verified_pdf_bytes(&root, &hash).unwrap_err(),
            "OBJECT_CORRUPT"
        );
    }
}
