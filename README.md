# Codex Usage Tracker

Local-first analytics for Codex token usage.

> **Unofficial project:** Codex Usage Tracker is an independent open-source project. It is not made by, affiliated with, endorsed by, sponsored by, or supported by OpenAI. OpenAI and Codex are trademarks of OpenAI; this project only reads local log files from your machine.

Codex Usage Tracker reads the JSONL logs already written by Codex, indexes aggregate usage counters into SQLite, and gives you a dashboard, CLI, and MCP tools for understanding where tokens and Codex usage credits are going. It is built for investigating real usage patterns while keeping prompts, assistant messages, tool output, and pasted secrets out of the stored index and generated dashboard HTML.

## Dashboard Preview

The dashboard opens with an insight-first summary that ranks threads and calls needing attention before you start sorting tables.

![Insights view with ranked Needs Attention cards, investigation presets, and top threads by attention score.](docs/assets/dashboard-insights.png?v=47d58ee)

![Calls view with filters, totals, model-call rows, and the details panel.](docs/assets/dashboard-calls.png?v=47d58ee)

![Threads view with grouped Codex threads and expanded chronological calls.](docs/assets/dashboard-threads.png?v=47d58ee)

![Call Details panel showing aggregate token, pricing, Codex credit, allowance, context, and thread attachment fields.](docs/assets/dashboard-details.png?v=47d58ee)

These screenshots use synthetic aggregate fixture data. They do not contain prompts, assistant responses, tool output, or real Codex session content.

## Why Use It

Use this when you want to answer questions like:

- Which Codex threads are using the most tokens or estimated cost?
- Which threads and calls are consuming the most Codex usage credits?
- Which models and reasoning efforts are driving usage?
- Do long-running chats get more expensive over time?
- Are subagents, auto-reviews, or review passes attached to the right parent work?
- Which calls have low cache reuse, high context-window pressure, or large reasoning output?
- Which projects, project tags, or active directories are consuming the most usage?
- Did a change in workflow, model choice, or reasoning mode improve efficiency?

The dashboard is intentionally split into three views:

- `Insights`: start with ranked issues, investigation presets, and top threads by attention score.
- `Calls`: inspect individual model calls, token fields, Codex credit estimates, pricing status, cache ratio, reasoning output, and context-window percentage.
- `Threads`: group calls by Codex thread, expand a thread chronologically, and see spawned subagents, inferred auto-review work, and credit growth in context.

## Important Pattern: Long Chats Can Bloat Fast

A common pattern this tool makes obvious is that staying in the same Codex chat for a long time can rapidly grow the context carried into later turns.

Prompt caching helps, but cached input is not the same as no input. Long threads can accumulate a large cached context, and each new turn may still include a large amount of cached input plus new uncached input, reasoning output, and tool-related context. That can make usage climb quickly even when the visible user request looks small.

Watch these fields when investigating that pattern:

- `Cached input`: how much previously seen context was reused.
- `Uncached input`: how much fresh context was added for the call.
- `Session cumulative`: how large the running session total has become.
- `Context use`: how much of the model context window the call consumed.
- `Cache ratio`: useful for spotting whether a thread is mostly reused context or mostly new context.

Practical takeaway: when old context is no longer relevant, starting a fresh thread can be more efficient than dragging a large cached history forward. This is not a rule for every task, but it is one of the clearest usage patterns the dashboard is designed to reveal.

## What It Does

- Reads local Codex JSONL logs from `~/.codex/sessions/**/*.jsonl`.
- Optionally includes `~/.codex/archived_sessions/*.jsonl`.
- Stores aggregate-only usage metrics in local SQLite at `~/.codex-usage-tracker/usage.sqlite3`.
- Exposes MCP tools for refresh, summaries, session detail, lazy call context, CSV export, and dashboard generation.
- Generates a static hoverable dashboard with insight summaries, flat calls, and threaded-by-thread views.
- Can serve the dashboard from localhost so raw logged context is loaded only after a row action.
- Provides a read-only doctor command for local plugin/MCP setup checks.
- Optionally estimates costs from a local pricing file that can be refreshed from OpenAI's published pricing docs.
- Estimates Codex usage credits from aggregate token counters and a bundled OpenAI Codex rate-card snapshot.
- Optionally displays local 5-hour and weekly allowance windows copied from Codex Usage or `/status`.
- Tracks aggregate subagent metadata, including explicit parent session ids when Codex logs them.

