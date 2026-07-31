"""
Purpose: Tests for access-aware aging — the read-hot-never-edited case,
S3 server-access-log parsing (real record format), and --access-logs CLI
enrichment end-to-end.
Author(s): John Reed
"""

import datetime

from tagmanager.storage import cli
from tagmanager.storage.access_log import load_access_index, parse_line
from tagmanager.storage.base import StorageObject
from tagmanager.storage.rollup import RollupBuilder

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)

LOG_LINE = ('79a5 mybucket [06/Feb/2026:00:00:38 +0000] 192.0.2.3 '
            'arn:aws:iam::123456789012:user/reader 3E57427F3EXAMPLE '
            'REST.GET.OBJECT reports/q1%2C%20final.pdf '
            '"GET /mybucket/reports/q1%2C%20final.pdf HTTP/1.1" 200 - 2662992 '
            '2662992 70 47 "-" "aws-cli/2.15" - tokenchars= SigV4 '
            'ECDHE-RSA-AES128-GCM-SHA256 AuthHeader mybucket.s3.amazonaws.com '
            'TLSv1.2 - -')

PUT_LINE = LOG_LINE.replace("REST.GET.OBJECT", "REST.PUT.OBJECT")
DASH_KEY_LINE = ('79a5 mybucket [06/Feb/2026:00:00:38 +0000] 192.0.2.3 req '
                 'id REST.GET.BUCKET - "GET / HTTP/1.1" 200 - 0 0 1 1 "-" '
                 '"c" - t= SigV4 c A h TLSv1.2 - -')


def test_parse_line_real_format():
    """A real GET record parses to (bucket, decoded key, aware time)."""
    bucket, key, when = parse_line(LOG_LINE)
    assert bucket == "mybucket"
    assert key == "reports/q1, final.pdf"
    assert when == datetime.datetime(2026, 2, 6, 0, 0, 38,
                                     tzinfo=datetime.timezone.utc)


def test_parse_line_filters_noise():
    """Non-GET ops, dash keys, and garbage return None."""
    assert parse_line(PUT_LINE) is None
    assert parse_line(DASH_KEY_LINE) is None
    assert parse_line("not a log line") is None
    assert parse_line("") is None


def test_load_access_index_keeps_newest(tmp_path):
    """Index folds duplicate keys to the newest read."""
    older = LOG_LINE.replace("06/Feb/2026", "01/Jan/2026")
    log = tmp_path / "access.log"
    log.write_text(f"{older}\n{LOG_LINE}\n{PUT_LINE}\n", encoding="utf-8")

    index, used = load_access_index([str(log)])
    assert used == 2
    assert index[("mybucket", "reports/q1, final.pdf")].day == 6


def test_read_hot_object_stays_fresh():
    """PLAN task 5's promise: read-hot never-edited lands in the fresh band."""
    builder = RollupBuilder(age_band_days=[90, 365], now=NOW)
    builder.add(StorageObject(
        backend="s3", container="bkt", key="hot.dat", size_bytes=100,
        last_modified=NOW - datetime.timedelta(days=800),
        last_accessed=NOW - datetime.timedelta(days=3)))

    assert builder.access_aware
    cells = builder.rollups()
    assert list(cells) == [("bkt", "", "STANDARD", "<90d", "")]


def test_no_access_data_unchanged():
    """Without access times the modified-age behavior is untouched."""
    builder = RollupBuilder(age_band_days=[90, 365], now=NOW)
    builder.add(StorageObject(
        backend="s3", container="bkt", key="cold.dat", size_bytes=100,
        last_modified=NOW - datetime.timedelta(days=800)))
    assert not builder.access_aware
    assert list(builder.rollups()) == [("bkt", "", "STANDARD", ">365d", "")]


def test_cli_access_logs_enrichment(tmp_path, monkeypatch, capsys):
    """--access-logs flips a stale-by-mtime object into the fresh band and
    labels output access-aware."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    read_day = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=2))
    line = LOG_LINE.replace("mybucket", "bkt").replace(
        "[06/Feb/2026:00:00:38 +0000]",
        read_day.strftime("[%d/%b/%Y:%H:%M:%S +0000]"))
    log = tmp_path / "access.log"
    log.write_text(line + "\n", encoding="utf-8")

    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="reports/q1, final.pdf", size_bytes=1024,
                                last_modified=now - datetime.timedelta(days=700))

        def capabilities(self):
            raise NotImplementedError

    rc = cli.main(["--bucket", "bkt", "--access-logs", str(log)],
                  provider=_Provider())
    assert rc == 0
    out = capsys.readouterr().out
    assert "access-aware" in out
    assert "<90d" in out

    assert cli.main(["--bucket", "b", "--access-logs",
                     str(tmp_path / "nope*.log")]) == 4