# Dashboard Guide

> **Unofficial project:** Codex Usage Tracker is independent and is not made by, affiliated with, endorsed by, sponsored by, or supported by OpenAI. OpenAI and Codex are trademarks of OpenAI.

This guide uses synthetic aggregate data. The screenshots do not contain prompts, assistant text, tool output, or real Codex session content.

## Open The Dashboard

For the best experience, run the localhost dashboard server:

```bash
codex-usage-tracker setup
codex-usage-tracker update-pricing
codex-usage-tracker update-rate-card
codex-usage-tracker serve-dashboard --open
```

For optional allowance context, initialize a local template and copy values from Codex Usage or `/status`:

```bash
codex-usage-tracker init-allowance
codex-usage-tracker parse-allowance "5h 79% 6:50 PM Weekly 33% Jun 7"
```

To tune review thresholds locally, run `codex-usage-tracker init-thresholds` and edit `~/.codex-usage-tracker/thresholds.json`. This file is a JSON object keyed by recommendation threshold names such as `low_cache_ratio`, `high_context_percent`, and `high_cost_usd`; unknown keys are ignored. These thresholds control low-cache, high-context, high-uncached-input, large-thread, reasoning-spike, low-output, and high-cost recommendations.

To tune project attribution locally, run `codex-usage-tracker init-projects` and edit `~/.codex-usage-tracker/projects.json`. This file supports `aliases`, `ignored_paths`, and `tags`. The dashboard derives project name, relative cwd, branch, tags, and a hashed remote origin from aggregate `cwd` and local Git metadata when available.

Before sharing screenshots or generated artifacts, use `--privacy-mode redacted` or `--privacy-mode strict` before the subcommand:

```bash
codex-usage-tracker --privacy-mode strict serve-dashboard --open
codex-usage-tracker --privacy-mode strict dashboard --open
```

Redacted mode hides raw cwd/source paths, hides Git remote labels, and hashes unnamed projects while preserving configured aliases. Strict mode also hides project-relative cwd, Git branch, and tags. The dashboard header shows the active metadata mode.

`serve-dashboard` refreshes active-session logs before opening by default. Use `--no-refresh` only when you intentionally want a cached view of the existing local index.

The server keeps the HTML aggregate-only and enables two live features:

- `Refresh` rescans local Codex logs and updates the dashboard rows.
- `Load context` reads one selected model call from the original local JSONL file only when you ask for it.

For a static snapshot, use:

```bash
codex-usage-tracker open-dashboard
```

Static file mode can still filter, sort, and inspect aggregate call fields. `open-dashboard` refreshes before writing the snapshot unless you pass `--no-refresh`. Static files cannot refresh from logs or load raw context after opening; use `serve-dashboard` when you want those live controls.

The localhost server uses a random per-server token for refresh and context API calls, validates loopback `Host` and `Origin` headers, and can start with context loading off through `codex-usage-tracker serve-dashboard --no-context-api`.

## Insights View

![Insights view with ranked attention cards, investigation presets, and top threads by attention score.](assets/dashboard-insights.png)

The dashboard opens in `Insights` view. This view is designed to answer "what needs attention?" before you start sorting tables.

- `Needs Attention` cards rank costly threads, Codex allowance usage, low cache reuse, context bloat, unpriced usage, estimated pricing, and reasoning-output spikes from aggregate fields only.
- `Investigation Presets` apply a view, derived filter, sort order, and explanatory caption together.
- Presets include highest-cost threads, highest Codex credits, context bloat, cache misses, pricing gaps, and estimated-price review.
- The top table shows threads by attention score so you can jump from a summary signal into a thread timeline or selected call.
- Clear an active preset to return to normal manual filtering and sorting.

## Calls View

![Calls view showing filters, totals, the model-call table, and the details panel.](assets/dashboard-calls.png)

Use `Calls` view when you want to inspect individual model calls.