The tracker intentionally does not store prompts, assistant messages, tool outputs, pasted secrets, or raw transcript snippets in SQLite, CSV exports, or generated dashboard HTML. The optional localhost server can read redacted, size-limited context from the original JSONL file on demand.

## Quick Install

### Let Codex Install It

Open a Codex session on your machine and paste this:

```text
Install and configure Codex Usage Tracker from https://github.com/douglasmonsky/codex-usage-tracker.
Use pipx if it is available. If pipx is missing, install it with Homebrew or use a local virtual environment.
After installation, run codex-usage-tracker setup and serve-dashboard --open.
Verify the dashboard opens locally and tell me the dashboard URL plus whether I need to restart Codex for plugin discovery.
```

Codex should run roughly:

```bash
brew install pipx
pipx ensurepath
pipx install "git+https://github.com/douglasmonsky/codex-usage-tracker.git"
codex-usage-tracker setup
codex-usage-tracker serve-dashboard --open
```

Restart Codex after `install-plugin` if you want Codex to discover the plugin tools in a fresh session. The localhost dashboard can run immediately.

### Manual Install

Run:

```bash
brew install pipx
pipx ensurepath
pipx install "git+https://github.com/douglasmonsky/codex-usage-tracker.git"
codex-usage-tracker setup
codex-usage-tracker serve-dashboard --open
```

`setup` installs or refreshes the package-owned plugin wrapper, initializes a local pricing template when pricing is missing, refreshes the aggregate index, runs `doctor`, prints a success/failure summary, and tells you whether Codex needs a restart for plugin discovery.

`install-plugin` is still available when you only want plugin registration. It creates `~/plugins/codex-usage-tracker`, writes a package-owned `.mcp.json` that points at the installed Python executable, and updates `~/.agents/plugins/marketplace.json`. Restart Codex after registration so it discovers the plugin.

## Fastest Useful Workflow

```bash
codex-usage-tracker update-pricing
codex-usage-tracker update-rate-card
codex-usage-tracker setup
codex-usage-tracker serve-dashboard --open
```

Then:

1. Leave `Live` enabled while working, or click `Refresh` after a Codex run finishes.
2. Start in `Insights` view and scan the `Needs Attention` cards.
3. Optionally run `codex-usage-tracker parse-allowance "5h 79% 6:50 PM Weekly 33% Jun 7"` with values copied from Codex Usage or `/status`.
4. Use an investigation preset when you already know the question: highest-cost threads, highest-credit calls, context bloat, cache misses, pricing gaps, or estimated-price review.
5. Open `Threads` view to find the active work thread and any spawned subagent or auto-review calls.
6. Expand an expensive or high-credit thread and read calls oldest to newest.
7. Hover or click rows to inspect exact aggregate fields in `Call Details`.
8. Use `Load context` only when the aggregate fields are not enough; context is fetched on demand from the local source JSONL and is not saved into SQLite or the dashboard.

For a screenshot-driven walkthrough, see [`docs/dashboard-guide.md`](docs/dashboard-guide.md).
Generated dashboards also link to a bundled local HTML copy of the guide. Set `CODEX_USAGE_TRACKER_DOCS_URL` if you want generated dashboards to point at a hosted docs page instead.
For codebase boundaries and extension rules, see [`docs/architecture.md`](docs/architecture.md).

## Development Setup

```bash
git clone https://github.com/douglasmonsky/codex-usage-tracker.git
cd codex-usage-tracker
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
codex-usage-tracker install-plugin --python .venv/bin/python
```

## Usage

Refresh the local aggregate index:

```bash
codex-usage-tracker refresh
```

Check setup:

```bash
codex-usage-tracker doctor
codex-usage-tracker doctor --suggest-repair
codex-usage-tracker --version
python -m codex_usage_tracker --version
```

