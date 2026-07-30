---
verb: map
args: "[\"build\" | \"<question>\" | \"diff\" | \"status\"]"
status: live
---

Project knowledge graph — typed nodes (`module|phase|issue|decision|person`)
and typed edges (`depends-on|implements|decided-in|owns`) over a single
deterministic store. The verb does the intelligence — building the graph,
answering questions, spotting drift; the server only guarantees shape and
atomicity. Graph writes happen ONLY through `map_set` — this verb never
edits `map.json` directly, same discipline as `config_set`.

## `map build`

1. Walk the sources of truth: code structure (modules, their dependencies),
   plan artifacts (phases, decisions), and the tracker (issues, who owns
   what). Propose nodes and edges from what's actually there — don't invent
   relationships the evidence doesn't support. Requirement → decision
   `implements` edges AND decision → module `decided-in` edges (both
   sourced from draft sessions) are first-class citizens of this walk,
   same as any other edge — the design-traceability sweep the `cairn-uat`
   agent runs depends on `map build` keeping both current.
2. Write in validated chunks via `map_set(patch)` — merge-patch by node id,
   edges replaced as a whole array per patch. Small, reviewable chunks beat
   one giant patch: if a chunk gets rejected (dangling edge, bad type), the
   rest of the build isn't lost with it. Chunk NODES across as many patches
   as you like, but edges go in ONE final patch carrying the complete list —
   an edges array replaces the whole list, so a partial edges chunk erases
   every edge written before it.
3. Report the final shape: node/edge counts by type, and anything the walk
   found but couldn't place (an edge whose endpoint doesn't exist yet, for
   instance) — surfaced, not silently dropped.

## `map "<question>"`

1. `map_get(filter?)` — pull the whole graph or a filtered slice
   (`nodeType`, `edgeType`, or `node` for a node plus its neighbors and
   touching edges).
2. Answer in named terms — this decision node, that edge, this module — not
   a vague gesture at "the graph." If the graph doesn't have the answer,
   say so; that's a `map build` gap, not a reason to guess.

## `map diff`

1. Rebuild the CURRENT truth in memory — same walk as `build` — but don't
   write it anywhere yet.
2. Compare against the stored graph (`map_get()`) and report drift by name:
   modules that moved or vanished, issues marked closed but still edged as
   open work, decisions a later decision superseded. Drift is the point of
   this mode — name it, don't summarize it away.
3. Offer `map build` to reconcile. `diff` never writes; it only compares.

## `map status`

1. `map_get()` for counts by node/edge type.
2. Staleness: compare the stored graph against `git log -1` — how long
   since the graph was last rebuilt versus how long since the codebase last
   moved. A graph that's weeks behind the last commit is a graph nobody
   should trust yet; say that plainly.

## Fast lane

There isn't one — `map build` walks real sources and `map_set` validates
every patch, so there's no shortcut that skips the walk without also
skipping the honesty of the graph.
