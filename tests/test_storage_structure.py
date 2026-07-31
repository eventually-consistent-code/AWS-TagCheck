"""
Purpose: Tests for the structure recommendation engine and move plans —
rule selection + precedence, per-prefix keying with owner attribution,
persisted-rec caps, and the two-pass move-plan flow with collision skips.
Author(s): John Reed
"""

import csv
import datetime
from types import SimpleNamespace

from tagmanager.storage import cli
from tagmanager.storage.base import StorageObject
from tagmanager.storage.manifests import MoveManifestEmitter
from tagmanager.storage.pricing import BYTES_PER_GB, load_pricing
from tagmanager.storage.structure import (MAX_PERSISTED_RECS,
                                          build_recommendations, recs_to_json)

BANDS = [90, 365]
NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)
KIB = 1024


def _stat(prefix="logs", band=">365d", sclass="STANDARD", count=10,
          total_bytes=10 * BYTES_PER_GB, small_count=0, small_bytes=0,
          owner="", container="bkt"):
    return SimpleNamespace(container=container, prefix=prefix,
                           storage_class=sclass, age_band=band,
                           object_count=count, total_bytes=total_bytes,
                           small_object_count=small_count,
                           small_object_bytes=small_bytes, owner=owner)


def _kinds(stats):
    recs, _ = build_recommendations(stats, BANDS)
    return {(rec.container, rec.prefix): rec.kind for rec in recs}


def test_date_split_for_cold_heavy_active_prefix():
    """>70% cold + fresh activity -> date-split."""
    stats = [_stat(band=">365d", total_bytes=80 * BYTES_PER_GB),
             _stat(band="<90d", total_bytes=10 * BYTES_PER_GB)]
    assert _kinds(stats) == {("bkt", "logs"): "date-split"}


def test_straight_lifecycle_for_dead_prefix():
    """Entirely cold, no fresh -> straight-lifecycle."""
    stats = [_stat(band=">365d")]
    assert _kinds(stats) == {("bkt", "logs"): "straight-lifecycle"}


def test_compact_first_beats_transition_advice():
    """Small-object-dominated cold prefix -> compact-first, even when the
    cold share would otherwise say date-split."""
    stats = [_stat(band=">365d", count=1000, small_count=800,
                   small_bytes=800 * 4 * KIB),
             _stat(band="<90d", total_bytes=BYTES_PER_GB)]
    assert _kinds(stats) == {("bkt", "logs"): "compact-first"}


def test_zone_split_for_class_mix():
    """Same-level class mix (below cold-share bar) -> zone-split."""
    stats = [_stat(band="90-365d", sclass="STANDARD",
                   total_bytes=40 * BYTES_PER_GB),
             _stat(band="<90d", sclass="GLACIER",
                   total_bytes=60 * BYTES_PER_GB)]
    assert _kinds(stats) == {("bkt", "logs"): "zone-split"}


def test_fresh_only_prefix_gets_nothing():
    """All-fresh prefixes produce no recommendation."""
    assert not _kinds([_stat(band="<90d")])


def test_owner_slices_attribute_not_duplicate():
    """Owner-keyed slices of one prefix yield ONE rec with attribution."""
    stats = [_stat(band=">365d", owner="alice",
                   total_bytes=60 * BYTES_PER_GB),
             _stat(band=">365d", owner="bob", total_bytes=30 * BYTES_PER_GB)]
    recs, _ = build_recommendations(stats, BANDS)
    assert len(recs) == 1
    assert recs[0].top_owners == ["alice", "bob"]


def test_cost_at_stake_priced_and_sorted():
    """With pricing, recs sort by cold-$ at stake."""
    stats = [_stat(prefix="big", band=">365d",
                   total_bytes=100 * BYTES_PER_GB),
             _stat(prefix="small", band=">365d", total_bytes=BYTES_PER_GB)]
    recs, _ = build_recommendations(stats, BANDS, pricing=load_pricing())
    assert [rec.prefix for rec in recs] == ["big", "small"]
    assert recs[0].monthly_cost_at_stake > 0