Run or refresh local lifecycle tasks:

```bash
codex-usage-tracker setup
codex-usage-tracker upgrade-plugin
codex-usage-tracker uninstall-plugin
codex-usage-tracker reset-db --yes
codex-usage-tracker support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

`support-bundle` writes package, Python, OS, doctor, database schema, parser diagnostics, pricing status, and allowance status. It does not include raw logs, prompts, assistant messages, tool output, or context text.

Inspect a single Codex log without writing to SQLite:

```bash
codex-usage-tracker inspect-log ~/.codex/sessions/YYYY/MM/DD/rollout-...jsonl
codex-usage-tracker inspect-log ~/.codex/sessions/YYYY/MM/DD/rollout-...jsonl --json
```

`inspect-log` reports the parser adapter, aggregate token-count events, session ids, models, and parser diagnostics. It does not store raw prompts, assistant messages, tool output, or transcript snippets.

Rebuild the local aggregate index after parser or schema changes:

```bash
codex-usage-tracker rebuild-index
```

`rebuild-index` clears only the local aggregate `usage_events` and refresh metadata tables, then rescans local Codex logs.

Generate the local dashboard:

```bash
codex-usage-tracker dashboard --open
codex-usage-tracker open-dashboard
```

Serve the dashboard with live aggregate refresh and lazy raw-context loading:

```bash
codex-usage-tracker serve-dashboard --open
codex-usage-tracker serve-dashboard --no-context-api --open
```

When served this way, the dashboard gets a `Refresh` button plus a `Live` toggle that polls the localhost `/api/usage` endpoint every 10 seconds while the tab is visible. Refresh calls and `/api/context` require a random per-server token embedded in that generated dashboard, and the server rejects non-loopback `Host` or cross-origin `Origin` headers. Each poll refreshes the SQLite aggregate index from local Codex logs and replaces the in-memory dashboard rows without embedding raw transcript content. Use the `Load` selector to fetch 5,000, 10,000, 20,000, or all aggregate calls; `--limit 0` also means all calls for CLI-generated dashboards. The table renders 500 rows or thread groups per page so larger histories remain responsive. Each call detail panel also gets a `Load context` action when the context API is enabled. Pressing it fetches only that call's logged turn context from the original local JSONL source. Tool output is omitted by default; the `Include tool output` action loads redacted, size-limited tool output for that call. None of this raw context is written to SQLite, CSV, or the generated HTML.

`serve-dashboard --context-api explicit` is the default and keeps context loading as an explicit per-row action. `serve-dashboard --no-context-api` or `--context-api disabled` serves live aggregate refresh while disabling `/api/context` entirely.

Dashboard behavior:

- The `Insights` view opens first with ranked attention cards, investigation presets, and top threads by attention score.
- Top cards include cached input, uncached input, Codex credit usage, and optional usage remaining, replacing the older estimated-token, unpriced-token, and price-coverage cards.
- The `Confidence` filter separates exact configured cost, estimated cost, unpriced cost, exact credit-rate matches, inferred credit mappings, user credit overrides, and missing credit rates.
- Filter, sort, active view, active preset, selected row/thread, current page, and expanded threads are reflected in the URL so a copied dashboard link can reopen the same investigation state.
- `Copy link` copies the current dashboard state. `Export CSV` downloads the currently filtered aggregate calls, including the rows behind a filtered Threads view.
- The flat `Calls` view is available for inspecting individual model calls.
- The `Threads` view groups filtered calls by thread, shows the most recently active thread first by default, and lets multiple threads stay expanded.
- Investigation presets can jump directly to highest-cost threads, highest Codex credits, context bloat, cache misses, pricing gaps, or estimated-price review.
- Cost cells show both USD estimates and Codex credit estimates when a model maps to the rate card.
- The details panel groups primary cost/cache/context/allowance signals first, then thread narrative, token/pricing breakdowns, and collapsed raw aggregate metadata.
- Call details include a recommended action and a "why flagged" explanation derived only from aggregate counters and pricing/allowance metadata.
- Thread details include lifecycle signals such as first expensive turn, largest cumulative jump, cache trend, context trend, and whether subagent or auto-review work appeared before a usage spike.
- Parser diagnostics from the latest refresh are surfaced as a compact warning when the parser sees drift, missing expected token fields, invalid counters, duplicate cumulative snapshots, or unknown event shapes.
- Expanded thread calls are ordered oldest to newest so you can see how usage grew across the conversation.
- Spawned subagents with logged parent sessions are shown under their parent thread when Codex logs enough metadata.
- Auto-review sessions do not currently log an explicit parent session id, so the dashboard can infer attachment by cwd and nearby activity and marks that relationship in the details panel.
- Mixed thread model summaries prefer non-review models; `codex-auto-review` is shown as the thread model only for review-only threads.

Useful investigations:

- Sort `Threads` by `Tokens` or `Cost` to find the conversations worth reviewing first.
- Sort by `Highest Codex credits` to find calls or threads consuming the most usage allowance.
- Sort by `Cache` to find threads that are mostly new context versus mostly reused context.
- Sort by `Context` to find calls approaching the model context window.
- Filter by model or reasoning effort to compare usage patterns across model choices.
- Use `summary --preset by-subagent-role` to see whether delegated work is driving a large share of usage.
- Use `expensive --limit 10` for a quick CLI list of the highest-cost calls.
- Use `query` when you need stable JSON for automation across project, model, effort, thread, pricing, token, or credit filters.

Show a summary:

```bash
codex-usage-tracker summary --group-by model
codex-usage-tracker summary --group-by project
codex-usage-tracker summary --group-by project_tag
codex-usage-tracker summary --group-by thread --limit 20
codex-usage-tracker summary --preset today
codex-usage-tracker summary --preset last-7-days
codex-usage-tracker summary --preset expensive
codex-usage-tracker summary --preset by-subagent-role
codex-usage-tracker expensive --limit 10
codex-usage-tracker pricing-coverage
```

Query aggregate rows as JSON:

```bash
codex-usage-tracker query --since 2026-06-01 --project codex-usage-tracker --min-credits 1
codex-usage-tracker query --pricing-status unpriced --limit 0
codex-usage-tracker summary --group-by model --json
codex-usage-tracker session <session-id> --json
```

See [`docs/cli-json-schemas.md`](docs/cli-json-schemas.md) for the stable CLI and MCP JSON payload shapes and error codes.

Show one session:

```bash
codex-usage-tracker session <session-id>
```

Load one call's logged context on demand:

```bash
codex-usage-tracker context <record-id>
```

Export CSV:

```bash
codex-usage-tracker export --output usage.csv
codex-usage-tracker export --output usage.csv --limit 0
```

Enable optional cost estimates:

```bash
codex-usage-tracker update-pricing
```

This fetches OpenAI text-token pricing from `https://developers.openai.com/api/docs/pricing.md`, parses the selected tier, and writes a source-stamped local cache to `~/.codex-usage-tracker/pricing.json`. The default tier is `standard`; other supported tiers are `batch`, `flex`, and `priority`. If a pricing file already exists, the updater leaves a timestamped `.bak` copy next to it before replacing the active cache.

