"""
Purpose: Tests for the lifecycle config generator — rule shape, hard
validation (IA minimums, chain gaps, explicit size filter), INT skips,
and the --emit-lifecycle CLI mode.
Author(s): John Reed
"""

import datetime
import json
from types import SimpleNamespace

import pytest

from tagmanager.storage import cli
from tagmanager.storage.base import StorageObject
from tagmanager.storage.lifecycle_gen import (LifecycleValidationError,
                                              build_lifecycle_configs,
                                              validate_config)

BANDS = [90, 365]


def _stat(prefix="logs/2019", band=">365d", sclass="STANDARD",
          container="bkt"):
    return SimpleNamespace(container=container, prefix=prefix,
                           storage_class=sclass, age_band=band,
                           object_count=1, total_bytes=1024,
                           small_object_count=0, small_object_bytes=0)


def test_generates_complete_config_with_ladder():
    """Stale prefix gets one rule carrying the full transition ladder and
    the explicit small-object filter."""
    configs, skips = build_lifecycle_configs([_stat()], BANDS)

    assert not skips
    rule = configs["bkt"]["Rules"][0]
    assert rule["Filter"]["And"]["Prefix"] == "logs/2019/"
    assert rule["Filter"]["And"]["ObjectSizeGreaterThan"] == 131072
    assert rule["Transitions"] == [
        {"Days": 90, "StorageClass": "STANDARD_IA"},
        {"Days": 365, "StorageClass": "GLACIER"}]
    assert "Expiration" not in rule


def test_delete_after_adds_expiration():
    """delete_after lands as an Expiration past the last transition."""
    configs, _ = build_lifecycle_configs([_stat()], BANDS, delete_after=730)
    assert configs["bkt"]["Rules"][0]["Expiration"] == {"Days": 730}


def test_int_only_prefix_with_illegal_target_is_skipped():
    """All-INT prefix mapped at Standard-IA gets a skip, not a dead rule."""
    stats = [_stat(band="90-365d", sclass="INTELLIGENT_TIERING")]
    configs, skips = build_lifecycle_configs(stats, BANDS)

    assert not configs
    assert len(skips) == 1 and "INTELLIGENT_TIERING" in skips[0]


def test_glacier_only_prefix_is_skipped():
    """Prefixes with no transition-eligible class produce a skip."""
    configs, skips = build_lifecycle_configs([_stat(sclass="GLACIER")], BANDS)
    assert not configs
    assert "no transition-eligible" in skips[0]


def test_validator_rejects_ia_below_30_days():
    """IA transition under 30d is a generation error."""
    with pytest.raises(LifecycleValidationError, match="below the 30d"):
        build_lifecycle_configs([_stat(band="7-30d")], [7, 30])


def test_validator_rejects_short_chain_gap():
    """IA at 30d then Glacier at 45d violates the 30d chain gap."""
    with pytest.raises(LifecycleValidationError, match="under 30d after"):
        build_lifecycle_configs([_stat(band=">45d")], [30, 45])


def test_validator_rejects_expiration_before_transition():
    """Expiration must exceed the last transition day."""
    with pytest.raises(LifecycleValidationError, match="must exceed"):
        build_lifecycle_configs([_stat()], BANDS, delete_after=100)


def test_validator_requires_size_filter():
    """A rule without ObjectSizeGreaterThan is refused outright."""
    config = {"Rules": [{"ID": "x", "Status": "Enabled",
                         "Filter": {"And": {"Prefix": "p/"}},
                         "Transitions": [{"Days": 90,
                                          "StorageClass": "STANDARD_IA"}]}]}
    with pytest.raises(LifecycleValidationError, match="ObjectSizeGreaterThan"):
        validate_config(config)


def test_cli_emit_lifecycle(tmp_path, monkeypatch, capsys):
    """Scan then emit: config file + APPLY.md land in the output dir."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="logs/2019/dump.tar",
                                size_bytes=10 * 1024 ** 3,
                                last_modified=now - datetime.timedelta(days=500))

        def capabilities(self):
            raise NotImplementedError

    assert cli.main(["--bucket", "bkt"], provider=_Provider()) == 0

    out_dir = tmp_path / "artifacts"
    rc = cli.main(["--emit-lifecycle", str(out_dir)])
    assert rc == 0

    with open(out_dir / "bkt.lifecycle.json", encoding="utf-8") as handle:
        config = json.load(handle)
    assert config["Rules"][0]["Filter"]["And"]["Prefix"] == "logs/2019/"
    apply_text = (out_dir / "APPLY.md").read_text(encoding="utf-8")
    assert "put-bucket-lifecycle-configuration" in apply_text
    assert "REPLACES" in apply_text
    assert "generating lifecycle configs..." in capsys.readouterr().out


def test_cli_emit_lifecycle_empty_run(tmp_path, monkeypatch):
    """Nothing stale -> exit 4 with guidance, no files."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="fresh/x", size_bytes=1024 ** 3,
                                last_modified=now)

        def capabilities(self):
            raise NotImplementedError

    assert cli.main(["--bucket", "bkt"], provider=_Provider()) == 0
    assert cli.main(["--emit-lifecycle", str(tmp_path / "out")]) == 4
