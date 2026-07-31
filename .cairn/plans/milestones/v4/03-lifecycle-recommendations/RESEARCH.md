# Phase 3: lifecycle recommendations — Research

Researched: 2026-07-31 (live AWS docs: CLI reference + S3 User Guide).
Note: one scraped doc page contained an injected garbage token inside a
policy example; researcher excluded it and used canonical doc content.

## Artifact shapes (confirmed against live docs)

- **Lifecycle config** (`put-bucket-lifecycle-configuration`): top-level
  `Rules` array; per rule ID (≤255), Status, `Filter` (bare single
  condition, or `And` wrapping Prefix + ObjectSizeGreaterThan/LessThan —
  bytes, bounds exclusive), `Transitions` [{Days, StorageClass}],
  `Expiration` {Days}. Transition StorageClass enum:
  GLACIER | STANDARD_IA | ONEZONE_IA | INTELLIGENT_TIERING |
  DEEP_ARCHIVE | GLACIER_IR.
- **Intelligent-Tiering config**
  (`put-bucket-intelligent-tiering-configuration`): {Id, Status, Filter,
  Tierings: [{Days, AccessTier}]}; AccessTier ARCHIVE_ACCESS (min 90d) /
  DEEP_ARCHIVE_ACCESS (min 180d), max 730; only affects objects already
  IN the INTELLIGENT_TIERING class.
- **Batch Operations manifest**: `S3BatchOperations_CSV_20180820`,
  `bucket,key[,versionId]` lines; keys URL-encoded; version IDs
  all-or-nothing; manifest uploads to S3 first and create-job needs its
  ETag. Copy op: ≤5 GB objects, one source/destination bucket per job,
  job created in destination region, role trust
  `batchoperations.s3.amazonaws.com`.

## Hard constraints for the generator

- **PUT replaces the whole lifecycle config** — emit the COMPLETE rule
  set per bucket, never a delta. Max 1,000 rules.
- **Min-days**: no IA transition before 30d; chained IA → Glacier must be
  ≥30d after the IA step; Expiration.Days > any transition Days in the
  same rule. Expiration precedence beats transitions on conflict.
- **Sept-2024 default**: objects <128 KiB transition NOWHERE by default —
  `ObjectSizeGreaterThan` must be explicit (matches phase-2 carry-over).
- **Waterfall is one-way down**; INT sources only → OZ-IA/GIR/Glacier/DA.

## Mass delete — decision-grade finding

**Batch Operations has NO plain delete-objects operation** (tag deletion
only — easy trap). Mass-delete paths:
(a) **Lifecycle Expiration rule** — free, managed, async (days-scale
sweep), AWS-recommended for "empty this prefix";
(b) **`aws s3api delete-objects`** — immediate, hard limit 1,000 keys per
request → generated manifests must be pre-chunked JSON
({Objects: [{Key}...], Quiet: true}); versioned buckets create delete
markers unless VersionId given.

## Architecture consequence

Phase-1 rollups are aggregates — **no per-object keys survive the scan**.
So: prefix-level artifacts (lifecycle configs, tiering configs,
expiration rules) generate from the persisted run in report-only mode;
key-level artifacts (delete-objects chunks, batch-ops copy manifests)
must be emitted STREAMING DURING A SCAN, gated on the same age
thresholds. Two generation surfaces, one honest split.