The updater also includes marked best-guess estimates for Codex labels that are not finalized in the public pricing table. `codex-auto-review` uses OpenAI's published `codex-mini-latest` Codex pricing from `https://openai.com/index/introducing-codex/`: `$1.50` per 1M input tokens, a 75% prompt-cache discount (`$0.375` per 1M cached input tokens), and `$6.00` per 1M output tokens. `gpt-5.3-codex-spark` is listed by OpenAI as a research preview with non-final Codex rates, so the tracker estimates it as `gpt-5.3-codex` at `$1.75` per 1M input tokens, `$0.175` per 1M cached input tokens, and `$14.00` per 1M output tokens. Use `--no-estimates` when you want only pricing rows parsed from the OpenAI pricing table.

For reproducible historical reports, pin the current pricing cache and pass the pinned file later:

```bash
codex-usage-tracker pin-pricing --output ~/.codex-usage-tracker/pricing-2026-06-05.json
codex-usage-tracker dashboard --pricing ~/.codex-usage-tracker/pricing-2026-06-05.json
```

For a manual template instead:

```bash
codex-usage-tracker init-pricing
```

Edit `~/.codex-usage-tracker/pricing.json` with USD-per-million-token rates for any local overrides or models that are not present in the OpenAI pricing table. Normal reports never contact the network; only `update-pricing` refreshes the local pricing cache.

