# Service Tier Billing Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OTel service-tier enrichment release-ready by preserving the exact tier, selecting API prices per call, source-stamping ChatGPT Fast multipliers, correcting presentation, and closing reset and rotation safety gaps.

**Architecture:** Keep `service_tier` as exact response evidence and `fast` as a derived speed classification. Pricing-v2 caches every published API tier while retaining the v1 `models` projection for compatibility; cost annotations expose exact-tier and comparison scenarios, while credit annotations use a source-stamped rate-card multiplier. OTel rebuild retention remains distinct from destructive database reset, and cursor identity comes from the open descriptor.

**Tech Stack:** Python 3.10+, SQLite, pytest, TypeScript/React, Vitest, local JSON pricing/rate-card files.

## Global Constraints

- Never infer ChatGPT-versus-API authentication from OTel `service_tier`.
- Never apply ChatGPT Fast multipliers to API USD estimates.
- Preserve pricing-v1 files and stable existing output keys.
- Keep all new persisted and fixture data aggregate-only and synthetic.
- Write a failing test and observe the expected failure before each production change.
- Do not stage `.idea/`, `uv.lock`, local databases, OTel logs, or private data.

---

### Task 1: Preserve Exact Response Tiers

**Files:**
- Modify: `tests/parser/test_otel_parser.py`
- Modify: `src/codex_usage_tracker/parser/otel.py`
- Modify: `tests/store/test_otel_reconciliation.py`

**Interfaces:**
- Produces: `OtelCompletion.service_tier` containing normalized upstream values such as `priority`, `fast`, `default`, `standard`, or `flex`.
- Produces: `OtelCompletion.fast` as the independent `1 | 0 | None` speed classification.

- [ ] **Step 1: Write failing parser expectations**

```python
@pytest.mark.parametrize(
    ("raw_tier", "normalized_tier", "fast"),
    [
        ("priority", "priority", 1),
        ("fast", "fast", 1),
        ("default", "default", 0),
        ("standard", "standard", 0),
        ("flex", "flex", 0),
    ],
)
def test_explicit_tier_names_are_preserved(raw_tier, normalized_tier, fast):
    completion = parse_otlp_json_line(
        synthetic_otlp_line(attributes=completion_attributes(service_tier=raw_tier))
    ).completions[0]
    assert (completion.service_tier, completion.fast) == (normalized_tier, fast)
```

- [ ] **Step 2: Run the parser test and verify RED**

Run: `.venv/bin/python -m pytest tests/parser/test_otel_parser.py -q`
Expected: FAIL because `priority` currently becomes `fast` and `default` becomes `standard`.

- [ ] **Step 3: Implement exact-tier normalization**

```python
normalized = raw_tier.lower()
if normalized in {"priority", "fast"}:
    return normalized, 1, "otel_response_completed", "exact"
return normalized, 0, "otel_response_completed", "exact"
```

Keep versioned omission as `service_tier="standard"`, `fast=0`, confidence `protocol`.

- [ ] **Step 4: Update reconciliation fixtures and verify GREEN**

Run: `.venv/bin/python -m pytest tests/parser/test_otel_parser.py tests/store/test_otel_reconciliation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -- tests/parser/test_otel_parser.py tests/store/test_otel_reconciliation.py src/codex_usage_tracker/parser/otel.py
git commit -m "fix: preserve exact OTel service tiers"
```

### Task 2: Cache All API Pricing Tiers Backward-Compatibly

**Files:**
- Modify: `tests/pricing/test_pricing.py`
- Modify: `src/codex_usage_tracker/pricing/config.py`
- Modify: `src/codex_usage_tracker/pricing/openai.py`
- Modify: `src/codex_usage_tracker/pricing/api.py`

