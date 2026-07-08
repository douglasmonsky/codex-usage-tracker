# Token Waste Review Conversation

This is a synthetic, aggregate-only example using the Codex Usage Tracker companion skill. It does not include prompts, assistant messages, tool output, pasted secrets, raw transcript text, real thread names, or real usage totals.

## User

Look through my usage for token waste and recommend what I should change.

## Codex

I refreshed the local aggregate index and started with `usage_investigate(goal="token_waste")`, then checked the recommended supporting Calls and Threads rows.

## Evidence

- One long implementation thread accounts for most recent tokens.
- Several calls have high input tokens and low cached input, which means repeated context was not reused efficiently.
- The highest-confidence finding points to broad file discovery and repeated validation as the main waste pattern.

## Likely Waste Pattern

Codex is rediscovering project context and rerunning broad checks in the same workstream. The dashboard evidence to inspect next is Calls sorted by total tokens, then the top thread in Threads, then the highest-pressure record in Call Investigator.

## Next Actions

- Use Calls to open the top three expensive rows.
- Follow the investigation report's `recommended_next_tools` before drilling into raw context.
- If Headroom is available, use it to estimate whether the thread is near context pressure before continuing.
- Move stable project facts into docs or an `AGENTS.md` note so Codex does not need to infer them repeatedly.
- Create a repo-specific validation command or test-selection checklist if broad checks are happening every turn.

## Verify

After the next few sessions, compare Threads total tokens, Calls cache ratio, and Diagnostics Notebook usage-drain evidence against the previous window.