Enable optional allowance context:

```bash
codex-usage-tracker init-allowance
codex-usage-tracker parse-allowance "5h 79% 6:50 PM Weekly 33% Jun 7"
```

Edit `~/.codex-usage-tracker/allowance.json` with the 5-hour and weekly remaining values you see in Codex Settings > Usage, the Codex Usage dashboard, or `/status` during an active CLI session, or use `parse-allowance` to update those windows from pasted text. The tracker can store `remaining_percent`, `reset_at`, `remaining_credits`, and `total_credits` for each window. If `total_credits` is present, call and thread details show the estimated share of that allowance; otherwise the dashboard shows the copied remaining percentages and reset context.

Enable optional recommendation threshold overrides:

```bash
codex-usage-tracker init-thresholds
```

Edit `~/.codex-usage-tracker/thresholds.json` to adjust the aggregate-only thresholds used for low cache reuse, high context pressure, high uncached input, large cumulative threads, reasoning-output spikes, large low-output calls, and high estimated cost. The dashboard uses these values for presets, insight cards, row recommendations, and thread lifecycle summaries.

Enable optional project aliases, ignored paths, and tags:

```bash
codex-usage-tracker init-projects
```

Edit `~/.codex-usage-tracker/projects.json` to map stable project hashes, repo roots, or project names to friendlier aliases, ignored paths, and tags. The tracker derives project identity from `cwd` and local Git metadata when available: repo root, repo name, current branch, and a hashed remote origin. It does not store or display the full remote URL.

Protect project metadata in shared artifacts:

```bash
codex-usage-tracker --privacy-mode redacted dashboard --open
codex-usage-tracker --privacy-mode strict export --output usage-redacted.csv
codex-usage-tracker --privacy-mode strict query --since 2026-06-01
```

`--privacy-mode` is a global option, so place it before the subcommand. `normal` keeps local project metadata visible. `redacted` hides raw `cwd` and source paths, hides Git remote labels, and replaces unnamed projects with stable hashed labels such as `Project ab12cd34`; configured project aliases are treated as explicit display opt-ins. `strict` also hides project-relative cwd, Git branch, and project tags. Dashboard payloads and support bundles include the active mode so screenshots and support artifacts make their metadata posture visible.

Credit usage estimates are calculated from Codex's aggregate input, cached-input, and output token counters using the bundled OpenAI Codex rate-card snapshot from `https://help.openai.com/en/articles/20001106-codex-rate-card` and `https://developers.openai.com/codex/pricing`. Direct model matches are marked exact. Local aliases and inferred labels, such as code-review usage mapped to GPT-5.3-Codex, are marked estimated. Local `credit_rates` overrides are marked `user_override`. Normal reports do not contact the network for allowance or credit estimates.

To copy the bundled source-stamped rate card into a local snapshot, run:

```bash
codex-usage-tracker update-rate-card
```

The local snapshot is written to `~/.codex-usage-tracker/rate-card.json`. Each bundled rate and alias includes source URL, fetched date, tier, confidence, and alias rationale where applicable. Use `--source-file` only when you have a reviewed replacement JSON snapshot you want the tracker to validate and use.

### Usage And Allowance Accuracy

`Codex Credits` is a calculated usage number, not a made-up dashboard unit. The tracker uses Codex's logged aggregate token counters and the official Codex rate card to estimate credits consumed by local Codex calls. Rows with a direct model match are the highest-confidence numbers; inferred aliases, research-preview models, fast-mode behavior, or workspace-specific exceptions should be treated as estimates.

`Usage Remaining` is different. The tracker cannot currently read your logged-in ChatGPT plan, live remaining credits, reset windows, or usage from other agentic surfaces automatically. A plan name such as Free, Plus, or Pro can provide context, but it is not enough to know the current remaining allowance. The dashboard shows exact-looking remaining values only when you copy them into `~/.codex-usage-tracker/allowance.json`.

