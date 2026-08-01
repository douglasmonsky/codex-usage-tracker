# CK-13-02 — Switch public entry points

**Status:** Blocked on CK-13-01

**Parent:** CK-13 umbrella

**Recommended owner:** `feature_worker entrypoint-cutover`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Make the qualified replacement the candidate default CLI/plugin/MCP
path using only the frozen allowlist.

**Why:** Entry-point mutation is bounded implementation and should not own its
approval or deletion decision.

**Controls:** CK-13-01 manifest and CK-12 exact candidate.

**Dependencies:** CK-13-01 merged and exact-main verified.

**Owned files/interfaces:** Named entry-point/configuration files and focused
smoke tests; no legacy deletion.

**Produces:** Candidate cutover configuration.

**Independent truth source:** Exact installed candidate and synthetic
question/setup oracle.

**Consumer seam:** Default CLI/MCP/plugin to application service and separate
database.

**Parallelism:** Serialized entry-point lock.

**Non-goals:** Legacy deletion, schema migration, dual-write, new public
contracts, release.

**Invariants:** No old database open, no spike import/fallback, exact catalog,
separate cache/database, rollback bytes untouched.

**Required tests/checks:** Clean install, two MCP processes, setup/query/evidence
smokes, path/database isolation, `just v/vc`.

**Acceptance:** Default candidate path uses only the qualified replacement and
all cutover smokes pass.

**Failure/rollback:** Revert entry-point selection and reinstall/select 0.28.

**Handoff:** Diff, hashes, smoke results to CK-13-03.

**Cleanup/docs:** No authority status change until verification.

**Suggested commit:** `feat: select agent kernel entry points`
