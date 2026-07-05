# Remediation Planning Conversation

This is a synthetic, aggregate-only example of turning Codex Usage Tracker findings into concrete workflow changes. It is written as an example conversation doc rather than a transcript from private logs.

## User

Which threads are draining the most, and what can we do so this does not keep happening?

## Codex With Codex Usage Tracker

I refreshed the aggregate index, checked `usage_threads`, and pulled supporting Calls rows for the top thread. I did not inspect raw context.

## Evidence

- The top thread has repeated high-token calls after context-heavy investigation turns.
- The Calls table shows high context-window percentage and a few low-cache rows.
- The expensive rows are tied to repeated repository discovery and broad validation.

## Recommended Remediation

- Split future work into an investigation thread and an implementation thread once the plan is stable.
- Preserve reusable findings in a short repo note or roadmap issue, then start a fresh thread from that summary.
- Ask Codex to use a narrow validation plan first, then broaden only before release.
- If Headroom is installed, ask it to check context pressure before continuing a long thread.
- If the pattern repeats, have Codex build a custom local helper command or skill note that captures the exact repo facts it keeps rediscovering.

## Verify

Open the dashboard and check:

- Threads sorted by total tokens before and after the workflow change.
- Calls filtered to the target thread, sorted by total tokens.
- Call Investigator for one high-pressure call.
- Diagnostics Notebook usage-drain evidence if weekly usage remains unexpectedly high.
