---
type: constraint
provenanceFiles: [tagmanager/storage/rollup.py, tagmanager/storage/manifests.py]
provenanceCommits: [4910203, a15921c]
created: 2026-07-31
confidence: high
---
Storage stack structural facts (milestone 4): rollups are aggregate-first and keep NO object keys, so prefix-level artifacts (lifecycle/tiering configs, expiration rules) generate from persisted runs while key-level manifests (delete chunks, batch-copy, move plans) must stream during a scan — move plans are inherently two-pass (recommend → rescan; recs load from the latest complete run BEFORE the walk, since the in-progress run is still "running"). Cell keys are ALWAYS 5-tuple (container, prefix, class, band, owner) with owner "" when the dimension is off — a conditional key shape breaks every unpacker (band_totals, persist_rollups, write_csv). Growing the key means updating every unpacker in one commit.
