# Read-Only Overlay Adapter Contract

> Historical 0.28 evidence only. This document is non-authoritative for the
> replacement and does not authorize implementation.

This document freezes `codex-usage-tracker.overlay-adapter-contract.v1`. It
does not authorize overlay implementation, a browser extension, DOM
integration, or a transport change. Those remain separately approved future
decisions.

## Authority boundary

An adapter may consume only three existing loopback routes:

- `GET /api/kernel/v1/status` for the runtime handshake;
- `POST /api/kernel/v1/evidence` for one bounded logical-selector snapshot;
- `GET /api/kernel/v1/events` for bounded generation-event replay.

It cannot refresh, capture, load raw content, write either database, acquire a
writer lease, read credentials, or transmit data externally. No credentials
may be supplied or stored. No DOM capture, page scraping, mutation, or
instrumentation is part of this contract.

Sidecar remains canonical renderer and fallback. The canonical live destination
is `/evidence/{selector}?view=timeline&live=1`; an adapter may present a
convenience view but cannot replace or reinterpret the evidence.

## Handshake and negotiation

The adapter is compiled against protocol version `1`, API prefix
`/api/kernel/v1`, and the machine contract in
`config/kernel-overlay-adapter-v1.json`. It reads the existing status fields
`version`, `state`, `generation`, and `publication_id`. The package version is
informational; protocol and API versions determine compatibility. The offered
capabilities must exactly equal the three route capabilities in the machine
contract.

Unknown protocol, API version, Host, or Origin fails closed. Requests require a
loopback Host. Origin may be absent for a non-browser client, but when present
must use HTTP or HTTPS with `127.0.0.1`, `localhost`, or `::1`, no credentials,
an empty or root path, no query, and no fragment. K13 does not add CORS
authority or authorize a non-loopback page to call the kernel directly.

## Selectors and snapshot identity

Only existing logical selectors are valid: thread, turn, call, tool, and
allowance. The adapter sends the same bounded evidence request used by the
sidecar and displays the returned selector, generation, grade, coverage, and
rows without inventing missing facts.

Generation and `publication_id` together form the active snapshot identity. A
changed publication invalidates prior presentation even when the generation
number is reused after rollback. An adapter accepts a snapshot only after this
sequence:

1. Read a usable status with non-null generation and publication ID.
2. Read bounded evidence and require its generation to match that status.
3. Read status again and require the exact same generation and publication ID.

An absent status, a null identity, a generation mismatch, or any publication
race rejects the snapshot. Retry is bounded and must not trigger refresh.

## Stream and reconnect

The stream carries `generation_committed` and `snapshot_required` as SSE events.
A heartbeat is an SSE comment, not an event. Generation payloads are restricted
to the aggregate allowlist in the machine contract; selectors may be present,
but raw arguments, prompts, model output, paths, and credentials are forbidden.

A normal reconnect sends the last accepted numeric SSE event ID in
`Last-Event-ID`. Replay is capped at 500 events. Retention gaps, generation
gaps, future event IDs, and publication mismatches produce
`snapshot_required`.

On `snapshot_required`, the consumer must close the stale EventSource, discard
its saved event cursor and local presentation, complete the status/evidence/
status snapshot sequence, and open a fresh EventSource without
`Last-Event-ID`. Reusing the old EventSource or its implicit browser cursor can
repeat the same gap forever. Silently bridging a gap is forbidden.

## Synthetic fixture

`tests/kernel/fixtures/overlay-adapter-v1.json` is the canonical synthetic
exchange. It contains a fenced snapshot, explicit absent-status and publication
race rejections, separate committed-event and gap connections, and a fresh
cursor-free heartbeat connection. It contains no real Usage Tracker or Codex
data.
