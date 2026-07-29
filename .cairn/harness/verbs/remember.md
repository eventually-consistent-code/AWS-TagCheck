---
verb: remember
args: "\"<fact>\" [--type decision|constraint|gotcha|reference]"
status: live
---

Store knowledge per the `cairn-memory` skill (it owns what deserves a card).

1. Judge the content per the skill: one durable fact → memory card; bulk
   material (tool output, fetched docs, research dumps) → index.
2. Card path: `mem_card_create(type: <flag or judged>, body: <fact>,
   scopePhase/scopeIssue: from context_get, provenanceFiles/provenanceCommits:
   the files and commits the fact is about, when known)`. Cards are
   git-committed — remind the user they ship with the repo.
3. Bulk path: `mem_index(content, source, phase/issueId from context)`.
4. Confirm what was stored, where (card id or index), and its scope.