**Interfaces:**
- Produces: `PRICING_SCHEMA = "codex-usage-tracker-pricing-v2"`.
- Produces: `PricingConfig.api_service_tiers: dict[str, dict[str, dict[str, float]]]`.
- Produces: `PricingConfig.billing_basis: str` with `unknown`, `chatgpt_credits`, or `api_tokens`.
- Produces: `PricingConfig.rates_for(model, service_tier=None)` and `pricing_tier_for(service_tier)`.
- Preserves: `PricingConfig.models`, `--tier`, `_source.tier`, aliases, estimates, pinning, and v1 loading.

- [ ] **Step 1: Write failing v1/v2 config tests**

```python
def test_pricing_v2_selects_rates_by_service_tier(tmp_path: Path) -> None:
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({
        "_schema": "codex-usage-tracker-pricing-v2",
        "billing_basis": "api_tokens",
        "models": {"gpt-5.6": {
            "input_per_million": 5.0,
            "cached_input_per_million": 0.5,
            "output_per_million": 30.0,
        }},
        "api_service_tiers": {
            "standard": {"gpt-5.6": {
                "input_per_million": 5.0,
                "cached_input_per_million": 0.5,
                "output_per_million": 30.0,
            }},
            "priority": {"gpt-5.6": {
                "input_per_million": 10.0,
                "cached_input_per_million": 1.0,
                "output_per_million": 60.0,
            }},
        },
    }), encoding="utf-8")
    config = load_pricing_config(path)
    assert config.billing_basis == "api_tokens"
    assert config.rates_for("gpt-5.6", service_tier="priority")["input_per_million"] == 10

def test_pricing_v1_ignores_row_tier_for_compatibility(tmp_path: Path) -> None:
    config = load_v1_pricing(tmp_path, input_rate=5)
    assert config.rates_for("gpt-5.6", service_tier="priority")["input_per_million"] == 5
```

- [ ] **Step 2: Run config tests and verify RED**

Run: `.venv/bin/python -m pytest tests/pricing/test_pricing.py -q`
Expected: FAIL because v2 tier maps and billing basis are unsupported.

- [ ] **Step 3: Implement v2 loading and canonical tier selection**

```python
def normalize_api_service_tier(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return {
        "fast": "priority",
        "priority": "priority",
        "default": "standard",
        "standard": "standard",
        "batch": "batch",
        "flex": "flex",
    }.get(normalized)

def rates_for(self, model: object, service_tier: object | None = None):
    tier = normalize_api_service_tier(service_tier)
    if tier and tier in self.api_service_tiers:
        return _rates_for_models(self.api_service_tiers[tier], self.aliases, model)
    return _rates_for_models(self.models, self.aliases, model)
```

Invalid `billing_basis` makes the config invalid rather than guessing.

- [ ] **Step 4: Write failing all-tier updater test**

```python
def test_update_pricing_caches_every_api_tier(tmp_path: Path) -> None:
    result = update_pricing_from_openai_docs(
        tmp_path / "pricing.json", tier="batch", fetch_text=lambda _: ALL_TIER_FIXTURE
    )
    raw = json.loads(result.path.read_text())
    assert set(raw["api_service_tiers"]) == {"standard", "batch", "flex", "priority"}
    official_batch_models = {
        model: rates
        for model, rates in raw["models"].items()
        if rates.get("estimated") is not True
    }
    assert official_batch_models == raw["api_service_tiers"]["batch"]
    assert raw["_source"]["tier"] == "batch"
```

- [ ] **Step 5: Implement atomic all-tier parsing and cache writing**

```python
def parse_all_openai_pricing_tiers(markdown: str):
    return {
        tier: parse_openai_pricing_markdown(markdown, tier=tier)
        for tier in VALID_PRICING_TIERS
    }
```

Fetch once, parse all four tiers before writing, keep `models` as the selected projection, add estimates only to that projection, and preserve the existing local `billing_basis` when refreshing.

- [ ] **Step 6: Verify GREEN**

Run: `.venv/bin/python -m pytest tests/pricing/test_pricing.py tests/cli/test_cli_module_entrypoints.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -- tests/pricing/test_pricing.py src/codex_usage_tracker/pricing/config.py src/codex_usage_tracker/pricing/openai.py src/codex_usage_tracker/pricing/api.py
git commit -m "feat: cache all API pricing tiers"
```

