---
type: gotcha
provenanceFiles: [.cairn/plans/milestones/v4/02-cost-analysis-engine/VERIFICATION.md, .cairn/plans/milestones/v4/05-structure-recommendations-and-reporting/VERIFICATION.md]
provenanceCommits: [e099064, e099064]
created: 2026-07-31
confidence: high
---
Adversarial verification caught spec-level bugs that green unit tests could not, twice in milestone 4. Phase 2 was REFUTED outright: the age-out projector omitted Glacier per-object overhead and recommended a transition that loses money on 1M tiny objects (+$0.02 shown vs −$0.27 true) — the exact honesty case the phase existed for. Phase 5 yielded a dead bimodal zone-split trigger and comma-corrupt move CSVs. Root cause both times: tests assert math the implementation and the test AGREE on; the adversarial agent recomputed independently from AWS billing semantics — a different oracle, so shared-assumption bugs had nowhere to hide. Rule: any phase doing money math or artifact generation gets deep verify with an independent-recomputation skeptic.
