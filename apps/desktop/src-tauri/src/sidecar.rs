use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

const PROTOCOL: &str = "0.1.0";

#[derive(Deserialize)]
struct Handshake {
    protocol_version: String,
    port: u16,
}

pub struct Sidecar {
    child: Child,
    input: Option<ChildStdin>,
    base: String,
    token: String,
    client: Client,
}

fn executable_path() -> Result<PathBuf, String> {
    #[cfg(test)]
    if let Some(path) = std::env::var_os("RAGSYSTEM_TEST_SIDECAR") {
        let path = PathBuf::from(path);
        if path.is_absolute() && path.is_file() {return Ok(path);}
        return Err("SIDECAR_NOT_PACKAGED".into());
    }
    let extension = if cfg!(windows) { ".exe" } else { "" };
    let packaged = std::env::current_exe()
        .map_err(|_| "ENGINE_START_FAILED")?
        .parent()
        .ok_or("ENGINE_START_FAILED")?
        .join(format!("ragsystem-engine{extension}"));
    if packaged.is_file() {
        return Ok(packaged);
    }
    let path = if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("binaries")
            .join(format!(
                "ragsystem-engine-{}{}",
                env!("RAGSYSTEM_HOST"),
                extension
            ))
    } else {
        packaged
    };
    if !path.is_file() {
        return Err("SIDECAR_NOT_PACKAGED".into());
    }
    Ok(path)
}

impl Sidecar {
    pub fn is_running(&mut self) -> Result<bool, String> {
        self.child.try_wait().map(|status| status.is_none()).map_err(|_| "ENGINE_PROCESS_STATUS_FAILED".into())
    }

    #[cfg(test)]
    pub fn test_identity(&self) -> (u32, String, String) {
        (self.child.id(), self.base.clone(), self.token.clone())
    }

    #[cfg(test)]
    pub fn test_crash(&mut self) {
        self.child.kill().unwrap();
        self.child.wait().unwrap();
    }

    #[cfg(test)]
    pub fn test_set_base(&mut self, base: String) { self.base = base; }