To configure the usage component:

1. Run `codex-usage-tracker parse-allowance "5h 79% 6:50 PM Weekly 33% Jun 7"` with your current copied values.
2. Or run `codex-usage-tracker init-allowance` and open `~/.codex-usage-tracker/allowance.json`.
3. Copy the current `remaining_percent` and `reset_at` values from Codex Settings > Usage, the Codex Usage dashboard, or `/status`.
4. Add `remaining_credits` and `total_credits` only if your plan or workspace exposes exact credit numbers.
5. Leave fields as `null` when you do not have a trustworthy value; the dashboard will still show credits used, but it will not pretend to know remaining allowance.

## Current Limitations

- This is a sidecar dashboard and plugin, not a native Codex chat overlay. Native hover tooltips inside Codex chat would require a transcript UI extension point that is not part of this v1 surface.
- Token counts come from Codex's logged counters. The tracker does not re-tokenize prompts or reconstruct usage from raw text.
- Pricing is optional and local. Rows are unpriced when no matching model rate is configured, and some Codex-specific labels may use marked best-guess estimates.
- Pricing can change after a report is generated. Use `pin-pricing` and pass the pinned file with `--pricing` when you need reproducible historical cost estimates.
- Project metadata can reveal private work context through `cwd`, project names, branch names, tags, and source paths. Use `--privacy-mode redacted` or `--privacy-mode strict` before sharing dashboards, CSV exports, JSON query output, or support bundles.
- Remaining 5-hour and weekly allowance is not read automatically from Codex or inferred from the logged-in account plan. Add `~/.codex-usage-tracker/allowance.json` when you want the dashboard to show your current copied allowance state.
- Local Codex logs may not include usage from other ChatGPT agentic surfaces that share the same allowance.
- Parent-child thread relationships are only as good as the metadata Codex logs. Explicit parent session ids are preferred; inferred auto-review attachments are labeled as inferred.
- On-demand context loading reads from the original local JSONL source. It is redacted and size-limited, but it is still local raw log context and should be treated as sensitive.

## Install As A Local Codex Plugin

After installing the Python package, register the plugin locally:

```bash
codex-usage-tracker install-plugin
```

For a source checkout that should use the repo-local virtual environment:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python
```

If you previously installed the older source-checkout symlink, replace it once:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python --force
```

Restart Codex after registration so it can discover the plugin.

Marketplace installs use the bundled MCP launcher at
`skills/codex-usage-tracker/scripts/run_mcp.py`. On first MCP startup it creates
a cached runtime under `~/.cache/codex-usage-tracker/mcp-runtime/` and installs
the Python package from GitHub, so it does not require a `.venv` inside the
plugin directory. The launcher stores the GitHub package spec used for that
runtime and reinstalls when the bundled package pin changes. Set
`CODEX_USAGE_TRACKER_PACKAGE_SPEC` to test a different Git ref or
`CODEX_USAGE_TRACKER_RUNTIME_DIR` to use a separate cache while debugging
plugin startup.

## Codex Skills

The plugin installs two companion skills. They are local instruction files that
help Codex use this package; they do not create another hosted service or send
usage data outside the machine.

- `codex-usage-tracker` is the operational skill for setup and direct tracker work: refresh data, generate or serve dashboards, export CSV, run doctor checks, and use MCP tools directly.
- `codex-usage-api` is the conversational analyst skill. Use it when you want Codex to answer questions from tracker data, compare threads/projects/models, explain cache and context behavior, or discuss pricing, Codex credit, and allowance limitations.

Good prompts for the API companion skill:

```text
Use my Codex Usage Tracker data to explain what drove usage this week.
Which threads used the most Codex credits and why?
Find low-cache or high-context calls from today and suggest what to inspect next.
Compare usage by project for the last 7 days.
Show me what is estimated or unpriced before I trust the cost numbers.
```

