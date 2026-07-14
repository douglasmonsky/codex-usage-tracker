# Token Waste Review Conversation

This synthetic, aggregate-only example uses the Codex Usage Tracker companion skill. It does not include prompts, assistant messages, tool output, pasted secrets, raw transcript text, real thread names, or real usage totals.

## User

Look through my usage for token waste and recommend what I should change.

## Codex

I refreshed the local aggregate index and started a Compression Lab run with `usage_compression_start(include_archived=false)`. After polling `usage_compression_status`, I read `usage_compression_profile`, paged the top `usage_compression_candidates`, inspected one selected candidate with `usage_compression_candidate_detail(evidence_mode="handles")`, and simulated the candidate with `usage_compression_simulate`. I did not inspect raw context.

## Evidence

- One long implementation thread accounts for most recent tokens.
- Several calls have high input tokens and low cached input, which suggests repeated context was not reused efficiently.
- The strongest Compression Lab candidate points to repeated context and file rediscovery as the main waste pattern.

## Likely Waste Pattern

Codex is rediscovering project context and rerunning broad checks in the same workstream. The dashboard evidence to inspect next is Calls sorted by total tokens, the top thread in Threads, and the highest-pressure record in Call Investigator.

## Next Actions

- Use Calls to open the top three expensive rows.
- Follow the Compression Lab candidate detail and simulation before drilling into raw context.
- If Headroom is available, use it to estimate whether the thread is near context pressure before continuing.
- Move stable project facts into docs or an `AGENTS.md` note so Codex does not need to infer them repeatedly.
- Create a repo-specific validation command or test-selection checklist if broad checks are happening every turn.

## Verify

After the next few sessions, compare Threads total tokens, Calls cache ratio, and Diagnostics Notebook usage-drain evidence against the previous window.
