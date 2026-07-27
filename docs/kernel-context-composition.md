# Optional Context Composition

Context composition is an explicit local capability layered beside the usage
kernel. It is disabled by default, does not run during normal refresh, and
never changes the accounting database.

Enable it only after reviewing the privacy boundary:

```bash
codex-usage-tracker content enable --confirm-private-content
codex-usage-tracker content index
```

The index stores exact UTF-8 byte counts and event counts by bounded structural
category in `codex-usage-content-v1.sqlite3`. Optional bounded fragments require
the additional `--store-redacted-fragments` flag. Secret-shaped values,
credential fields, and host paths are redacted before fragment persistence.
Fragments are never returned by `usage_query` or the shareable `export`
command.

The `context` dataset supports bounded rows, aggregate, share, distribution,
and timeline queries. For example:

```json
{
  "requests": [
    {
      "dataset": "context",
      "operation": "share",
      "dimensions": ["category"],
      "measures": ["events", "observed_bytes", "estimated_tokens"],
      "order_by": "observed_bytes",
      "limit": 25
    }
  ]
}
```

`observed_bytes` and `events` are exact observations of indexed payload
strings. They are not exact billed input-token attribution.
`estimated_tokens` remains `null` unless an explicit tokenizer supplied the
estimate; results identify the estimator and coverage. Unattributed input
tokens remain explicit and unavailable when no safe comparison exists.

Indexing consumes only source ranges already committed by the kernel. Repeated
indexing resumes from per-source cursors, replacement detection rebuilds only
the affected source, and failures roll back the isolated content transaction.
Normal accounting queries remain available if this database is absent,
disabled, corrupt, or deleted.

Disable future indexing while retaining its database:

```bash
codex-usage-tracker content disable
```

Delete all optional content metadata and fragments:

```bash
codex-usage-tracker content delete
```

Deleting the content database does not delete or rebuild the accounting
kernel.
