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
rebuilt. Avoid starting a second tracker process against the same SQLite
database until that refresh finishes. A concurrent `service serve
--no-refresh` can currently encounter `database is locked` while startup job
recovery attempts to write. This is a known post-release concurrency finding;
do not interrupt the single refresh or bypass integrity and freshness checks.
