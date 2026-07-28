# Spike Performance Evidence

> Historical, non-authoritative measurements. These results guide bake-off
> fixture shape and regression budgets; they are not promises for the
> replacement.

All production-shaped measurements below were aggregate-only. The prior work
did not read or preserve raw prompt, response, reasoning, command, patch, tool
output, or private path content.

## Production shape

| Metric | Recorded value |
| --- | ---: |
| Local source history | 14.955 GiB |
| Model calls in deterministic production-shaped fixture | 1,316,864 |
| Tool calls | 658,432 |
| Activity events | 164,608 |
| Allowance states | 41,152 |
| Threads | 643 |
| Turns | 164,608 |
| Early schema-v2 analytical database | 1,370,804,224 bytes |
| Schema-v3 analytical database | 634,011,648 bytes |
| Corrected published database after rollups | 627,216,384 bytes |

The live aggregate inventory that motivated the work contained about 2.40
million stored facts, 1,051,496 allowance observations, 518,900 repeated
same-timestamp allowance observations, and 133,587 observed state-change rows.
Those counts show why exact observation retention and compact physical shape
must coexist.

## Cold build and history selection

| Workload | Earlier result | Best recorded spike result | Lesson |
| --- | ---: | ---: | --- |
| 100,000 model calls | 11.293 s, 503 transactions | 2.857 s, 8 transactions | Batched normalization, bounded identity maps, and deferred secondary indexes matter. |
| 160-source production slice | 49.825 s | 18.643 s | Per-row SQLite and repeated count work were material. |
| Complete 643-source fixture | 792.320 s | 111.402 s before later corrections; 129.835 s in installed correction | Complete history remains too slow for a first impression. |
| Recent 30 days over a three-year fixture | no selective baseline | 2.562 s, 17 of 643 sources, 34,816 calls | Recent-first inventory and explicit coverage are essential. |
| 30-day to 90-day expansion | 37.043 s live-writer path | 3.929 s unpublished bulk clone | Expansion should be explicit and isolated. |
| 90-day to complete expansion | exceeded 240 s and was stopped | 110.193 s unpublished bulk clone | Old history needs a separate artifact path. |

The useful mechanism was to inventory every candidate source, capture one UTC
cutoff, parse only selected whole sources, hydrate timestamp-uncertain sources,
and disclose deferred bytes. That behavior is a transplant candidate; its
physical implementation is not.

## Tail and no-change behavior

| Workload | Recorded result | Interpretation |
| --- | ---: | --- |
| One-call tail on 160-source fixture | 420.444 ms | Met the old 500 ms target but did not generalize. |
| 32-call tail on 160-source fixture | 501.004 ms | Acceptable bounded tail. |
| One-call complete-history tail before correction | 9.151 s | Whole-catalog and whole-rollup work leaked into an ordinary tail. |
| One-call complete-history tail after correction | 1.078 s | 88.2% faster, still above the desired sub-500 ms experience. |
| One-tool complete-history tail | 2.228 s | Lifecycle and projection fanout remained expensive. |
| Warm no-change after correction | 185–192 ms | Avoiding catalog rewrites and fact work was effective. |
| Earlier warm no-change | 1.178–1.199 s | Full 643-source discovery dominated even with no data change. |
| 2,000-call append over 100,000 calls | 35.565 ms writer p95 | Dirty-key rollup maintenance can be fast when bounded correctly. |

The replacement bake-off must separately measure discovery, parsing,
canonicalization, fact writes, projection writes, validation, and promotion.
It must stop early when a hard budget has already failed rather than waiting
for a long run to finish.

## Query and agent evidence

| Workload | Recorded result |
| --- | ---: |
| 100,000-call model/effort plan | 4.744 ms p95 |
| 100,000-call thread concentration plan | 2.157 ms p95 |
| 100,000-call daily bands plan | 2.258 ms p95 |
| 100,000-call week comparison | 145.575 ms p95 |
| Specialized top-thread cost/credit companion | 10.955 ms p95 |
| Prior full-table cost/credit path | 615.058 ms p95 |
| Fresh-agent one-call tracker execution | roughly 37–51 ms |
| Fresh-agent time before first tool call | roughly 15–21 s |
| Fresh-agent end-to-end answers after query corrections | roughly 24–35 s |

The strongest lesson is that fast SQL is necessary but not sufficient.
Unbounded schemas, missing named plans, duplicated response projections, and
tool-discovery behavior caused agents to spend minutes or make many calls even
when the underlying query took milliseconds. Installed-agent latency, MCP
calls, response bytes, and model tokens are first-class budgets in the new
qualification plan.

## Rejected or incomplete claims

- Profile output is attribution evidence only. Unprofiled repeated runs are
  the speed evidence.
- Small-fixture tail results are not universal production-tail claims.
- Warm Console route latency below 1 ms did not prove a useful human or agent
  experience.
- Tool adjacency does not prove token causality.
- Local usage between allowance observations does not prove provider billing
  attribution.
- A compact database alone does not win the new A/C/D bake-off; evidence
  stability, lifecycle completion, tail writes, and agent outcomes also gate
  selection.
