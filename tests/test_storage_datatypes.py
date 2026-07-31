"""
Purpose: Tests for the data-type classifier and the --rollup-types
dimension plumbing — extension mapping edge cases, the always-6-tuple
cell key, persistence roundtrip, and combined owners x types.
Author(s): John Reed
"""

import datetime

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import StoragePrefixStat
from tagmanager.storage.base import StorageObject
from tagmanager.storage.datatypes import classify_key
from tagmanager.storage.rollup import RollupBuilder
from tagmanager.storage.store import persist_rollups

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)


def test_classify_key_coarse_types():
    """Each bucket resolves from a representative extension."""
    assert classify_key("app/server.log") == "logs"
    assert classify_key("photos/beach.JPG") == "media"       # case-insensitive
    assert classify_key("backups/2019/db.tar.gz") == "archives"  # compound
    assert classify_key("exports/q1.csv") == "data"
    assert classify_key("contracts/nda.pdf") == "docs"
    assert classify_key("blob") == "other"                   # no extension
    assert classify_key("weird/file.xyzunknown") == "other"  # unknown ext


def test_classify_key_edge_cases():
    """Dotfiles, README, trailing slashes, deep paths."""
    assert classify_key("dir/README") == "other"
    assert classify_key("logs/.gitignore") == "other"        # dotfile, no ext
    assert classify_key("a/b/c/data.parquet") == "data"
    assert classify_key("archive.tgz") == "archives"


def _obj(key, days_old, owner="", size=100):
    return StorageObject(
        backend="s3", container="bkt", key=key, size_bytes=size,
        last_modified=NOW - datetime.timedelta(days=days_old), owner=owner)


def test_cell_key_always_six_tuple_types_off():
    """With --rollup-types off, data_type slot is '' — stable shape."""
    builder = RollupBuilder(age_band_days=[90], now=NOW)
    builder.add(_obj("logs/a.log", days_old=5))
    (key,) = list(builder.rollups())
    assert len(key) == 6
    assert key[4] == "" and key[5] == ""    # owner, data_type both off


def test_rollup_types_splits_cells():
    """Types on: same prefix/band splits by data type."""
    builder = RollupBuilder(age_band_days=[90], now=NOW, rollup_types=True)
    builder.add(_obj("mix/a.log", days_old=5))
    builder.add(_obj("mix/b.csv", days_old=6))
    types = {key[5] for key in builder.rollups()}
    assert types == {"logs", "data"}


def test_owners_times_types_multiplies():
    """Both dimensions on: cells key on (owner, data_type) jointly."""
    builder = RollupBuilder(age_band_days=[90], now=NOW,
                            rollup_owners=True, rollup_types=True)
    builder.add(_obj("p/a.log", days_old=5, owner="alice"))
    builder.add(_obj("p/b.log", days_old=5, owner="bob"))
    builder.add(_obj("p/c.csv", days_old=5, owner="alice"))
    keys = {(key[4], key[5]) for key in builder.rollups()}
    assert keys == {("alice", "logs"), ("bob", "logs"), ("alice", "data")}


def test_persist_roundtrip_records_data_type():
    """The data_type column persists and reads back."""
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    session = session_factory(engine)()

    builder = RollupBuilder(age_band_days=[90], now=NOW, rollup_types=True)
    builder.add(_obj("logs/old.log", days_old=200))
    persist_rollups(session, builder, backend="s3")
    session.commit()

    stat = session.query(StoragePrefixStat).one()
    assert stat.data_type == "logs"
