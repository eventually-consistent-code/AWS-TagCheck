# Phase 5: dry run diff engine — Context

## Locked decisions

- **Read-only, guaranteed.** `--dry-run-diff` fetches live config with
  ONLY GET / list S3 calls — never a Put/Delete. This is the apply
  ladder's rung one: it shows what an apply WOULD change and writes
  nothing. A test asserts the fetch path calls no mutating client method.

- **The diff is a whole-config SET diff, not a line diff.** S3's
  `PutBucketLifecycleConfiguration` REPLACES a bucket's entire rule set
  (the emit side already treats every generated file as a full config).
  So the diff classifies each rule by ID into:
  - **would-add** — in generated, not live.
  - **would-remove** — in live, not generated. LOUD: because apply
    replaces the whole config, any live rule we don't emit gets DROPPED.
    This is the dangerous case a future guarded apply must confirm.
  - **would-change** — same ID, normalized bodies differ.
  - **unchanged** — same ID, equal after normalization.
  Intelligent-Tiering diffs the same way, keyed by config `Id`.

- **Diff against a freshly-generated config, in-memory.** `--dry-run-diff`
  operates on a scan run (like the other subcommands): it regenerates the
  lifecycle + tiering configs in-memory from the run (reusing
  `build_lifecycle_configs` / `build_tiering_configs`) and diffs them
  against live — no artifact-file parsing, no new persistence. Both sides
  are current: generated-from-the-run vs live-now.

- **Normalization before compare** (per RESEARCH): strip
  `ResponseMetadata` + `TransitionDefaultMinimumObjectSize`; canonicalize
  the prefix across rule-level `Prefix` / `Filter.Prefix` /
  `Filter.And.Prefix` → `""` when whole-bucket; sort Transitions /
  Tierings; compare only the generator-emitted key subset; a `Date`-based
  live rule is a genuine difference, never a crash.

- **Honest missing-signal messaging.** 404
  (`NoSuchLifecycleConfiguration`) → "no live config" (diff vs empty, so
  everything is would-add). 403 (`AccessDenied`) → "unknown — no
  permission to read config for <bucket>", NOT "no config" — never
  conflate can't-see with nothing-there. IT: empty list = no live config.

- **Freshness is content-based.** No server-side config-age token exists,
  so there is no timestamp/ETag freshness check — the diff itself is the
  freshness/drift signal. A clean diff means live already reflects what
  we'd generate; a non-empty diff is the drift. Framed exactly that way
  in the output; no fabricated "last-applied" claim.

- **S3-only.** Lifecycle / intelligent-tiering are S3 concepts. On a
  non-S3 backend `--dry-run-diff` errors cleanly ("dry-run-diff is S3
  only") rather than pretending.

- **Output shaped for a future guarded apply.** The engine returns a
  structured `ConfigDiff` (per bucket: the four rule buckets, plus the
  unknown/no-config flags); the CLI renders it rule-by-rule with the
  drop-warning surfaced. The dataclass is the contract a later apply rung
  consumes.
