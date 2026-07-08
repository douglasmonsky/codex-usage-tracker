# Agentic MCP And Skill Roadmap

Codex Usage Tracker has moved from static usage summaries toward local investigation tools that can help an AI analyst find waste, explain allowance evidence, and suggest concrete fixes. The next step is to make that experience intentional: agents should start from user goals, choose the right tracker endpoints, and return clear evidence-backed recommendations instead of making users pick from a long MCP tool catalog.

## Product Stance

- Local-first and unofficial remain non-negotiable.
- Aggregate reports stay the default for normal usage answers.
- Content-index tools remain explicit local investigation tools and must label when indexed snippets or local fragments can appear.
- Remediation should be first-class: every investigation should make it clear what to do next and how to verify whether the change helped.
- The MCP should help the model drive the tracker, but it should not claim access to OpenAI's internal ledger or account-wide usage outside local Codex logs.

## Target Experience

Users should be able to ask questions like:

- "Look through my usage for token waste."
- "Did my weekly allowance change?"
- "Why is my 5-hour counter weird?"
- "What should I fix first?"
- "Where am I rediscovering the same files?"
- "Which calls are big but low value?"

The agent should then:

1. Refresh or check local index freshness.
2. Pick an investigation plan.
3. Use stable MCP/API reports.
4. Return findings with confidence and caveats.
5. Recommend concrete workflow/tooling changes.
6. Offer a verification path using dashboard rows, call investigator links, or follow-up MCP reports.

## Payload Shape

New agent-facing report payloads should converge on:

- `goal`: the user intent or investigation kind.
- `summary`: top finding, evidence count, confidence, privacy mode, data scope.
- `findings`: normalized rows with `finding`, `evidence`, `confidence`, `why_it_matters`, `recommended_action`, `verify_with`, and `privacy_notes`.
- `recommended_next_tools`: MCP calls the agent can use when the answer needs more detail.
- `caveats`: limits such as stale index, missing pricing, missing allowance observations, archived sessions excluded, or outside usage possible.

## Logical Units

### Unit 1: Roadmap And Direction

- Add this roadmap.
- Keep existing behavior unchanged.
- Use it as the reference for the next code PRs.

### Unit 2: Agentic Investigation Orchestrator

Add new MCP/API reports:

- `usage_suggest_investigations(...)`
  - Returns suggested investigations based on available local data and optional user goal.
  - Does not require raw context.
  - Suggestions should include which tool to call, why it matters, default parameters, and privacy caveats.

- `usage_investigate(...)`
  - Takes a goal such as `token_waste`, `allowance_change`, `cache_failure`, `workflow_churn`, or `overview`.
  - Chains existing report builders instead of duplicating analysis logic.
  - Returns a compact evidence-backed answer payload using the target shape above.

Initial goals:

- `token_waste`: combine large low-output calls, shell churn, repeated file rediscovery, report pack, and high-token calls.
- `allowance_change`: route to weekly allowance diagnostics and strict export when sharing is likely.
- `cache_failure`: use high-token calls, cache ratio, context-window percent, and large low-output evidence.
- `workflow_churn`: use shell churn and repeated file rediscovery.
- `overview`: use status, summaries, recommendations, and report pack evidence.

### Unit 3: Skill Makeover

Rewrite `codex-usage-api` around user intents:

- Start with a small "intent router" instead of a long tool list.
- Prefer `usage_investigate(...)` for broad goals.
- Prefer `usage_suggest_investigations(...)` when the user asks for ideas.
- Keep explicit privacy boundaries for raw context and content search.
- Teach remediation structure: `Evidence`, `Likely waste pattern`, `Next action`, `How to verify`.
- Mention Headroom and custom local automation only as conditional recommendations when evidence supports them.

### Unit 4: Documentation And Examples

- Update MCP docs to present agentic entrypoints first.
- Keep the full tool catalog, but make it secondary.
- Add one or two concise example prompts and response-shape notes.
- Update JSON schema docs for new payload contracts.

### Unit 5: Release Readiness

- Add contract tests for the two new payloads.
- Add MCP release-list tests for the new tools.
- Run focused tests, full Python test suite, release checker, and package build before release.
- Ship as the next minor release after the already-published `0.16.0`, likely `0.16.1` if treated as follow-up MCP polish or `0.17.0` if positioned as the agentic MCP release.

## Non-Goals For This Pass

- No new database schema.
- No raw prompt/tool-output export.
- No hosted data collection.
- No dashboard redesign.
- No replacement for existing specific diagnostic tools.
- No claim that allowance diagnostics can read OpenAI's internal ledger.
