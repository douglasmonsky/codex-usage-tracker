# Evidence Console Route Migration

Release 0.23.0 keeps old stable bookmarks readable while making the current
route model explicit. Normalization preserves reviewed scope parameters and
removes parameters that do not belong to the destination.

## Stable URL Mapping

| Historical URL | Canonical destination |
| --- | --- |
| `?view=overview` | `?view=home` |
| `?view=calls` | `?view=explore&mode=calls` |
| `?view=threads` | `?view=explore&mode=threads` |
| `?view=call&record=<id>` | `?view=evidence&kind=call&record=<id>` |

Home is readiness and status, Explore owns both Calls and Threads, and Evidence
owns exact contextual verification. Limits and Settings retain their stable
route names.

## Contextual Evidence Selectors

```text
?view=evidence&kind=call&record=<canonical-record-id>
?view=evidence&kind=thread&thread_key=<canonical-thread-key>
?view=evidence&kind=finding&analysis=<analysis-id>&finding=<finding-id>
?view=evidence&kind=allowance&analysis=<analysis-id>&evidence=<evidence-id>
```

Malformed, stale, ambiguous, or wrong-history selectors render a recoverable
not-found state. They never fall back to a similarly named record or silently
broaden from active history to all history.

## Dashboard Target v2

New MCP, HTTP, and CLI application results emit
`codex-usage-tracker-dashboard-target-v2`. A target carries its surface,
evidence kind, reviewed selectors, scope, relative URL, optional healthy
loopback absolute URL, and fallback instruction. Prefer the absolute URL when
present. Otherwise run `codex-usage-tracker service status` and use
`codex-usage-tracker open`.

## Transition-Only Routes

Investigate, Compression Lab, Cache and Context, Reports, and Diagnostics
remain directly routable through 0.24.x. They are absent from primary
navigation, show transition guidance, and receive no new product features.
The legacy static dashboard follows the same removal window.
