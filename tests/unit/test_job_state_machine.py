import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.jobs.repository import Jobs
from ragsystem.storage.database import Database


@pytest.fixture
def jobs(tmp_path):
    return Jobs(Database(tmp_path / "数据 空格" / "research.db"))


def test_payload_conflict_and_idempotency(jobs):
    first = jobs.enqueue("import", "once", {"grant": "a"})
    assert jobs.enqueue("import", "once", {"grant": "a"})["id"] == first["id"]
    with pytest.raises(EngineError, match="IDEMPOTENCY_CONFLICT"):
        jobs.enqueue("import", "once", {"grant": "different"})


def test_expired_worker_cannot_publish(jobs):
    job = jobs.enqueue("import", "lease", {})
    old = jobs.claim(job["id"], now=100, lease_seconds=10)
    assert old["attempt_count"] == 1
    assert jobs.recover_expired(now=111) == 1
    new = jobs.claim(job["id"], now=112, lease_seconds=10)
    with pytest.raises(EngineError, match="LEASE_LOST"):
        jobs.complete(job["id"], old["lease_token"], "result:old", now=113)
    jobs.complete(job["id"], new["lease_token"], "result:new", now=113)
    assert jobs.get(job["id"])["result_ref"] == "result:new"


def test_cancel_revokes_publication(jobs):
    job = jobs.enqueue("import", "cancel", {})
    claimed = jobs.claim(job["id"], now=100)
    jobs.cancel(job["id"])
    with pytest.raises(EngineError, match="LEASE_LOST"):
        jobs.complete(job["id"], claimed["lease_token"], "bad", now=101)
    assert jobs.get(job["id"])["status"] == "cancelled"


def test_attempt_limit_and_empty_result(jobs):
    job = jobs.enqueue("import", "limit", {}, max_attempts=1)
    claimed = jobs.claim(job["id"], now=100, lease_seconds=1)
    with pytest.raises(EngineError, match="INVALID_RESULT"):
        jobs.complete(job["id"], claimed["lease_token"], "", now=100)
    jobs.recover_expired(now=102)
    assert jobs.get(job["id"])["status"] == "failed"
    assert jobs.claim(job["id"], now=103) is None


def test_only_one_concurrent_claim(jobs):
    from concurrent.futures import ThreadPoolExecutor

    job = jobs.enqueue("import", "concurrent", {})
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: jobs.claim(job["id"]), range(4)))
    assert sum(c is not None for c in claims) == 1