The API skill should use aggregate JSON first: refresh the local index, call
`usage_summary`, `usage_query`, `session_usage`,
`most_expensive_usage_calls`, or `usage_pricing_coverage`, then explain the
answer with the data scope and any estimate caveats. If MCP tools are not
available, the same questions can be answered through the CLI JSON commands
documented in [`docs/cli-json-schemas.md`](docs/cli-json-schemas.md).

The companion skill cannot read your logged-in Codex account plan, native
remaining allowance, or usage from other agentic surfaces. Remaining allowance
context is only as accurate as the values you manually copy into
`~/.codex-usage-tracker/allowance.json`. Raw logged context is separate from
normal analysis and should only be loaded when you explicitly ask for it.

## MCP Tools

- `refresh_usage_index`
- `usage_doctor`
- `usage_summary`
- `usage_query`
- `session_usage`
- `usage_call_context`
- `most_expensive_usage_calls`
- `usage_pricing_coverage`
- `generate_usage_dashboard`
- `export_usage_csv`
- `init_usage_pricing_config`
- `update_usage_pricing_config`
- `init_usage_allowance_config`

`usage_summary`, `session_usage`, `most_expensive_usage_calls`, and `usage_pricing_coverage` accept `response_format="json"` when an agent needs stable structured output instead of markdown. `usage_query` always returns JSON.

## Data Privacy

The SQLite database is stored at `~/.codex-usage-tracker/usage.sqlite3` by default and contains only aggregate metrics:

- session id, thread name, cwd, source file, turn id, timestamps
- model, reasoning effort, context window
- token counts and derived efficiency ratios
- subagent source, role, nickname, parent session id, and parent thread name when present

Raw chat text and tool outputs are ignored by the parser and are never written to the tracker database, CSV exports, or generated dashboard HTML. `usage_call_context`, `codex-usage-tracker context`, and the `serve-dashboard` context endpoint read a single source JSONL file only when explicitly requested, redact common secret patterns, and cap returned text size.

The localhost server binds only to loopback hosts, validates loopback `Host` and `Origin` headers, protects refresh/context API calls with a random per-server token, and can disable the context API entirely with `--no-context-api`.

For MCP users, `usage_call_context` is additionally disabled unless the MCP server process has `CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1` in its environment. Aggregate MCP tools do not require that opt-in.

Cost estimates are calculated only from aggregate token fields and your local pricing config. They are omitted when no matching model price is configured. Pricing refreshes pull only OpenAI's public pricing markdown and do not send local usage data anywhere.

Codex credit estimates are calculated only from aggregate token fields and bundled or locally configured rate-card values. The optional allowance config is local and stores only the remaining percentages, reset times, or credit totals you manually enter.

## Test

```bash
python -m pytest
python -m compileall src
python -m build
python scripts/check_release.py --dist
git diff --check
codex-usage-tracker update-pricing --output /tmp/codex-usage-pricing.json
codex-usage-tracker update-rate-card --output /tmp/codex-usage-rate-card.json
codex-usage-tracker init-allowance --output /tmp/codex-usage-allowance.json
codex-usage-tracker parse-allowance --output /tmp/codex-usage-allowance.json "5h 79% 6:50 PM Weekly 33% Jun 7"
codex-usage-tracker doctor
codex-usage-tracker dashboard --output /tmp/codex-usage-dashboard.html
codex-usage-tracker serve-dashboard --help
codex-usage-tracker pricing-coverage
codex-usage-tracker summary --preset by-subagent-role
codex-usage-tracker expensive --limit 5
```

## Release Checklist

Before making the repository public or publishing a package:

```bash
python -m pytest
python -m compileall src
python -m build
python scripts/check_release.py --dist
git diff --check
```

Then verify the local package install path:

```bash
python -m pip install ".[dev]"
codex-usage-tracker --version
codex-usage-tracker install-plugin --plugin-dir /tmp/codex-usage-tracker-plugin-smoke --marketplace /tmp/codex-usage-marketplace-smoke.json --python .venv/bin/python --force
```

Keep the GitHub repository private until you are ready to intentionally switch visibility. The release checker verifies version alignment, required public docs, packaged plugin assets, wheel contents, and obvious tracked secret patterns; it does not publish anything.
