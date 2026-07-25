# Upgrading to 0.25.0

Release 0.25 removes the legacy static dashboard product and its entry points.
The live localhost Evidence Console remains the supported dashboard.

| Removed in 0.25 | Replacement |
| --- | --- |
| `codex-usage-tracker dashboard` | `codex-usage-tracker open`, or CLI CSV/JSON export |
| `codex-usage-tracker open-dashboard` | `codex-usage-tracker open` |
| MCP `generate_usage_dashboard` | Core `usage_query` / `usage_analyze`, then an exact Evidence Console link when needed |
| Generated static dashboard files | Live `/react-dashboard.html` or CLI CSV/JSON export |

Existing bookmarks to `/dashboard.html` receive a data-free `410 Gone` page
that links to `/react-dashboard.html` for the 0.25 release. Requests to `/`
receive a `302` redirect to `/react-dashboard.html`.

Exact Evidence Console deep links remain supported. The focused Calls, Threads,
thread-call, Home, and Limits query plans are unchanged, as are canonical
accounting, privacy and raw-context controls, incremental refresh behavior, and
schema migration integrity.

When upgrading an installed plugin bundle, refresh it after the package
upgrade:

```bash
codex-usage-tracker setup --force-plugin
codex-usage-tracker open
```

Large existing indexes may require a long refresh while derived state is
rebuilt once after an older parser/checkpoint format. Normal MCP and Evidence
Console startup is read-only in 0.25, so `service serve --no-refresh` remains
available against the last committed generation while that refresh runs.
Operational job leases and progress use the separate `usage.jobs.sqlite3`
sidecar instead of competing for the usage-index writer lock.

After a compatible initial build, refresh is incremental:

- no source, configuration, or OTel change completes without a usage-index
  write, even when another connection holds the writer lock; canonical refresh
  metadata continues to describe the last material index update;
- appended complete JSONL rows hydrate from the stored byte checkpoint;
- a partial last line remains pending;
- rows appended after a refresh captures its fixed boundary are reported as
  `tail_pending` and hydrate in one bounded follow-up refresh.

- detached refresh workers retry transient `locked` or `busy` sidecar status
  writes and bounded process-spawn failures, preventing a brief cross-process
  collision from leaving an otherwise valid refresh permanently queued;
- same-version plugin cache coherence includes the generated Python launcher,
  so `setup --force-plugin` invalidates a cache that points at an older
  environment.

Reopening a browser tab against an already running service does not refresh or
rebuild the index. Starting `open` or `service serve` without `--no-refresh`
does request a refresh, but a no-change request reuses the existing build.