- The header stays compact: refresh controls on the right, and short status chips on the left. Exact refresh time, pricing source, and credit-rate source live in hover titles so live refreshes do not reflow the page.
- The top cards include cached input, uncached input, Codex credit usage, and optional usage remaining instead of estimated-token, unpriced-token, and price-coverage counters.
- The `Confidence` filter separates exact cost, estimated cost, unpriced cost, exact credit-rate matches, inferred credit mappings, user credit overrides, and missing credit rates.
- The `Time` filter supports all time, today, this week, last 7 days, this month, and custom calendar ranges. Presets are relative to your browser's local date. Custom ranges use inclusive start and end dates.
- The `History` control defaults to `Active sessions only`. Switch to `All history` only when you want live refresh to scan archived session logs and include any archived rows already present in SQLite.
- The URL tracks the active view, filters, time preset or custom range, sort, preset, selected row or thread, page, and expanded threads. `Copy link` copies that state so the same investigation can be reopened.
- `Export CSV` downloads the currently filtered aggregate calls. In Threads view, it exports the calls behind the filtered thread list rather than only the visible group headers.
- A `Parser warnings` chip appears only when the latest refresh reports skipped token events, missing expected token fields, invalid counters, duplicate cumulative snapshots, or unknown event shapes. Use `codex-usage-tracker inspect-log <path>` to inspect a suspect log without writing to SQLite.
- Search matches thread, cwd, model, session id, turn id, subagent role, and parent thread fields.
- Search also matches derived project names, project-relative cwd values, tags, branch names, and redacted remote labels.
- In redacted or strict privacy mode, search only sees the redacted metadata fields included in the dashboard payload.
- The cards summarize only the currently visible filtered rows.
- Time values are shown in your browser's local date/time format while sorting and time filtering still use the logged timestamp.
- Click a column header like `Time`, `Thread`, `Tokens`, `Cost`, or `Cache` to sort. Use the sort menu for `Highest Codex credits`. Click the same header again to reverse the direction.
- Hover or click a row to pin its aggregate fields in `Call Details`; on desktop, the details panel stays visible as you scroll.
- The `Call Details` panel groups primary cost, Codex credit, allowance, cache, context, and pricing signals first, then thread narrative and token breakdowns.
- The first detail section includes a recommended action and a "why flagged" explanation derived only from aggregate counters and pricing/allowance metadata.
- Raw aggregate identifiers and source file metadata are collapsed until you need them.
- The details panel always reserves a visible scrollbar so long field lists are discoverable before you start scrolling.
- Pagination appears only when the active Insights, Calls, or Threads view has more than one page.
- When served from localhost, `/api/usage` accepts `limit` and `offset` so automation can page aggregate rows without loading an entire large history.
- After you scroll down, the bottom-right `Top` button returns to the top of the dashboard.

Useful interpretation notes:

- `Last call total` is the token usage for the selected model call.
- `Session cumulative` is the running total Codex logged for that session at the time of that call.
- `Cached input` and `Uncached input` are split so cache behavior is visible without storing transcript text.
- A cost with `*` means the pricing row is marked as a best-guess estimate.
- Codex credits are estimated from aggregate input, cached-input, and output token counters. Direct model matches use the bundled OpenAI Codex rate-card snapshot; inferred labels are marked estimated, and local credit-rate overrides are marked user-provided.
- `Usage Remaining` is not read from the logged-in account plan. Configure `~/.codex-usage-tracker/allowance.json` with values copied from Codex Settings > Usage, the Codex Usage dashboard, or `/status` when you want current remaining allowance context.

## Threads View

![Threads view with one expanded thread and its calls in chronological order.](assets/dashboard-threads.png)

Use `Threads` view when you want to understand a work session as a group instead of one call at a time.

- Each thread row groups the filtered model calls by thread name, falling back to session id when no name is available.
- Thread rows show latest activity, call count, model mix, effort mix, total tokens, estimated cost, Codex credits, cache ratio, and signal count.
- Mixed model summaries prefer the primary non-review model; `codex-auto-review` appears as the thread model only for review-only threads.
- Click a thread row to expand or collapse its calls. Multiple thread rows can stay open.
- Expanded calls are ordered oldest to newest by event timestamp, then cumulative token count.
- Subagents with logged parent session ids are shown under the parent thread. Auto-review sessions without explicit parent ids may be attached by cwd and nearby activity and are marked as attached or inferred in the details.

The same search, time range, confidence status, load limit, cards, and sort controls apply in `Insights`, `Calls`, and `Threads` views.

## Details And Context

![Details panel showing aggregate fields for the selected usage row.](assets/dashboard-details.png)

The details panel is structured for progressive disclosure. On desktop, it sticks inside the viewport and scrolls internally when the selected call has more fields or loaded context than can fit on screen.

For selected calls, the panel shows:

- primary cost, Codex credits, allowance impact, cache, uncached input, context use, pricing status, and next action
- thread attachment, source, parent-thread, and timestamp narrative
- input, cached input, uncached input, output, reasoning output, cumulative tokens, pricing fields, credit model, credit confidence, and rate-card source metadata
- collapsed raw aggregate identifiers
- collapsed source JSONL file and line metadata

