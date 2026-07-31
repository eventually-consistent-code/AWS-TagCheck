"""
Purpose: Tests for the storage web app — target CRUD, scan trigger with
overlap messaging, htmx progress fragment (done trigger on terminal
states), and cooperative cancel. Inline FakeScheduler; no sleeps.
Author(s): John Reed
"""

import datetime

from fastapi.testclient import TestClient

from tagmanager.config import Settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import StorageJob, StorageTarget
from tagmanager.storage.base import StorageObject
from tagmanager.storage.pricing import BYTES_PER_GB

NOW = datetime.datetime.now(datetime.timezone.utc)


class FakeScheduler:
    """add_job runs the worker inline."""

    def __init__(self, run_inline=True):
        self.run_inline = run_inline

    def add_job(self, func, args=(), kwargs=None, **_meta):
        if self.run_inline:
            func(*args, **(kwargs or {}))


def _client(tmp_path, scheduler=None):
    from tagmanager.app.main import create_app  # pylint: disable=import-outside-toplevel
    engine = get_engine(f"sqlite:///{tmp_path / 'web.db'}")
    create_all(engine)
    maker = session_factory(engine)
    client = TestClient(create_app(Settings(auth_mode="none"), maker,
                                   scheduler=scheduler))
    return client, maker


def test_target_crud_roundtrip(tmp_path):
    """Add via form, list, edit, disable."""
    client, maker = _client(tmp_path)

    page = client.post("/storage/targets", data={
        "display_name": "lake", "backend": "s3",
        "buckets": "bkt-one\nbkt-two", "age_bands": "90,365"},
        follow_redirects=True)
    assert page.status_code == 200
    assert "target added." in page.text
    assert "bkt-one, bkt-two" in page.text

    session = maker()
    target = session.query(StorageTarget).one()
    assert target.buckets == ["bkt-one", "bkt-two"]
    assert target.age_band_days == [90, 365]
    target_id = target.id
    session.close()

    page = client.post(f"/storage/targets/{target_id}", data={
        "display_name": "lake", "backend": "s3", "buckets": "bkt-one",
        "age_bands": "30"}, follow_redirects=True)
    assert "target updated." in page.text
    session = maker()
    target = session.get(StorageTarget, target_id)
    assert target.age_band_days == [30]
    assert target.enabled is False  # checkbox absent -> disabled
    session.close()

    page = client.post("/storage/targets", data={
        "backend": "s3", "buckets": "b", "age_bands": "banana"},
        follow_redirects=True)
    assert "bad age bands" in page.text


def test_scan_trigger_runs_job_and_overlap_message(tmp_path):
    """Trigger runs inline to done; a queued job yields the overlap
    message instead of a second job."""

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="a/x", size_bytes=BYTES_PER_GB,
                                last_modified=NOW)

        def capabilities(self):
            raise NotImplementedError

    # Inline scheduler needs a provider injection path the web trigger
    # doesn't expose — monkeypatch make_provider at the services layer.
    import tagmanager.storage.services as services  # pylint: disable=import-outside-toplevel
    original = services.make_provider
    services.make_provider = lambda backend, account_url="": _Provider()
    try:
        client, maker = _client(tmp_path, scheduler=FakeScheduler())
        client.post("/storage/targets", data={"backend": "s3",
                                              "buckets": "bkt"})
        page = client.post("/storage/targets/1/scan", follow_redirects=True)
        assert "scan started (job 1)." in page.text

        session = maker()
        job = session.get(StorageJob, 1)
        assert job.state == "done"
        session.close()
    finally:
        services.make_provider = original

    # Overlap: idle scheduler leaves job queued; second trigger refused.
    (tmp_path / "b").mkdir()
    client, maker = _client(tmp_path / "b",
                            scheduler=FakeScheduler(run_inline=False))
    client.post("/storage/targets", data={"backend": "s3", "buckets": "bkt"})
    client.post("/storage/targets/1/scan")
    page = client.post("/storage/targets/1/scan", follow_redirects=True)
    assert "already queued or running" in page.text


def test_scan_trigger_without_scheduler(tmp_path):
    """No scheduler wired -> honest message, no crash."""
    client, _ = _client(tmp_path)
    client.post("/storage/targets", data={"backend": "s3", "buckets": "b"})
    page = client.post("/storage/targets/1/scan", follow_redirects=True)
    assert "no scheduler in this deployment" in page.text


def test_progress_fragment_and_done_trigger(tmp_path):
    """Active jobs poll plain; terminal states carry HX-Trigger: done."""
    client, maker = _client(tmp_path)
    client.post("/storage/targets", data={"backend": "s3", "buckets": "b"})
    session = maker()
    session.add(StorageJob(target_id=1, state="running", objects_seen=42))
    session.commit()
    session.close()

    frag = client.get("/storage/jobs/1/progress")
    assert frag.status_code == 200
    assert "42 objects" in frag.text
    assert "HX-Trigger" not in frag.headers

    session = maker()
    job = session.get(StorageJob, 1)
    job.state = "done"
    session.commit()
    session.close()

    frag = client.get("/storage/jobs/1/progress")
    assert frag.headers.get("HX-Trigger") == "done"

    gone = client.get("/storage/jobs/999/progress")
    assert gone.headers.get("HX-Trigger") == "done"


def test_cancel_flow_and_jobs_page(tmp_path):
    """Cancel flips the flag with the boundary notice; jobs page renders."""
    client, maker = _client(tmp_path)
    client.post("/storage/targets", data={"display_name": "lake",
                                          "backend": "s3", "buckets": "b"})
    session = maker()
    session.add(StorageJob(target_id=1, state="running"))
    session.commit()
    session.close()

    page = client.post("/storage/jobs/1/cancel", follow_redirects=True)
    assert "cancelling at the next batch boundary" in page.text
    session = maker()
    assert session.get(StorageJob, 1).cancel_requested is True
    session.close()

    page = client.get("/storage/jobs")
    assert "lake" in page.text
    assert "cancel" in page.text

    done = client.post("/storage/jobs/999/cancel", follow_redirects=True)
    assert "nothing to cancel" in done.text
