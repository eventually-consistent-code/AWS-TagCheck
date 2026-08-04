"""
Purpose: Tests for the AWS-free dry-run diff core — rule-ID set diff
(add/remove/change/unchanged), the dangerous would-remove drop case, and
the normalization that keeps semantically-equal rules from reading as
changed (prefix-shape collapse, unordered transitions, Date-vs-Days).
Author(s): John Reed
"""

import datetime

from tagmanager.storage.diff import (FetchResult, diff_bucket, diff_rule_set,
                                      normalize_lifecycle_rule,
                                      normalize_tiering_config)

FLOOR = 128 * 1024


def _gen_rule(rule_id="tagmanager-logs-age-out", prefix="logs/",
              days=30, storage_class="STANDARD_IA"):
    """A rule shaped like build_lifecycle_configs emits (Filter.And)."""
    return {"ID": rule_id, "Status": "Enabled",
            "Filter": {"And": {"Prefix": prefix,
                               "ObjectSizeGreaterThan": FLOOR}},
            "Transitions": [{"Days": days, "StorageClass": storage_class}]}


def _tier_cfg(cfg_id="tagmanager-logs-archive-tiers", prefix="logs/"):
    return {"Id": cfg_id, "Status": "Enabled",
            "Filter": {"Prefix": prefix},
            "Tierings": [{"Days": 90, "AccessTier": "ARCHIVE_ACCESS"},
                         {"Days": 180, "AccessTier": "DEEP_ARCHIVE_ACCESS"}]}


# set-diff classification

def test_would_add_when_live_lacks_the_id():
    diff = diff_rule_set([_gen_rule()], [], "ID", normalize_lifecycle_rule)
    assert len(diff.would_add) == 1
    assert not diff.would_remove and not diff.would_change
    assert diff.has_changes()


def test_would_remove_flags_live_only_rule():
    """A live rule whose ID we don't generate would be DROPPED by an apply
    (PutBucket* replaces the whole config) — the dangerous case."""
    live = [{"ID": "customer-hand-rule", "Status": "Enabled",
             "Prefix": "invoices/",
             "Transitions": [{"Days": 400, "StorageClass": "GLACIER"}]}]
    diff = diff_rule_set([_gen_rule()], live, "ID", normalize_lifecycle_rule)
    assert [r["ID"] for r in diff.would_remove] == ["customer-hand-rule"]
    assert len(diff.would_add) == 1  # our rule is new
    assert diff.has_changes()


def test_would_change_on_differing_body_same_id():
    diff = diff_rule_set([_gen_rule(days=30)], [_gen_rule(days=60)],
                         "ID", normalize_lifecycle_rule)
    assert len(diff.would_change) == 1
    generated, live = diff.would_change[0]
    assert generated["Transitions"][0]["Days"] == 30
    assert live["Transitions"][0]["Days"] == 60


def test_unchanged_when_bodies_match():
    diff = diff_rule_set([_gen_rule()], [_gen_rule()], "ID",
                         normalize_lifecycle_rule)
    assert len(diff.unchanged) == 1
    assert not diff.has_changes()


# normalization — semantically-equal rules must NOT read as changed

def test_prefix_shape_collapse_reads_equal():
    """A live rule expressed as rule-level Prefix equals our Filter.And form."""
    live_flat = {"ID": "tagmanager-logs-age-out", "Status": "Enabled",
                 "Prefix": "logs/",
                 "Filter": {"ObjectSizeGreaterThan": FLOOR},
                 "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}]}
    diff = diff_rule_set([_gen_rule()], [live_flat], "ID",
                         normalize_lifecycle_rule)
    assert len(diff.unchanged) == 1, "prefix-shape difference is spurious"


def test_unordered_transitions_read_equal():
    """AWS does not guarantee Transition order — sort before comparing."""
    gen = _gen_rule()
    gen["Transitions"] = [{"Days": 30, "StorageClass": "STANDARD_IA"},
                          {"Days": 90, "StorageClass": "GLACIER"}]
    live = dict(gen)
    live = {**gen, "Transitions": list(reversed(gen["Transitions"]))}
    assert normalize_lifecycle_rule(gen) == normalize_lifecycle_rule(live)


def test_live_only_extras_do_not_read_as_changed():
    """NoncurrentVersion*/AbortIncomplete/ExpiredObjectDeleteMarker on the
    live rule are outside the generator's key subset — ignored."""
    live = {**_gen_rule(),
            "NoncurrentVersionExpiration": {"NoncurrentDays": 10},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}}
    assert normalize_lifecycle_rule(_gen_rule()) == \
        normalize_lifecycle_rule(live)


