"""
Purpose: Tests for the insights pages and artifact generate/download flow
— latest-run rendering, fs no-pricing honesty, empty states, and the
generate -> index -> zip roundtrip with artifact_dir honored.
Author(s): John Reed
"""

import datetime
import io
import zipfile

from fastapi.testclient import TestClient

from tagmanager.config import Settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.storage import services
from tagmanager.storage.base import StorageObject
from tagmanager.storage.pricing import BYTES_PER_GB

NOW = datetime.datetime.now(datetime.timezone.utc)


class _Provider:
    backend_name = "s3"

    def list_objects(self, container, prefix=""):
        yield StorageObject(backend="s3", container=container,
                            key="logs/old.log", size_bytes=8 * BYTES_PER_GB,
                            last_modified=NOW - datetime.timedelta(days=500))
        yield StorageObject(backend="s3", container=container,
                            key="logs/new.log", size_bytes=BYTES_PER_GB,
                            last_modified=NOW)

    def capabilities(self):
        raise NotImplementedError


def _client_with_run(tmp_path, monkeypatch):
    """App client + a persisted s3 run, artifact_dir inside tmp."""
    from tagmanager.app.main import create_app  # pylint: disable=import-outside-toplevel
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'ins.db'}")
    maker = services.open_storage_session_maker()
    services.run_storage_scan(maker, services.ScanOptions(buckets=("bkt",)),
                              provider=_Provider())
    settings = Settings(auth_mode="none",
                        artifact_dir=str(tmp_path / "arts"))
    engine = get_engine(f"sqlite:///{tmp_path / 'ins.db'}")
    create_all(engine)
    return TestClient(create_app(settings, session_factory(engine))), maker


def test_cost_and_savings_pages(tmp_path, monkeypatch):
    """Both pages render figures with disclaimers off the latest run."""
    client, _ = _client_with_run(tmp_path, monkeypatch)

    cost = client.get("/storage/cost")
    assert cost.status_code == 200
    assert "not a bill" in cost.text
    assert "bkt/logs" in cost.text
    assert "total:" in cost.text

    savings = client.get("/storage/savings")
    assert "delete" in savings.text
    assert "stale slice only" in savings.text


def test_recommendations_page(tmp_path, monkeypatch):
    """Recommendations render with rationale and note list."""
    client, _ = _client_with_run(tmp_path, monkeypatch)
    page = client.get("/storage/recommendations")
    assert page.status_code == 200
    assert "date-split" in page.text
    assert "out of scope" in page.text


def test_insights_empty_state(tmp_path, monkeypatch):
    """No runs for a backend -> friendly prompt."""
    client, _ = _client_with_run(tmp_path, monkeypatch)
    page = client.get("/storage/cost?backend=gcs")
    assert "no saved gcs runs" in page.text


def test_artifact_generate_index_download_roundtrip(tmp_path, monkeypatch):
    """Generate lifecycle + report, see them indexed, download real zips
    into the configured artifact_dir."""
    client, _ = _client_with_run(tmp_path, monkeypatch)

    page = client.post("/storage/runs/1/artifacts/lifecycle",
                       follow_redirects=True)
    assert "lifecycle artifacts generated." in page.text
    page = client.post("/storage/runs/1/artifacts/report",
                       follow_redirects=True)
    assert "report artifacts generated." in page.text
    assert "download zip" in page.text

    assert (tmp_path / "arts" / "run-1" / "lifecycle").is_dir()

    download = client.get("/storage/runs/1/artifacts/lifecycle/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    names = archive.namelist()
    assert "APPLY.md" in names
    assert any(name.endswith(".lifecycle.json") for name in names)

    report_zip = zipfile.ZipFile(io.BytesIO(
        client.get("/storage/runs/1/artifacts/report/download").content))
    assert "storage-report.html" in report_zip.namelist()


def test_artifact_errors_are_messages(tmp_path, monkeypatch):
    """Unknown kind and not-yet-generated downloads redirect with
    messages, never 500."""
    client, _ = _client_with_run(tmp_path, monkeypatch)

    page = client.post("/storage/runs/1/artifacts/bogus",
                       follow_redirects=True)
    assert "unknown artifact kind" in page.text

    page = client.get("/storage/runs/1/artifacts/tiering/download",
                      follow_redirects=True)
    assert "generate first" in page.text

    page = client.post("/storage/runs/999/artifacts/lifecycle",
                       follow_redirects=True)
    assert "no such run." in page.text