### Task 3: Select Per-Call API Rates and Expose Scenarios

**Files:**
- Modify: `tests/pricing/test_pricing.py`
- Modify: `src/codex_usage_tracker/pricing/costing.py`
- Modify: `src/codex_usage_tracker/core/schema.py`
- Modify: `frontend/dashboard/src/api/serviceTier.ts`
- Modify: `frontend/dashboard/src/api/types.ts`

**Interfaces:**
- Adds row keys: `standard_cost_usd`, `priority_cost_usd`, `pricing_service_tier`, `billing_basis`, and `cost_semantics`.
- Preserves `estimated_cost_usd` as the API-equivalent estimate selected from the exact tier when available.

- [ ] **Step 1: Write failing cost-selection tests**

```python
def pricing_v2_config() -> PricingConfig:
    standard = {
        "input_per_million": 5.0,
        "cached_input_per_million": 0.5,
        "output_per_million": 30.0,
    }
    priority = {
        "input_per_million": 10.0,
        "cached_input_per_million": 1.0,
        "output_per_million": 60.0,
    }
    return PricingConfig(
        path=Path("/synthetic/pricing.json"),
        models={"gpt-5.6": standard},
        loaded=True,
        api_service_tiers={
            "standard": {"gpt-5.6": standard},
            "priority": {"gpt-5.6": priority},
        },
        billing_basis="unknown",
    )

def cost_row(service_tier: str | None) -> dict[str, object]:
    return {
        "model": "gpt-5.6",
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "uncached_input_tokens": 80,
        "output_tokens": 10,
        "service_tier": service_tier,
    }

def test_v2_priority_row_uses_priority_table() -> None:
    config = pricing_v2_config()
    standard = estimate_cost_usd(cost_row(service_tier="standard"), config)
    priority = estimate_cost_usd(cost_row(service_tier="priority"), config)
    assert priority == pytest.approx(standard * 2)

def test_cost_annotations_expose_standard_and_priority_scenarios() -> None:
    annotated = annotate_rows_with_efficiency([cost_row(service_tier=None)], pricing_v2_config())[0]
    assert annotated["standard_cost_usd"] is not None
    assert annotated["priority_cost_usd"] is not None
    assert annotated["billing_basis"] == "unknown"
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/pricing/test_pricing.py -q`
Expected: FAIL because costing does not pass the row tier or emit scenarios.

- [ ] **Step 3: Implement exact-tier and scenario costing**

```python
rates = pricing.rates_for(
    model if model is not None else row.get("model"),
    service_tier=row.get("service_tier"),
)
copy["pricing_service_tier"] = pricing.pricing_tier_for(copy.get("service_tier"))
copy["standard_cost_usd"] = estimate_cost_usd_for_tier(copy, config, "standard")
copy["priority_cost_usd"] = estimate_cost_usd_for_tier(copy, config, "priority")
copy["billing_basis"] = config.billing_basis
copy["cost_semantics"] = "api_token_estimate"
```

- [ ] **Step 4: Verify GREEN and schema propagation**

Run: `.venv/bin/python -m pytest tests/pricing/test_pricing.py tests/core/test_api_payloads.py tests/dashboard/test_dashboard_payload.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -- tests/pricing/test_pricing.py tests/core/test_api_payloads.py tests/dashboard/test_dashboard_payload.py src/codex_usage_tracker/pricing/costing.py src/codex_usage_tracker/core/schema.py frontend/dashboard/src/api/serviceTier.ts frontend/dashboard/src/api/types.ts
git commit -m "feat: price calls by observed API tier"
```

### Task 4: Source-Stamp ChatGPT Fast Multipliers

