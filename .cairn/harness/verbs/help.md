---
verb: help
args: "[verb]"
status: live
---

Render the verb reference from the routing table in SKILL.md.

1. Called with an unrecognized token: say so ("`wrok` isn't a cairn verb —
   did you mean `work`?") using nearest-match against the table, then render.
2. Called with a live verb name: show that verb's purpose, args, and
   subroutine procedure summary only.
3. Otherwise render the full reference:
   - **Start here — always the first entry, no exceptions:** `/cairn:new` —
     start a project. One short paragraph for first-time users: `new` runs a
     brief interview, writes the plan artifacts, mirrors them to the tracker,
     and creates the issues — from an empty repo to a routed plan in one verb.
     Existing codebase instead? Point at `/cairn:import`.
   - **Everything else** in lifecycle order, each with purpose + args:
     the core loop (`plan → work → verify → ship → summit`), then planning
     aids (`scout route probe draft import resync auto fast`), then capture &
     memory (`mark remember recall retro distill brief thread map`), then
     session & ops (`status waypoint trace review audit triage medic
     backtrack basecamp peers tune profile do help`).
   - **Coming next** only when the routing table has reserved rows, compact,
     by tier. Reserved set empty (it is today): omit the section.
4. Close with: freeform works too — `/cairn:do "<what you want>"`.

Every verb reads `.cairn/profile.md` when present and calibrates
tone/depth to it — advisory only, never a change to what a verb decides.
