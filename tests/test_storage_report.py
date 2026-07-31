"""
Purpose: Tests for the storage insights surfaces — standalone HTML report
(escaping, sections, artifacts index from recorded metadata) and the web
UI /storage page (latest-run scoping, empty state, stale-schema notice).
Author(s): John Reed
"""

import datetime

from fastapi.testclient import TestClient

from tagmanager.storage import cli
from tagmanager.storage.base import StorageObject
from tagmanager.storage.pricing import BYTES_PER_GB

NOW = datetime.datetime.now(datetime.timezone.utc)


class _Provider:
    backend_name = "s3"

    def list_objects(self, container, prefix=""):
        yield StorageObject(backend="s3", container=container,
                            key="lo<gs/old.log",
                            size_bytes=8 * BYTES_PER_GB,
                            last_modified=NOW - datetime.timedelta(days=500))
        yield StorageObject(backend="s3", container=container,
                            key="lo<gs/new.log", size_bytes=BYTES_PER_GB,
                            last_modified=NOW)

    def capabilities(self):
        raise NotImplementedError


def _scan_with_everything(tmp_path, monkeypatch):
    """One scan + recommendations + a lifecycle emit for the artifacts index."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    assert cli.main(["--bucket", "bkt", "--recommend-structure",
                     "--emit-lifecycle", str(tmp_path / "life")],
                    provider=_Provider()) == 0


def test_html_report_sections_and_escaping(tmp_path, monkeypatch):
    """Report carries every section, escapes keys, indexes artifacts."""
    _scan_with_everything(tmp_path, monkeypatch)
    out = tmp_path / "report.html"
    assert cli.main(["--html-report", str(out)]) == 0

    page = out.read_text(encoding="utf-8")
    assert "Age distribution" in page
    assert "Stale-data cost" in page
    assert "Savings options" in page
    assert "Structure recommendations" in page
    assert "Generated artifacts" in page
    assert "date-split" in page
    assert "lifecycle" in page          # artifacts index entry
    assert "not a bill" in page
    assert "lo<gs" not in page          # escaped everywhere it renders
    assert "lo&lt;gs" in page


def test_html_report_fs_backend_omits_costs(tmp_path, monkeypatch, capsys):
    """fs runs render with costs honestly omitted, exit 0."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    root = tmp_path / "share"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "f.bin").write_bytes(b"x" * 10)

    assert cli.main(["--backend", "fs", "--bucket", str(root)]) == 0
    out = tmp_path / "fs_report.html"
    assert cli.main(["--backend", "fs", "--html-report", str(out)]) == 0
    page = out.read_text(encoding="utf-8")
    assert "costs omitted" in page


def _ui_client(tmp_path):
    """App client on the same sqlite DB the CLI used."""
    # pylint: disable=import-outside-toplevel
    from tagmanager.app.main import create_app
    from tagmanager.config import Settings
    from tagmanager.models.base import create_all, get_engine, session_factory

    engine = get_engine(f"sqlite:///{tmp_path / 'scan.db'}")
    create_all(engine)
    maker = session_factory(engine)
    return TestClient(create_app(Settings(auth_mode="none"), maker))


def test_ui_storage_page_renders_latest_run(tmp_path, monkeypatch):
    """/storage shows the latest run's bands and recommendations."""
    _scan_with_everything(tmp_path, monkeypatch)
    client = _ui_client(tmp_path)

    page = client.get("/storage")
    assert page.status_code == 200
    assert "Storage insights" in page.text
    assert "365d" in page.text
    assert "date-split" in page.text


def test_ui_storage_page_empty_state(tmp_path):
    """No storage runs -> friendly prompt, not an error."""
    client = _ui_client(tmp_path)
    page = client.get("/storage")
    assert page.status_code == 200
    assert "no storage scans yet" in page.text


def test_ui_storage_page_stale_schema(tmp_path):
    """Old DB missing new columns -> notice, not a 500."""
    import sqlite3  # pylint: disable=import-outside-toplevel
    db = tmp_path / "scan.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE storage_scan_runs (id INTEGER PRIMARY KEY, "
                 "status TEXT)")
    conn.execute("INSERT INTO storage_scan_runs (status) VALUES ('complete')")
    conn.commit()
    conn.close()

    client = _ui_client(tmp_path)
    page = client.get("/storage")
    assert page.status_code == 200
    assert "schema out of date" in page.text