**Files:**
- Modify: `src/codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json`
- Modify: `src/codex_usage_tracker/pricing/allowance_rate_card.py`
- Modify: `src/codex_usage_tracker/pricing/allowance_config.py`
- Modify: `src/codex_usage_tracker/pricing/fast_tier.py`
- Modify: `src/codex_usage_tracker/pricing/allowance_usage.py`
- Modify: `tests/pricing/test_allowance.py`
- Modify: `tests/pricing/test_rate_card.py`

**Interfaces:**
- Produces: `FastMultiplierMatch(multiplier, model_family, source_url, fetched_at, confidence)`.
- Adds row keys: `fast_usage_credits`, `usage_credit_multiplier_source_url`, `usage_credit_multiplier_fetched_at`, and `usage_credit_multiplier_confidence`.
- Allows local `allowance.json` `fast_multipliers` entries to override bundled entries with `user_override` confidence.

- [ ] **Step 1: Write failing rate-card and annotation tests**

```python
def test_fast_multiplier_provenance_comes_from_rate_card() -> None:
    config = replace(
        _synthetic_allowance_config(),
        fast_multipliers={
            "gpt-5.6": FastMultiplierRate(
                multiplier=2.5,
                source_name="OpenAI Codex Fast mode docs",
                source_url="https://learn.chatgpt.com/docs/agent-configuration/speed",
                fetched_at="2026-07-16",
                confidence="exact",
            )
        },
    )
    row = annotate_rows_with_allowance(
        [_credit_row(model="gpt-5.6", fast=1, service_tier="priority")], config
    )[0]
    assert row["usage_credit_multiplier"] == 2.5
    assert row["usage_credit_multiplier_source"] == "OpenAI Codex Fast mode docs"
    assert row["usage_credit_multiplier_source_url"].endswith("/agent-configuration/speed")
    assert row["usage_credit_multiplier_confidence"] == "exact"
    assert row["service_tier_source"] == "otel_response_completed"

def test_local_fast_multiplier_override_is_source_stamped() -> None:
    config = load_allowance_config(write_allowance_override(
        fast_multipliers={
            "gpt-5.6": {
                "multiplier": 3.0,
                "source_name": "Synthetic override",
                "source_url": "https://example.invalid/synthetic-fast-rate",
                "fetched_at": "2026-07-16",
            }
        }
    ))
    assert config.fast_multipliers["gpt-5.6"].confidence == "user_override"
```