def test_date_based_live_rule_flagged_not_crashed():
    """A live Expiration expressed with Date (not Days) is a real
    difference — surfaced, never a TypeError on the sort/compare."""
    live = {**_gen_rule(),
            "Expiration": {"Date": datetime.datetime(2027, 1, 1)}}
    gen = {**_gen_rule(), "Expiration": {"Days": 365}}
    assert normalize_lifecycle_rule(gen) != normalize_lifecycle_rule(live)


def test_tiering_prefix_and_order_normalized():
    live = {**_tier_cfg(),
            "Tierings": list(reversed(_tier_cfg()["Tierings"]))}
    assert normalize_tiering_config(_tier_cfg()) == \
        normalize_tiering_config(live)


# diff_bucket — fetch-result wiring

def test_diff_bucket_unknown_lifecycle_sets_flag():
    """A 403 on lifecycle marks unknown, never a diff (can't tell drift)."""
    result = diff_bucket(
        "bkt", [_gen_rule()], FetchResult(unknown=True, present=False),
        [], FetchResult(present=False))
    assert result.unknown_lifecycle is True
    assert result.lifecycle is None


def test_diff_bucket_no_live_lifecycle_is_all_add():
    """A 404 (no live config) diffs our rules against empty -> all add."""
    result = diff_bucket(
        "bkt", [_gen_rule()], FetchResult(rules=[], present=False),
        [], FetchResult(present=False))
    assert result.no_live_lifecycle is True
    assert len(result.lifecycle.would_add) == 1


def test_diff_bucket_present_tiering_diffs():
    result = diff_bucket(
        "bkt", [], FetchResult(present=False),
        [_tier_cfg()], FetchResult(rules=[_tier_cfg()], present=True))
    assert result.tiering is not None
    assert len(result.tiering.unchanged) == 1
    assert not result.has_changes()


# regression: a kind we generate NOTHING for must not read as would-remove

def test_ungenerated_kind_is_untouched_not_dropped():
    """A bucket we generate only tiering for: its live LIFECYCLE rules are
    left untouched by an apply — never a false would-remove/DROP."""
    live_life = FetchResult(present=True, rules=[
        {"ID": "customer-hand-rule", "Status": "Enabled",
         "Prefix": "invoices/",
         "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}]}])
    result = diff_bucket(
        "bkt", [], live_life,                       # NO generated lifecycle
        [_tier_cfg()], FetchResult(rules=[_tier_cfg()], present=True))
    assert result.lifecycle_not_generated is True
    assert result.untouched_lifecycle == 1
    assert result.lifecycle is None                 # no diff -> no would-remove
    assert not result.has_changes()                 # apply won't touch it


def test_idless_live_lifecycle_rule_is_removed_not_crash():
    """An ID-less live lifecycle rule can't correlate to a generated ID —
    it reads as would-remove, never a KeyError."""
    live = [{"Status": "Enabled", "Prefix": "misc/",
             "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}]}]
    diff = diff_rule_set([_gen_rule()], live, "ID", normalize_lifecycle_rule)
    assert len(diff.would_remove) == 1
    assert len(diff.would_add) == 1                 # our rule is still new