def test_recs_json_caps_and_marks_truncation():
    """Persisted payload caps at MAX_PERSISTED_RECS with a marker."""
    stats = [_stat(prefix=f"p{i}") for i in range(MAX_PERSISTED_RECS + 10)]
    recs, _ = build_recommendations(stats, BANDS)
    payload = recs_to_json(recs)
    assert len(payload) == MAX_PERSISTED_RECS + 1
    assert payload[-1]["kind"] == "truncated"


def test_move_emitter_date_split_rewrite(tmp_path):
    """date-split injects year/month; conforming keys are skipped."""
    recs = [{"kind": "date-split", "container": "bkt", "prefix": "logs"}]
    emitter = MoveManifestEmitter(tmp_path, recs, stale_after_days=90,
                                  now=NOW)
    emitter.offer(StorageObject(
        backend="s3", container="bkt", key="logs/app.log", size_bytes=10,
        last_modified=datetime.datetime(2024, 6, 3,
                                        tzinfo=datetime.timezone.utc)))
    emitter.offer(StorageObject(
        backend="s3", container="bkt", key="logs/2024/06/b.log",
        size_bytes=10, last_modified=NOW))
    summary = emitter.close()

    assert summary["bkt"] == {"moves": 1}
    assert summary["_skipped_conforming"] == 1
    rows = (tmp_path / "bkt.move-plan.csv").read_text(encoding="utf-8")
    assert "logs/app.log,logs/2024/06/app.log" in rows


def test_move_emitter_zone_split_stale_only(tmp_path):
    """zone-split moves only stale objects; cold/ keys skipped."""
    recs = [{"kind": "zone-split", "container": "bkt", "prefix": "data"}]
    emitter = MoveManifestEmitter(tmp_path, recs, stale_after_days=90,
                                  now=NOW)
    emitter.offer(StorageObject(
        backend="s3", container="bkt", key="data/old.bin", size_bytes=10,
        last_modified=NOW - datetime.timedelta(days=200)))
    emitter.offer(StorageObject(
        backend="s3", container="bkt", key="data/hot.bin", size_bytes=10,
        last_modified=NOW))
    summary = emitter.close()

    assert summary["bkt"] == {"moves": 1}
    rows = (tmp_path / "bkt.move-plan.csv").read_text(encoding="utf-8")
    assert "data/old.bin,cold/data/old.bin" in rows
    assert "hot.bin" not in rows.replace("old.bin", "")


def test_cli_two_pass_move_plan(tmp_path, monkeypatch, capsys):
    """recommend -> rescan with --emit-move-plan; and refusal without recs."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="logs/old.log",
                                size_bytes=8 * BYTES_PER_GB,
                                last_modified=now - datetime.timedelta(days=500))
            yield StorageObject(backend="s3", container=container,
                                key="logs/new.log", size_bytes=BYTES_PER_GB,
                                last_modified=now)

        def capabilities(self):
            raise NotImplementedError

    move_dir = tmp_path / "moves"
    # Refusal before any recommendations exist.
    assert cli.main(["--bucket", "bkt", "--emit-move-plan", str(move_dir)],
                    provider=_Provider()) == 4

    # Pass 1: scan + recommend (persists recs on the run).
    assert cli.main(["--bucket", "bkt", "--recommend-structure"],
                    provider=_Provider()) == 0
    assert "date-split" in capsys.readouterr().out

    # Pass 2: rescan with the move plan.
    rc = cli.main(["--bucket", "bkt", "--emit-move-plan", str(move_dir)],
                  provider=_Provider())
    assert rc == 0
    rows = (move_dir / "bkt.move-plan.csv").read_text(encoding="utf-8")
    assert "logs/old.log,logs/" in rows
    assert "new.log" not in rows.split("\n")[0]
    apply_text = (move_dir / "APPLY.md").read_text(encoding="utf-8")
    assert "COPY + DELETE" in apply_text