Add `write_allowance_override()` as a local test helper that writes the shown dictionary beneath
the existing allowance template's `fast_multipliers` key to `tmp_path / "allowance.json"` and
returns that path.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/pricing/test_allowance.py tests/pricing/test_rate_card.py -q`
Expected: FAIL because multipliers are hard-coded and provenance is conflated with OTel.

- [ ] **Step 3: Move multipliers into the source-stamped rate card**

```json
"fast_multipliers": {
  "gpt-5.6": {
    "multiplier": 2.5,
    "source_name": "OpenAI Codex Fast mode docs",
    "source_url": "https://learn.chatgpt.com/docs/agent-configuration/speed",
    "fetched_at": "2026-07-16",
    "confidence": "exact"
  }
}
```

Add equivalent GPT-5.5 and GPT-5.4 entries. Parse only finite multipliers `>= 1.0`; reject malformed local overrides without discarding the valid bundled card.

- [ ] **Step 4: Resolve multiplier by model family and annotate provenance**

`fast_tier.py` performs family matching against parsed configuration rather than module constants. `allowance_usage.py` computes Standard and hypothetical Fast scenarios, applies the Fast scenario only when `fast == 1`, and keeps OTel tier evidence in the existing service-tier fields.

- [ ] **Step 5: Verify GREEN**

Run: `.venv/bin/python -m pytest tests/pricing/test_allowance.py tests/pricing/test_rate_card.py tests/dashboard/test_dashboard_payload.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -- src/codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json src/codex_usage_tracker/pricing/allowance_rate_card.py src/codex_usage_tracker/pricing/allowance_config.py src/codex_usage_tracker/pricing/fast_tier.py src/codex_usage_tracker/pricing/allowance_usage.py tests/pricing/test_allowance.py tests/pricing/test_rate_card.py tests/dashboard/test_dashboard_payload.py
git commit -m "feat: source stamp Fast credit multipliers"
```

### Task 5: Correct Dashboard Tier Labels

**Files:**
- Modify: `frontend/dashboard/src/features/calls/serviceTier.test.ts`
- Modify: `frontend/dashboard/src/features/shared/callPresentation.ts`
- Modify: `frontend/dashboard/src/features/shared/tables.test.ts`
- Modify: `frontend/dashboard/src/features/shared/tables.tsx`

**Interfaces:**
- Produces: `serviceTierLabel()` labels derived from `serviceTier` first and `fast` only as fallback.
- Produces: tier detail that reports exact tier and confidence without claiming billing path.

- [ ] **Step 1: Write failing presentation tests**

```typescript
it.each([
  ['priority', true, 'Priority / Fast'],
  ['fast', true, 'Fast'],
  ['default', false, 'Default / Standard'],
  ['standard', false, 'Standard'],
  ['flex', false, 'Flex'],
  ['batch', false, 'Batch'],
])('labels exact service tier %s', (serviceTier, fast, expected) => {
  expect(serviceTierLabel({ ...baseCall, serviceTier, fast })).toBe(expected);
});
```

- [ ] **Step 2: Verify RED**

Run: `npm test -- --run frontend/dashboard/src/features/calls/serviceTier.test.ts`
Expected: FAIL because every `fast=false` row is currently Standard.

- [ ] **Step 3: Implement exact-tier labels and details**

Normalize the tier string, map known values explicitly, title-case bounded unknown values, and use `fast` only when no exact tier exists. Include `serviceTier` in `ServiceTierInput`.

- [ ] **Step 4: Verify GREEN**

Run: `npm test -- --run frontend/dashboard/src/features/calls/serviceTier.test.ts frontend/dashboard/src/features/shared/tables.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/dashboard/src/features/calls/serviceTier.test.ts frontend/dashboard/src/features/shared/callPresentation.ts frontend/dashboard/src/features/shared/tables.test.ts frontend/dashboard/src/features/shared/tables.tsx
git commit -m "fix: label exact service tiers"
```

### Task 6: Make Reset Destructive and Rotation Cursor-Safe

**Files:**
- Modify: `tests/store/test_source_records.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `tests/store/test_otel_ingest.py`
- Modify: `src/codex_usage_tracker/store/otel_ingest.py`

**Interfaces:**
- `reset_usage_database()` deletes `otel_completion_events` and `otel_completion_sources`.
- OTel cursors persist descriptor identity and never mix offsets across inodes.

- [ ] **Step 1: Write failing reset test**

```python
def test_reset_usage_database_clears_otel_staging_and_cursors(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    otel_dir = write_otel_directory(
        tmp_path,
        "synthetic-reset",
        (120, 40, 30, 10),
    )
    with connect(db_path) as conn:
        init_db(conn)
        ingest_otel_completion_files(conn, otel_dir)
    reset_usage_database(db_path)
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM otel_completion_events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM otel_completion_sources").fetchone()[0] == 0
```

- [ ] **Step 2: Verify RED, implement deletion, and verify GREEN**

Run: `.venv/bin/python -m pytest tests/store/test_source_records.py -q`
Expected before implementation: FAIL with retained rows. Add both fixed-table `DELETE` statements and rerun for PASS.

- [ ] **Step 3: Write failing concurrent-rotation test**

Use a small injected `open_file`/`after_open` seam in `ingest_otel_completion_files` so the test can replace the path after the initial discovery stat but before reading. Assert the replacement file is read from byte zero and its cursor matches its own `fstat()` identity.

- [ ] **Step 4: Verify RED**

Run: `.venv/bin/python -m pytest tests/store/test_otel_ingest.py -q`
Expected: FAIL because path stats and descriptor reads can refer to different inodes.

- [ ] **Step 5: Implement descriptor-based cursor safety**

