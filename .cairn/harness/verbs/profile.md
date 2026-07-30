---
verb: profile
args: "(interview-lite)"
status: live
---

A developer profile — how you talk, what you already know, what you'd
rather not re-explain every session. Advisory only: it calibrates tone and
depth for every other verb, never what those verbs decide to do.

**No tools.** This verb writes `.cairn/profile.md` directly — there is no
`profile_*` tool, no tracker object, and nothing else in the system
mutates the file. It's a file on disk, not workflow state.

## Infer first, ask only what's left

1. Read the repo before asking anything: `README.md`, `CONTRIBUTING.md`,
   linter/formatter configs, commit message style from recent `git log`,
   test framework choice, and the languages actually in use. This is real
   evidence about conventions — don't overwrite it with a guess.
2. Read recent session activity — the .cairn/ session and audit files,
   recent `LEDGER.md` entries, prior probe/trace resolutions — for signal
   on how detailed this person likes explanations, whether they push back
   on process, and what they already clearly understand vs. what tripped
   them up before.
3. Whatever the repo and the session history can't answer, ask — one
   batched `AskUserQuestion`, not a checkbox at a time. Typical gaps:
   preferred verbosity, whether they want the "why" spelled out or just
   the "what," and any hard no-gos (a library they won't use, a pattern
   they're tired of seeing suggested).
   When `user.mode` is unset in cairn.json, fold the vibe/engineer mode
   choice into the same batch (writes via `config_set`, not the profile
   file — mode is workflow state, not tone calibration).
4. Never ask something the repo already answered. If the commit history
   is clearly terse and lowercase, that's the convention — confirming it
   out loud just spends a question the interview didn't need to spend.

## `.cairn/profile.md` sections

- **communication** — verbosity preference, tone (terse vs. explain-the-why),
  how they like bad news delivered (straight, no cushioning vs. some
  context first).
- **expertise** — languages/frameworks they're fluent in (skip the
  explainer), areas they've flagged as unfamiliar (slow down, spell it
  out).
- **conventions** — commit style, naming, formatting, test framework —
  whatever `git log` and the repo's own config already prove.
- **cadence** — how often they want checkpoints, whether they prefer one
  big batch of questions or short frequent check-ins, timezone/availability
  notes if volunteered.

Each section is inferred-or-asked, never invented — an empty section
beats a guessed one.

## Advisory only

Every other verb that talks to the user reads `.cairn/profile.md` when
present and calibrates tone/depth accordingly — nothing more. It never
changes what `plan` researches, what `work` builds, or what `audit`
flags. A profile that says "keep it terse" shortens the prose around a
finding; it does not shorten the finding.

Missing file is the default state, not an error — every verb works
exactly as it does today until `profile` is run once.
