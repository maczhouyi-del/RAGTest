"""Explicitly approved offline OCR candidate; no downloads or system binaries."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.directories import directory_identity
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.process import run_worker
from ragsystem.storage.database import utc_now

REVISION = "65727574dfcd264acbb0c3e07860e4e9e9b22185"
WEIGHTS = {
    "eng.traineddata": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
    "chi_sim.traineddata": "a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730",
}
POLICY = {
    "model": "tesseract-ocr/tessdata_fast",
    "revision": REVISION,
    "weight_sha256": WEIGHTS,
    "languages": "eng+chi_sim",
    "oem": "LSTM_ONLY",
    "psm": "AUTO_NO_OSD",
    "render_dpi": 200,
    "max_render_pixels": 8000000,
    "max_ocr_pages": 40,
    "min_native_nonspace_chars": 24,
    "min_mean_confidence": 60,
    "preprocessing": "pdfium-gray-white-background-v1",
    "location_level": "page_only",
    "pipeline_version": "offline-ocr-candidate-v1",
}


def verify_directory(directory):
    path = Path(directory)
    directory_identity(path)
    for name, expected in WEIGHTS.items():
        file = path / name
        if file.is_symlink() or not file.is_file() or file.stat().st_size > 16 * 1024 * 1024:
            raise EngineError("OCR_MODEL_NOT_AVAILABLE")
        with file.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise EngineError("OCR_MODEL_HASH_MISMATCH")
    return path


def native_api(directory):
    directory = verify_directory(directory)
    try:
        import tesserocr
    except (ImportError, OSError) as exc:
        raise EngineError("OCR_RUNTIME_NOT_PACKAGED") from exc
    fingerprint = {
        **POLICY,
        "runtime": "tesserocr",
        "runtime_version": importlib.metadata.version("tesserocr"),
        "native_version": tesserocr.tesseract_version(),
    }
    api = tesserocr.PyTessBaseAPI(
        path=str(directory) + "/",
        lang=POLICY["languages"],
        oem=tesserocr.OEM.LSTM_ONLY,
        psm=tesserocr.PSM.AUTO,
        variables={"debug_file": "", "user_defined_dpi": "200"},
    )
    return api, fingerprint


def recognize(page, api):
    scale = POLICY["render_dpi"] / 72
    width, height = page.get_size()
    if width <= 0 or height <= 0 or width * height * scale * scale > POLICY["max_render_pixels"]:
        return "", "OCR_PIXEL_LIMIT", None
    bitmap = page.render(scale=scale, grayscale=True, fill_color=(255, 255, 255, 255))
    try:
        # Keep immutable bytes alive until recognition finishes (native API does not copy).
        data = bytes(bitmap.buffer)
        api.SetImageBytes(data, bitmap.width, bitmap.height, 1, bitmap.stride)
        text = api.GetUTF8Text()
        confidence = api.MeanTextConf()
        if len(text) > 50000:
            return "", "PAGE_TEXT_LIMIT", confidence
        return text, None if text.strip() else "OCR_NO_TEXT", confidence
    finally:
        api.Clear()
        bitmap.close()


class OcrService:
    def __init__(self, db):
        self.db = db

    def status(self):
        with self.db.connection() as conn:
            row = conn.execute("SELECT value_json FROM app_settings WHERE key='ocr'").fetchone()
        config = json.loads(row[0]) if row else None
        return {
            "configured": bool(config),
            "fingerprint": config["fingerprint"] if config else None,
            "candidate_only": True,
        }

    def require(self):
        with self.db.connection() as conn:
            row = conn.execute("SELECT value_json FROM app_settings WHERE key='ocr'").fetchone()
        if not row:
            raise EngineError("OCR_NOT_CONFIGURED")
        config = json.loads(row[0])
        verify_directory(config["directory"])
        return config

    def configure(self, grant, job):
        grant.check()
        verify_directory(grant.path)
        jobs = Jobs(self.db)

        def check():
            with self.db.connection() as conn:
                jobs.require_lease(conn, job["id"], job["lease_token"])

        result = run_worker(
            {"operation": "ocr_probe", "ocr_directory": str(grant.path)},
            check=check,
            log_directory=self.db.path.parent / "parse-worker-logs",
        )
        grant.check()
        config = {"directory": str(grant.path), "fingerprint": result["ocr_fingerprint"]}
        with self.db.transaction() as conn:
            jobs.require_lease(conn, job["id"], job["lease_token"])
            conn.execute(
                "INSERT INTO app_settings VALUES('ocr',?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (json.dumps(config), utc_now()),
            )
            jobs.complete(job["id"], job["lease_token"], "ocr:approved-candidate", connection=conn)
        return self.status()
