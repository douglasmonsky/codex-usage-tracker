# CK-16 — Publish public documentation and release

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Explain and release the clean agent-first product with compelling
examples and exact artifact evidence.

**Why:** The public should understand the pivot, setup magic, supported
questions, evidence/grade discipline, and future direction.

**Controls:** CK-14 (and CK-15 only if selected), release policy.
**Dependencies:** CK-14.

**Scope and expected files:**

- README hero, badges, agent-install copy/paste prompt, product narrative;
- setup guide, conversation examples, supported/deferred/unsupported guide;
- screenshots or native artifact captures from synthetic data only;
- Data Analytics recommendation and optional handoff;
- gradual naming language that preserves “Codex Usage Tracker” discovery;
- changelog, version, release notes, exact release evidence.

**Schema/API changes:** None except final version constants.
**Non-goals:** Abrupt repository/package/plugin rename, unsupported feature
claims, hosted/Claude launch.

**Invariants:** Every screenshot/example matches the exact installed candidate;
no Console imagery after retirement; install commands use public artifacts;
release built once from merged main/tag through protected workflow.

**Tests/benchmarks:** Link/command/docs checks, exact protected build and
distribution checks, pre-publication clean-install smoke of the downloaded
workflow artifacts, post-publication public-index download/install smoke,
fresh CLI/Desktop prompts, synthetic image inspection, and
package/DB/response ratchets.

**Acceptance:** Public page makes purpose/value/setup clear; artifact
hashes/sizes and public URLs recorded; byte-identical public install smoke
passes; no authority doc remains “planned” for implemented behavior.

**Failure/rollback:** Do not publish. Correct docs/artifacts on a focused branch.
After publication, use a normal patch release; never mutate artifacts.

**Cleanup/docs:** Mark roadmap release evidence and future CK-15/Claude items
appropriately.

**Suggested commits:**

1. `docs: explain the agent-first usage kernel`
2. `chore: prepare clean-cutover release`
