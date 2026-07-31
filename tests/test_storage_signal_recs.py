"""
Purpose: Tests for phase-4 signal-driven recommendation upgrades — the
per-kind confidence/evidence rubric, the expire-in-place churn kind that
consumes write telemetry, its precedence slot (below fan-out, above every
transition kind), and confidence/evidence persistence.
Author(s): John Reed
"""

from types import SimpleNamespace

from tagmanager.storage.pricing import BYTES_PER_GB
from tagmanager.storage.structure import (
    CHURN_WRITE_FRACTION, FANOUT_CEILING_FRACTION, READ_CEILING_RPS,
    WRITE_CEILING_RPS, build_recommendations, recs_to_json)

BANDS = [90, 365]

# pylint: disable=too-many-arguments,too-many-positional-arguments


def _stat(prefix="logs", band=">365d", total_bytes=10 * BYTES_PER_GB,
          storage_class="STANDARD", small=0, count=10, data_type=""):
    return SimpleNamespace(container="bkt", prefix=prefix,
                           storage_class=storage_class, age_band=band,
                           object_count=count, total_bytes=total_bytes,
                           small_object_count=small, small_object_bytes=0,
                           owner="", data_type=data_type)


def _rate(read_frac=0.0, write_frac=0.0, container="bkt", prefix="logs"):
    return {"container": container, "prefix": prefix,
            "read_rps": read_frac * READ_CEILING_RPS,
            "write_rps": write_frac * WRITE_CEILING_RPS,
            "window_s": 7200, "sample_ops": 99999}


def _only(recs):
    assert len(recs) == 1, [r.kind for r in recs]
    return recs[0]


# Confidence rubric

def test_cold_rec_low_confidence_without_access_telemetry():
    """An age-only cold rec is graded low — the weaker inference."""
    rec = _only(build_recommendations([_stat()], BANDS)[0])
    assert rec.kind == "straight-lifecycle"
    assert rec.confidence == "low"
    assert rec.evidence == ["age (no access telemetry)"]


def test_cold_rec_high_confidence_when_access_aware():
    """On an access-aware run a still-cold prefix is telemetry-verified
    unread — the cold rec grades high."""
    rec = _only(build_recommendations([_stat()], BANDS, access_aware=True)[0])
    assert rec.kind == "straight-lifecycle"
    assert rec.confidence == "high"
    assert "access telemetry (verified unread)" in rec.evidence


def test_compact_first_high_confidence():
    """compact-first is deterministic from object sizes — high."""
    rec = _only(build_recommendations(
        [_stat(small=9, count=10)], BANDS)[0])
    assert rec.kind == "compact-first"
    assert rec.confidence == "high"
    assert rec.evidence == ["object-size distribution"]


def test_type_split_medium_confidence():
    """type-split rests on age + type inference — medium. Reached only as
    the residual: mostly-fresh (no date-split), single band+class (no
    zone-split), but two data types each past the share bar."""
    stats = [_stat(prefix="mix", band="<90d", data_type="csv",
                   total_bytes=4 * BYTES_PER_GB),
             _stat(prefix="mix", band="<90d", data_type="parquet",
                   total_bytes=4 * BYTES_PER_GB),
             _stat(prefix="mix", band=">365d", data_type="csv",
                   total_bytes=1 * BYTES_PER_GB)]
    rec = _only(build_recommendations(stats, BANDS)[0])
    assert rec.kind == "type-split"
    assert rec.confidence == "medium"
    assert rec.evidence == ["age", "data types"]


def test_fanout_high_confidence():
    """prefix-fanout is rate-telemetry-backed — high."""
    rates = {"bkt/logs": _rate(read_frac=FANOUT_CEILING_FRACTION + 0.1)}
    rec = _only(build_recommendations([_stat()], BANDS,
                                      request_rates=rates)[0])
    assert rec.kind == "prefix-fanout"
    assert rec.confidence == "high"
    assert rec.evidence == ["request-rate telemetry"]


# expire-in-place churn kind

def test_expire_in_place_fires_on_write_hot_cold_prefix():
    """Write telemetry past the churn fraction on cold data yields
    expire-in-place with a min-duration warning + conditional honesty."""
    rates = {"bkt/logs": _rate(write_frac=CHURN_WRITE_FRACTION + 0.01)}
    rec = _only(build_recommendations([_stat()], BANDS,
                                      request_rates=rates)[0])
    assert rec.kind == "expire-in-place"
    assert rec.confidence == "high"
    assert rec.evidence == ["write-rate telemetry"]
    assert "early-delete" in rec.rationale
    assert "IF" in rec.rationale  # conditional, never a hard determination


def test_expire_in_place_silent_below_the_write_fraction():
    """A trickle of writes leaves the transition rec standing."""
    rates = {"bkt/logs": _rate(write_frac=CHURN_WRITE_FRACTION - 0.01)}
    rec = _only(build_recommendations([_stat()], BANDS,
                                      request_rates=rates)[0])
    assert rec.kind == "straight-lifecycle"


def test_expire_in_place_silent_without_cold_data():
    """No cold bytes -> no transition to warn against -> no churn rec."""
    fresh = _stat(band="<90d")  # entirely fresh
    rates = {"bkt/logs": _rate(write_frac=0.1)}  # churn-hot but no cold data
    recs, _ = build_recommendations([fresh], BANDS, request_rates=rates)
    assert not any(r.kind == "expire-in-place" for r in recs)


def test_expire_in_place_beats_every_transition_kind():
    """Even a compact-first prefix yields expire-in-place when write-hot —
    tiering churn is pointless."""
    stats = [_stat(small=9, count=10)]  # would be compact-first
    # write-hot enough for churn, below the fan-out ceiling fraction.
    rates = {"bkt/logs": _rate(write_frac=0.1)}
    rec = _only(build_recommendations(stats, BANDS, request_rates=rates)[0])
    assert rec.kind == "expire-in-place"


def test_fanout_beats_expire_in_place():
    """A live read ceiling outranks the churn warning."""
    rates = {"bkt/logs": _rate(read_frac=0.9, write_frac=0.9)}
    rec = _only(build_recommendations([_stat()], BANDS,
                                      request_rates=rates)[0])
    assert rec.kind == "prefix-fanout"


# persistence

def test_confidence_and_evidence_persist():
    """recs_to_json carries confidence + evidence for the HTML report."""
    payload = recs_to_json(build_recommendations([_stat()], BANDS)[0])
    assert payload[0]["confidence"] == "low"
    assert payload[0]["evidence"] == ["age (no access telemetry)"]