Open first, call `os.fstat(handle.fileno())` for resume identity, read complete lines, call `os.fstat()` again, and persist only descriptor-derived state. If descriptor identity changes unexpectedly, discard the candidate cursor and retry from zero once; never combine `Path.stat()` identity with an offset read from another descriptor.

- [ ] **Step 6: Verify GREEN and commit**

Run: `.venv/bin/python -m pytest tests/store/test_source_records.py tests/store/test_otel_ingest.py tests/store/test_otel_refresh.py -q`
Expected: PASS.

```bash
git add -- tests/store/test_source_records.py tests/store/test_otel_ingest.py src/codex_usage_tracker/store/api.py src/codex_usage_tracker/store/otel_ingest.py
git commit -m "fix: clear OTel state and harden rotation"
```

### Task 7: Update Contracts, Documentation, and Generated Dashboard Assets

**Files:**
- Modify: `docs/pricing-and-credits.md`
- Modify: `docs/database-schema.md`
- Modify: `docs/privacy.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `CHANGELOG.md`
- Modify: generated files under `src/codex_usage_tracker/plugin_data/dashboard/react/assets/`
- Modify: affected API/dashboard/report tests.

**Interfaces:**
- Documents pricing-v2, exact-tier semantics, billing basis, scenario fields, reset/rebuild distinction, and source-stamped multipliers.
- Generated dashboard assets match the reviewed TypeScript source.

- [ ] **Step 1: Update contract tests before docs/assets**

Add assertions for exact `priority`, pricing scenario fields, multiplier provenance, and billing-basis labels to the existing API payload, CSV, report, and dashboard tests. Run them and observe failures where propagation is missing.

- [ ] **Step 2: Complete additive propagation and documentation**

Keep existing stable keys. Explain that `usage_credits` is ChatGPT-equivalent, `estimated_cost_usd` is API-token-equivalent, `billing_basis` identifies applicability, and unknown basis exposes scenarios without claiming actual spend.

- [ ] **Step 3: Build dashboard assets and run focused gates**

Run the repository's existing frontend build/governance commands from `package.json`, followed by:

```bash
.venv/bin/python -m pytest tests/core/test_api_payloads.py tests/dashboard/test_dashboard_payload.py tests/reports/test_support.py -q
python scripts/check_release.py
git diff --check
```

Expected: all PASS and generated assets match source.

- [ ] **Step 4: Commit**

```bash
git add -- CHANGELOG.md docs/pricing-and-credits.md docs/database-schema.md docs/privacy.md docs/dashboard-guide.md docs/cli-json-schemas.md frontend/dashboard/src src/codex_usage_tracker/plugin_data/dashboard/react/assets tests
git commit -m "docs: explain tier-aware billing estimates"
```

### Task 8: Final Verification and Review

**Files:**
- No intended production edits; fix only verified failures within this feature scope.

**Interfaces:**
- Produces release-readiness evidence for the complete branch.

- [ ] **Step 1: Run focused Python and frontend suites**

```bash
python -m pytest tests/parser/test_otel_parser.py tests/store/test_otel_ingest.py tests/store/test_otel_reconciliation.py tests/store/test_otel_refresh.py tests/pricing/test_allowance.py tests/pricing/test_pricing.py tests/store/test_source_records.py -q
```

Run the frontend service-tier and table tests plus every dashboard test affected by generated assets.

- [ ] **Step 2: Run the full repository gates**

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m compileall src
for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done
python scripts/check_release.py
git diff --check
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
```

- [ ] **Step 3: Review status, diff, and privacy**

Confirm only intended tracked files changed, no local logs/database/config/private values entered the diff, `.idea/` and `uv.lock` remain untracked, and the exact-tier/billing tests prove the reviewed blockers are closed.

- [ ] **Step 4: Report readiness**

Provide commits, validation counts, skipped checks with reasons, remaining risks, and whether the branch is ready to push/open as a PR. Do not push or open a PR unless requested.