For selected threads, the panel shows:

- estimated cost, Codex credits, allowance impact, attention score, cache ratio, max context use, pricing status, and next action
- lifecycle signals: first expensive turn, largest cumulative jump, cache trend, context trend, and whether subagent or auto-review work appeared before a usage spike
- a compact thread timeline with recent calls, cost, credits, cache, context, and pricing cues
- direct, subagent, auto-review, attached-call, and spawned-thread relationship counts

When served from localhost, the details panel includes `Load context` and `Include tool output`.

- `Load context` fetches a size-limited, redacted context excerpt for only that call.
- `Include tool output` repeats the request with tool output included, still redacted and capped.
- Raw context is not written to SQLite, CSV, or the generated dashboard HTML.
- If the server was started with `--no-context-api`, context loading starts off. Use `Enable context loading` in the details panel when you want to allow explicit row actions without restarting the dashboard server.

## Practical Workflow

1. Start with `serve-dashboard --open`.
2. Leave `Live` enabled while you work, or click `Refresh` after a Codex run finishes.
3. Leave `History` on `Active sessions only` for current work. Switch to `All history` when you intentionally want archived sessions included in the live refresh.
4. Optionally run `parse-allowance` with copied values from Codex Usage or `/status`, or initialize and edit `allowance.json` manually.
5. Start in `Insights` view and review the highest-severity attention cards.
6. Narrow the `Time` filter when you are investigating a recent spike or a specific work window.
7. Use a preset when the question is already clear: highest-cost threads, highest Codex credits, context bloat, cache misses, pricing gaps, or estimated-price review.
8. Use `Threads` view to find the active work thread and any spawned subagent calls.
9. Sort by `Cost`, `Highest Codex credits`, `Tokens`, `Cache`, or `Context` when you need manual comparison.
10. Use `Copy link` when you want to return to the same filter/sort/selection state later.
11. Use `Export CSV` when the current filtered aggregate calls need spreadsheet review.
12. Click into a row and use `Load context` only when aggregate fields are not enough to explain the call.

## Investigating Long Chat Growth

Long-running Codex chats can carry a surprising amount of context into later turns. Prompt caching can reduce the cost of repeated input, but it does not make a large conversation free. Later calls may still include a large cached prefix, new uncached input, reasoning output, and tool-related context.

Use these dashboard fields together:

- `Cached input`: repeated context Codex was able to reuse.
- `Uncached input`: fresh context added by the current turn.
- `Session cumulative`: the running total Codex logged for the session.
- `Context use`: how much of the model's context window the call used.
- `Cache ratio`: whether the call is mostly reused context or mostly new input.

When a thread keeps growing but the old context is no longer helping, starting a fresh Codex thread may be more efficient than continuing to carry the same cached history forward.

## Privacy Model

The dashboard is designed to be shareable as an aggregate report, but only after you review it like any generated artifact.

It includes:

- session ids, thread names, cwd values, source file paths, timestamps, model labels, reasoning effort, token counts, cost estimates, Codex credit estimates, optional manually entered allowance windows, and derived ratios

It does not include:

- prompts, assistant responses, raw tool output, pasted secrets, message snippets, or transcript text

The screenshots in this guide are produced from synthetic fixture data used by the test suite.

Use `--privacy-mode redacted` or `--privacy-mode strict` before sharing generated dashboards, CSV exports, query JSON, or support bundles. Redacted mode removes raw cwd/source paths and hides unnamed project names behind stable hashes. Strict mode also hides project-relative cwd, branch, and tags. Configured project aliases are treated as explicit display opt-ins in both modes.

Remaining 5-hour and weekly allowance is not read from Codex logs or inferred from the logged-in account plan automatically. Add `~/.codex-usage-tracker/allowance.json` only when you want the dashboard to show current copied allowance state. Local Codex logs may also omit usage from other ChatGPT agentic surfaces that share the same allowance.

Archived sessions are excluded from dashboard payloads by default. The `All history` mode is an explicit opt-in because archived logs can make refreshes slower and can make current dashboards look inflated by older work.

Pricing and Codex credit estimates are source-stamped local calculations. Use `codex-usage-tracker pin-pricing --output <path>` when a report needs to keep the same USD pricing snapshot over time, and use `codex-usage-tracker update-rate-card` when you want an explicit local copy of the bundled Codex credit rate-card snapshot.
