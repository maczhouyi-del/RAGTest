import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.jobs.repository import Jobs
from ragsystem.storage.database import Database


def test_actual_process_kill_after_file_publish_recovers_without_source(tmp_path):
    # All inputs are synthetic fault-test data in a dedicated test directory.
    root = tmp_path / "store"
    source = tmp_path / "crash.pdf"
    marker = tmp_path / "published.json"
    source.write_bytes(b"%PDF-1.4\nsynthetic crash recovery fixture\n%%EOF")
    script = """
import sys,json,time
from pathlib import Path
from ragsystem.storage.database import Database
from ragsystem.ingestion.import_pdf import PdfImporter
root,source,marker=map(Path,sys.argv[1:])
db=Database(root/'data/research.db')
def fault(stage):
    if stage=='file_published':
        marker.write_text(json.dumps({'stage':stage}))
        while True:time.sleep(.1)
PdfImporter(db,root).import_path_for_test(source,'crash-key',fault=fault)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "engine")
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(root), str(source), str(marker)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.is_file():
            assert child.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert json.loads(marker.read_text())["stage"] == "file_published"
    finally:
        child.kill()
        child.wait(timeout=5)
    db = Database(root / "data/research.db")
    jobs = Jobs(db)
    job = jobs.find_key("import", "crash-key")
    assert job["status"] == "running"
    # Simulate elapsed lease time after the old process is confirmed dead.
    jobs.recover_expired(now=job["lease_until"] + 1)
    importer = PdfImporter(db, root)
    assert importer.recover_published_imports() == 1
    assert len(importer.list_documents()) == 1
    assert importer.list_documents()[0]["title"] == "crash.pdf"
    assert jobs.get(job["id"])["status"] == "completed"
    assert db.integrity()["foreign_key_check"] == []