    pub fn start(root: &Path) -> Result<Self, String> {
        std::fs::create_dir_all(root.join("logs")).map_err(|_| "DATA_ROOT_UNAVAILABLE")?;
        let mut entropy = [0u8; 32];
        getrandom::fill(&mut entropy).map_err(|_| "ENTROPY_UNAVAILABLE")?;
        let token: String = entropy.iter().map(|b| format!("{b:02x}")).collect();
        let client = Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            // The sidecar uses a short keep-alive timeout; fresh local sockets
            // avoid reusing an idle connection while a native import yields.
            .pool_max_idle_per_host(0)
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|_| "ENGINE_START_FAILED")?;
        let mut command = Command::new(executable_path()?);
        command.env_clear();
        for name in [
            "PATH",
            "HOME",
            "TMPDIR",
            "TEMP",
            "TMP",
            "SYSTEMROOT",
            "WINDIR",
            "LOCALAPPDATA",
            "APPDATA",
            "USERPROFILE",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
        ] {
            if let Some(value) = std::env::var_os(name) {
                command.env(name, value);
            }
        }
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        let mut child = command.spawn().map_err(|_| "ENGINE_START_FAILED")?;
        let mut input = child.stdin.take().ok_or("ENGINE_START_FAILED")?;
        let stdout = child.stdout.take().ok_or("ENGINE_START_FAILED")?;
        let stderr = child.stderr.take().ok_or("ENGINE_START_FAILED")?;
        let log_root = root.join("logs");
        // Persist only well-formed stable startup codes. Never persist arbitrary
        // parser traces, broker paths, source text or process stdin.
        thread::spawn(move || {
            for text in BufReader::new(stderr)
                .lines()
                .map_while(Result::ok)
                .take(32)
            {
                if let Ok(value) = serde_json::from_str::<Value>(&text) {
                    if let Some(code) = value.get("code").and_then(Value::as_str) {
                        if !code.is_empty()
                            && code.len() < 80
                            && code.bytes().all(|c| c.is_ascii_uppercase() || c == b'_')
                        {
                            if let Ok(mut log) = std::fs::OpenOptions::new()
                                .create(true)
                                .append(true)
                                .open(log_root.join("sidecar-startup.log"))
                            {
                                let _ = writeln!(log, "{code}");
                            }
                        }
                    }
                }
            }
        });
        let startup = json!({"protocol_version":PROTOCOL,"token":token,"data_root":root});
        let write_result = writeln!(input, "{}", startup).and_then(|_| input.flush());
        if write_result.is_err() {
            let _ = child.kill();
            let _ = child.wait();
            return Err("ENGINE_START_FAILED".into());
        }
        let (send, receive) = mpsc::channel();
        thread::spawn(move || {
            let mut line = String::new();
            let result = BufReader::new(stdout).take(4096).read_line(&mut line);
            let _ = send.send(result.map(|_| line));
        });
        let handshake = receive
            .recv_timeout(Duration::from_secs(15))
            .ok()
            .and_then(Result::ok)
            .and_then(|line| serde_json::from_str::<Handshake>(&line).ok());
        let Some(handshake) = handshake else {
            let _ = child.kill();
            let _ = child.wait();
            return Err("ENGINE_START_FAILED".into());
        };
        if handshake.protocol_version != PROTOCOL || handshake.port == 0 {
            let _ = child.kill();
            let _ = child.wait();
            return Err("ENGINE_PROTOCOL_MISMATCH".into());
        }
        let mut sidecar = Self {
            child,
            input: Some(input),
            base: format!("http://127.0.0.1:{}", handshake.port),
            token,
            client,
        };
        let started = Instant::now();
        loop {
            if sidecar.request("GET", "/v0/health", None).is_ok() {
                break;
            }
            if started.elapsed() > Duration::from_secs(15)
                || sidecar.child.try_wait().ok().flatten().is_some()
            {
                sidecar.stop();
                return Err("ENGINE_START_FAILED".into());
            }
            thread::sleep(Duration::from_millis(100));
        }
        Ok(sidecar)
    }

    pub fn request(&self, method: &str, path: &str, body: Option<Value>) -> Result<Value, String> {
        let url = format!("{}{}", self.base, path);
        let mut request = match method {
            "GET" => self.client.get(url),
            "POST" => self.client.post(url),
            _ => return Err("METHOD_NOT_ALLOWED".into()),
        }
        .header("X-RAG-Session", &self.token);
        if let Some(body) = body {
            request = request.json(&body);
        }
        let response = request.send().map_err(|error| {
            if error.is_timeout() {
                "ENGINE_TIMEOUT"
            } else {
                "ENGINE_UNAVAILABLE"
            }
        })?;
        let status = response.status();
        let value: Value = response.json().map_err(|_| "ENGINE_PROTOCOL_MISMATCH")?;
        if !status.is_success() {
            let code = value
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or("ENGINE_REQUEST_FAILED");
            if code.len() > 80 || !code.bytes().all(|b| b.is_ascii_uppercase() || b == b'_') {
                return Err("ENGINE_REQUEST_FAILED".into());
            }
            return Err(code.into());
        }
        Ok(value)
    }

    pub fn stop(&mut self) {
        // Close broker stdin first: Python observes EOF and gracefully stops.
        self.input.take();
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(7) {
            if self.child.try_wait().ok().flatten().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn actual_frozen_sidecar_health_and_eof() {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
            .unwrap()
            .join(".tools/test-data")
            .join(format!("rust-中文 空格-{stamp}"));
        let mut engine = Sidecar::start(&root).expect("actual bundled sidecar must start");
        let health = engine.request("GET", "/v0/health", None).unwrap();
        assert_eq!(health["components"]["engine"]["available"], true);
        assert_eq!(health["components"]["database"]["available"], true);
        assert_eq!(health["status"], "degraded"); // No model/index configured in the new workspace.
        assert_eq!(health["schema_version"], health["components"]["database"]["schema_version"].to_string());
        assert!(!health.to_string().contains(&engine.token));
        assert!(
            engine
                .client
                .get(format!("{}/v0/health", engine.base))
                .send()
                .unwrap()
                .status()
                == 401
        );
        engine.stop();
        assert!(engine.child.try_wait().unwrap().is_some());
    }

    #[test]
    #[ignore = "requires the explicitly approved local E5 directory and full frozen sidecar"]
    fn actual_frozen_candidate_indexes_through_rust_transport() {
        let model =
            std::env::var("RAGSYSTEM_MODEL_DIR").expect("approved local model path required");
        let project = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
            .unwrap()
            .to_path_buf();
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = project
            .join(".tools/test-data")
            .join(format!("rust-indexes-中文 空格-{stamp}"));
        let mut engine = Sidecar::start(&root).unwrap();
        fn wait_job(engine: &Sidecar, identifier: &str) {
            let started = Instant::now();
            loop {
                let requested = Instant::now();
                let job = engine
                    .request("GET", &format!("/v0/jobs/{identifier}"), None)
                    .unwrap();
                if requested.elapsed() > Duration::from_secs(3) {
                    println!(
                        "Cold candidate status request: {} ms",
                        requested.elapsed().as_millis()
                    );
                }
                if job["status"] != "running" && job["status"] != "queued" {
                    assert_eq!(job["status"], "completed", "job failed: {job}");
                    return;
                }
                assert!(started.elapsed() < Duration::from_secs(120));
                thread::sleep(Duration::from_millis(100));
            }
        }
        let pdf = project
            .join("tests/fixtures/public/N19-1423.pdf")
            .canonicalize()
            .unwrap();
        let grant = engine
            .request(
                "POST",
                "/v0/internal/file-grants",
                Some(json!({"path":pdf})),
            )
            .unwrap();
        let imported = engine
            .request(
                "POST",
                "/v0/imports",
                Some(json!({"file_grant_id":grant["file_grant_id"],"idempotency_key":"import"})),
            )
            .unwrap();
        wait_job(&engine, imported["job_id"].as_str().unwrap());
        let docs = engine.request("GET", "/v0/documents", None).unwrap();
        let version = docs["documents"][0]["doc_version_id"].as_str().unwrap();
        let parsed = engine
            .request(
                "POST",
                &format!("/v0/documents/{version}/parse"),
                Some(json!({"idempotency_key":"parse"})),
            )
            .unwrap();
        wait_job(&engine, parsed["job_id"].as_str().unwrap());
        for backend in ["sqlite-vec", "lancedb"] {
            let grant = engine
                .request(
                    "POST",
                    "/v0/internal/directory-grants",
                    Some(json!({"path":model,"purpose":"embedding"})),
                )
                .unwrap();
            let indexed = engine.request("POST", "/v0/index", Some(json!({"backend":backend,"model_grant_id":grant["directory_grant_id"],"idempotency_key":backend}))).unwrap();
            wait_job(&engine, indexed["job_id"].as_str().unwrap());
            let result = engine.request("POST", "/v0/search", Some(json!({"query":"BERT pre-training tasks","strategy":"hybrid","authorized_doc_version_ids":[version],"k":5}))).unwrap();
            let hits = result["results"].as_array().unwrap();
            assert!(!hits.is_empty());
            for hit in hits {
                let id = hit["source_anchor_id"].as_str().unwrap();
                let anchor = engine
                    .request("GET", &format!("/v0/source-anchors/{id}"), None)
                    .unwrap();
                assert_eq!(anchor["doc_version_id"], version);
                assert_eq!(anchor["location_level"], "page_only");
            }
        }
        engine.stop();
        assert!(engine.child.try_wait().unwrap().is_some());
    }
    #[test]
    #[ignore = "requires explicitly approved OCR directory and locally derived scan fixture"]
    fn actual_frozen_ocr_through_rust_transport() {
        let model =
            std::env::var("RAGSYSTEM_OCR_MODEL_DIR").expect("approved OCR directory required");
        let scan = std::env::var("RAGSYSTEM_OCR_SCAN_PDF").expect("derived licensed scan required");
        let project = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
            .unwrap()
            .to_path_buf();
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = project
            .join(".tools/test-data")
            .join(format!("rust-ocr-中文 空格-{stamp}"));
        let mut engine = Sidecar::start(&root).unwrap();
        fn wait(engine: &Sidecar, id: &str) {
            let started = Instant::now();
            loop {
                let job = engine
                    .request("GET", &format!("/v0/jobs/{id}"), None)
                    .unwrap();
                if job["status"] != "running" && job["status"] != "queued" {
                    assert_eq!(job["status"], "completed", "{job}");
                    return;
                }
                assert!(started.elapsed() < Duration::from_secs(120));
                thread::sleep(Duration::from_millis(100));
            }
        }
        let grant = engine
            .request(
                "POST",
                "/v0/internal/file-grants",
                Some(json!({"path":scan})),
            )
            .unwrap();
        let imported = engine
            .request(
                "POST",
                "/v0/imports",
                Some(json!({"file_grant_id":grant["file_grant_id"],"idempotency_key":"scan"})),
            )
            .unwrap();
        wait(&engine, imported["job_id"].as_str().unwrap());
        let docs = engine.request("GET", "/v0/documents", None).unwrap();
        let version = docs["documents"][0]["doc_version_id"].as_str().unwrap();
        let grant = engine
            .request(
                "POST",
                "/v0/internal/directory-grants",
                Some(json!({"path":model,"purpose":"ocr"})),
            )
            .unwrap();
        let loaded=engine.request("POST","/v0/ocr",Some(json!({"model_grant_id":grant["directory_grant_id"],"idempotency_key":"configure"}))).unwrap();
        wait(&engine, loaded["job_id"].as_str().unwrap());
        let parsed = engine
            .request(
                "POST",
                &format!("/v0/documents/{version}/parse"),
                Some(json!({"idempotency_key":"ocr","use_ocr":true})),
            )
            .unwrap();
        wait(&engine, parsed["job_id"].as_str().unwrap());
        let diagnostics = engine
            .request(
                "GET",
                &format!("/v0/documents/{version}/parse-diagnostics"),
                None,
            )
            .unwrap();
        assert_eq!(
            diagnostics["pages"][0]["quality"],
            "ocr_extracted_unreviewed"
        );
        let hits=engine.request("POST","/v0/search",Some(json!({"query":"BERT","authorized_doc_version_ids":[version],"strategy":"keyword","k":5}))).unwrap();
        let id = hits["results"][0]["source_anchor_id"].as_str().unwrap();
        let anchor = engine
            .request("GET", &format!("/v0/source-anchors/{id}"), None)
            .unwrap();
        assert_eq!(anchor["location_level"], "page_only");
        assert!(anchor["bbox_norm"].is_null());
        assert!(anchor["reason_if_degraded"]
            .as_str()
            .unwrap()
            .starts_with("OCR_"));
        engine.stop();
        assert!(engine.child.try_wait().unwrap().is_some());
    }

    #[test]
    #[ignore = "requires the explicitly approved Docling candidate directory and full frozen sidecar"]
    fn actual_frozen_docling_through_rust_transport() {
        let model = std::env::var("RAGSYSTEM_DOCLING_MODEL_DIR")
            .expect("approved Docling directory required");
        let project = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
            .unwrap()
            .to_path_buf();
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = project
            .join(".tools/test-data")
            .join(format!("rust-docling-中文 空格-{stamp}"));
        let mut engine = Sidecar::start(&root).unwrap();
        fn wait(engine: &Sidecar, id: &str) {
            let started = Instant::now();
            loop {
                let job = engine
                    .request("GET", &format!("/v0/jobs/{id}"), None)
                    .unwrap();
                if job["status"] != "running" && job["status"] != "queued" {
                    assert_eq!(job["status"], "completed", "{job}");
                    return;
                }
                assert!(started.elapsed() < Duration::from_secs(180));
                thread::sleep(Duration::from_millis(150));
            }
        }
        let grant = engine
            .request(
                "POST",
                "/v0/internal/file-grants",
                Some(json!({"path":project.join("tests/fixtures/public/N19-1423.pdf")})),
            )
            .unwrap();
        let imported = engine
            .request(
                "POST",
                "/v0/imports",
                Some(json!({"file_grant_id":grant["file_grant_id"],"idempotency_key":"bert"})),
            )
            .unwrap();
        wait(&engine, imported["job_id"].as_str().unwrap());
        let docs = engine.request("GET", "/v0/documents", None).unwrap();
        let version = docs["documents"][0]["doc_version_id"].as_str().unwrap();
        let grant = engine
            .request(
                "POST",
                "/v0/internal/directory-grants",
                Some(json!({"path":model,"purpose":"docling"})),
            )
            .unwrap();
        let loaded = engine.request("POST", "/v0/docling", Some(json!({"model_grant_id":grant["directory_grant_id"],"idempotency_key":"configure"}))).unwrap();
        wait(&engine, loaded["job_id"].as_str().unwrap());
        let parsed = engine
            .request(
                "POST",
                &format!("/v0/documents/{version}/parse"),
                Some(json!({"idempotency_key":"layout","use_docling":true})),
            )
            .unwrap();
        wait(&engine, parsed["job_id"].as_str().unwrap());
        let tables = engine
            .request("GET", &format!("/v0/documents/{version}/tables"), None)
            .unwrap();
        assert!(tables["total"].as_u64().unwrap() > 0);
        let id = tables["tables"][0]["id"].as_str().unwrap();
        let table = engine
            .request("GET", &format!("/v0/tables/{id}"), None)
            .unwrap();
        assert_eq!(table["review"]["status"], "unreviewed");
        assert_eq!(table["location_level"], "page_only");
        assert!(!table["cells"].as_array().unwrap().is_empty());
        let review = engine.request("POST", &format!("/v0/tables/{id}/review"), Some(json!({"expected_revision":0,"status":"uncertain","note":"Rust integration; not scientific validation"}))).unwrap();
        assert_eq!(review["review"]["revision"], 1);
        // Change a different original page through the actual Rust HTTP client.
        let parsed = engine.request("POST", &format!("/v0/documents/{version}/parse"), Some(json!({"idempotency_key":"automatic-page8","auto_enhance":true,"page_numbers":[8]}))).unwrap();
        wait(&engine, parsed["job_id"].as_str().unwrap());
        let preserved = engine
            .request("GET", &format!("/v0/tables/{id}"), None)
            .unwrap();
        assert_eq!(preserved, review);
        let diagnostics = engine
            .request(
                "GET",
                &format!("/v0/documents/{version}/parse-diagnostics"),
                None,
            )
            .unwrap();
        assert_eq!(diagnostics["pages"].as_array().unwrap().len(), 16);
        assert_eq!(diagnostics["runs"][0]["page_count"], 1);
        assert_eq!(diagnostics["runs"][0]["routing"][0]["method"], "docling");
        engine.stop();
        assert!(engine.child.try_wait().unwrap().is_some());
    }
}
