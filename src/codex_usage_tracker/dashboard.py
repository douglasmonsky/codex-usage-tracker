"""Static dashboard generation from aggregate-only usage rows."""

from __future__ import annotations

import html
import json
from pathlib import Path

from codex_usage_tracker.paths import DEFAULT_DASHBOARD_PATH, DEFAULT_PRICING_PATH
from codex_usage_tracker.pricing import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.store import query_dashboard_events


def generate_dashboard(
    db_path: Path,
    output_path: Path = DEFAULT_DASHBOARD_PATH,
    limit: int = 5000,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    since: str | None = None,
) -> Path:
    rows = query_dashboard_events(db_path=db_path, limit=limit, since=since)
    pricing = load_pricing_config(pricing_path)
    rows = annotate_rows_with_efficiency(rows, pricing)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "rows": rows,
            "pricing_configured": pricing.loaded and not pricing.error,
            "pricing_source": pricing.source,
        },
        ensure_ascii=True,
    ).replace("</", "<\\/")
    output_path.write_text(_html(payload), encoding="utf-8")
    return output_path


def _html(payload: str) -> str:
    title = html.escape("Codex Usage Dashboard")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #69758a;
      --line: #dde3ee;
      --blue: #2563eb;
      --green: #047857;
      --amber: #b45309;
      --red: #b91c1c;
      --violet: #6d28d9;
      --shadow: 0 12px 32px rgba(23, 32, 51, 0.09);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 24px 28px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ margin: 0 0 6px; font-size: 24px; font-weight: 720; }}
    header p {{ margin: 0; color: var(--muted); max-width: 920px; line-height: 1.45; }}
    .source-line {{ margin-top: 6px; font-size: 12px; }}
    main {{ padding: 22px 28px 36px; }}
    .filters {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    label {{ display: grid; gap: 6px; font-size: 12px; font-weight: 680; color: var(--muted); }}
    input, select {{
      width: 100%;
      min-height: 38px;
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      font: inherit;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
    }}
    .card span {{ display: block; color: var(--muted); font-size: 12px; font-weight: 680; }}
    .card strong {{ display: block; margin-top: 7px; font-size: 22px; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.8fr);
      gap: 16px;
      align-items: start;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    section h2 {{
      margin: 0;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; background: #fbfcfe; position: sticky; top: 0; }}
    tr:hover {{ background: #eff6ff; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #e0ecff;
      color: #184fc5;
      font-weight: 680;
      font-size: 12px;
    }}
    .flags {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      justify-content: flex-end;
    }}
    .flag {{
      display: inline-flex;
      min-height: 20px;
      align-items: center;
      padding: 1px 7px;
      border-radius: 999px;
      background: #f5e8ff;
      color: var(--violet);
      font-size: 11px;
      font-weight: 680;
      white-space: nowrap;
    }}
    .detail {{
      padding: 14px 16px;
      min-height: 280px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .detail dl {{ display: grid; grid-template-columns: minmax(120px, 0.6fr) minmax(0, 1fr); gap: 8px 14px; margin: 0; }}
    .detail dt {{ font-weight: 720; color: var(--ink); }}
    .detail dd {{ margin: 0; overflow-wrap: anywhere; }}
    @media (max-width: 980px) {{
      .filters, .cards, .grid {{ grid-template-columns: 1fr; }}
      main, header {{ padding-left: 16px; padding-right: 16px; }}
      table {{ font-size: 12px; }}
      th, td {{ padding: 8px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Codex Usage Dashboard</h1>
    <p>Aggregate-only token analytics from local Codex logs. Hover a table row to inspect exact last-call and cumulative usage without exposing raw chat text.</p>
    <p id="pricingSource" class="source-line"></p>
  </header>
  <main>
    <div class="filters">
      <label>Search<input id="search" type="search" placeholder="Thread, cwd, model, session"></label>
      <label>Model<select id="model"><option value="">All models</option></select></label>
      <label>Reasoning<select id="effort"><option value="">All efforts</option></select></label>
      <label>Pricing<select id="pricingStatus"><option value="">All pricing</option><option value="official">Official/configured</option><option value="estimated">Estimated</option><option value="unpriced">Unpriced</option></select></label>
      <label>Sort<select id="sort"><option value="total">Most tokens</option><option value="cost">Highest estimated cost</option><option value="time">Newest calls</option><option value="cache">Lowest cache ratio</option><option value="context">Highest context use</option></select></label>
    </div>
    <div class="cards">
      <div class="card"><span>Visible Calls</span><strong id="visibleCalls">0</strong></div>
      <div class="card"><span>Total Tokens</span><strong id="totalTokens">0</strong></div>
      <div class="card"><span>Cached Input</span><strong id="cachedTokens">0</strong></div>
      <div class="card"><span>Reasoning Output</span><strong id="reasoningTokens">0</strong></div>
      <div class="card"><span>Estimated Cost</span><strong id="estimatedCost">$0.00</strong></div>
      <div class="card"><span>Price Coverage</span><strong id="priceCoverage">0.0%</strong></div>
      <div class="card"><span>Estimated Tokens</span><strong id="estimatedTokens">0</strong></div>
      <div class="card"><span>Unpriced Tokens</span><strong id="unpricedTokens">0</strong></div>
    </div>
    <div class="grid">
      <section>
        <h2>Model Calls</h2>
        <table>
          <thead>
            <tr>
              <th>Time</th><th>Thread</th><th>Model</th><th>Effort</th><th class="num">Last Call</th><th class="num">Cost</th><th class="num">Cache</th><th class="num">Signals</th>
            </tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </section>
      <section>
        <h2>Hover Details</h2>
        <div id="detail" class="detail">Hover a row to inspect aggregate usage fields.</div>
      </section>
    </div>
  </main>
  <script id="usage-data" type="application/json">{payload}</script>
  <script>
    const payload = JSON.parse(document.getElementById('usage-data').textContent);
    const data = Array.isArray(payload) ? payload : payload.rows;
    const pricingConfigured = Boolean(payload.pricing_configured);
    const pricingSource = payload.pricing_source || {{}};
    const rowsEl = document.getElementById('rows');
    const detailEl = document.getElementById('detail');
    const searchEl = document.getElementById('search');
    const modelEl = document.getElementById('model');
    const effortEl = document.getElementById('effort');
    const pricingStatusEl = document.getElementById('pricingStatus');
    const sortEl = document.getElementById('sort');
    const number = new Intl.NumberFormat();
    const money = (value, missingLabel = 'No price') => {{
      if (value === null || value === undefined) return missingLabel;
      const amount = Number(value) || 0;
      if (amount > 0 && amount < 0.01) return `$${{amount.toFixed(4)}}`;
      return `$${{amount.toFixed(2)}}`;
    }};
    const pct = value => `${{((Number(value) || 0) * 100).toFixed(1)}}%`;
    const short = (value, fallback = 'Unknown') => value || fallback;
    const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({{
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }}[char]));
    const truncate = (value, size = 54) => {{
      const text = short(value, '');
      return text.length > size ? `${{text.slice(0, size - 1)}}…` : text;
    }};
    function optionize(select, values) {{
      [...new Set(values.filter(Boolean))].sort().forEach(value => {{
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }});
    }}
    optionize(modelEl, data.map(row => row.model));
    optionize(effortEl, data.map(row => row.effort));
    if (pricingConfigured && pricingSource.url) {{
      const sourceParts = [
        pricingSource.name || 'Pricing source',
        pricingSource.tier ? `${{pricingSource.tier}} tier` : '',
        pricingSource.fetched_at ? `fetched ${{pricingSource.fetched_at}}` : '',
      ].filter(Boolean);
      document.getElementById('pricingSource').textContent = `Estimated costs use ${{sourceParts.join(', ')}}; internal Codex labels may use marked best-guess estimates.`;
    }}
    function filtered() {{
      const term = searchEl.value.trim().toLowerCase();
      const model = modelEl.value;
      const effort = effortEl.value;
      const pricingStatus = pricingStatusEl.value;
      const rows = data.filter(row => {{
        const haystack = [row.thread_name, row.cwd, row.model, row.effort, row.session_id, row.turn_id].join(' ').toLowerCase();
        const statusMatches = !pricingStatus
          || (pricingStatus === 'official' && row.pricing_model && !row.pricing_estimated)
          || (pricingStatus === 'estimated' && row.pricing_estimated)
          || (pricingStatus === 'unpriced' && !row.pricing_model);
        return (!term || haystack.includes(term)) && (!model || row.model === model) && (!effort || row.effort === effort) && statusMatches;
      }});
      rows.sort((a, b) => {{
        if (sortEl.value === 'cost') return Number(b.estimated_cost_usd || 0) - Number(a.estimated_cost_usd || 0);
        if (sortEl.value === 'time') return String(b.event_timestamp).localeCompare(String(a.event_timestamp));
        if (sortEl.value === 'cache') return Number(a.cache_ratio || 0) - Number(b.cache_ratio || 0);
        if (sortEl.value === 'context') return Number(b.context_window_percent || 0) - Number(a.context_window_percent || 0);
        return Number(b.total_tokens || 0) - Number(a.total_tokens || 0);
      }});
      return rows;
    }}
    function render() {{
      const rows = filtered();
      rowsEl.textContent = '';
      document.getElementById('visibleCalls').textContent = number.format(rows.length);
      document.getElementById('totalTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0));
      document.getElementById('cachedTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0));
      document.getElementById('reasoningTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.reasoning_output_tokens || 0), 0));
      const estimatedCost = rows.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
      const pricedTokens = rows.reduce((sum, row) => sum + (row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      const estimatedTokens = rows.reduce((sum, row) => sum + (row.pricing_estimated ? Number(row.total_tokens || 0) : 0), 0);
      const unpricedTokens = rows.reduce((sum, row) => sum + (!row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      const totalTokens = rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
      document.getElementById('estimatedCost').textContent = pricingConfigured ? money(estimatedCost) : 'Not configured';
      document.getElementById('priceCoverage').textContent = pct(totalTokens ? pricedTokens / totalTokens : 0);
      document.getElementById('estimatedTokens').textContent = number.format(estimatedTokens);
      document.getElementById('unpricedTokens').textContent = number.format(unpricedTokens);
      for (const row of rows.slice(0, 500)) {{
        const tr = document.createElement('tr');
        const flags = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
        tr.innerHTML = `
          <td>${{escapeHtml(truncate(row.event_timestamp, 20))}}</td>
          <td title="${{escapeHtml(short(row.session_id))}}">${{escapeHtml(truncate(row.thread_name || row.session_id))}}</td>
          <td><span class="pill">${{escapeHtml(short(row.model))}}</span></td>
          <td>${{escapeHtml(short(row.effort))}}</td>
          <td class="num">${{number.format(row.total_tokens || 0)}}</td>
          <td class="num">${{escapeHtml(row.pricing_estimated ? `${{money(row.estimated_cost_usd)}}*` : money(row.estimated_cost_usd))}}</td>
          <td class="num">${{pct(row.cache_ratio)}}</td>
          <td><div class="flags">${{flags.slice(0, 2).map(flag => `<span class="flag">${{escapeHtml(flag)}}</span>`).join('')}}</div></td>
        `;
        tr.addEventListener('mouseenter', () => showDetail(row));
        rowsEl.appendChild(tr);
      }}
    }}
    function showDetail(row) {{
      const fields = [
        ['Thread', row.thread_name || row.session_id],
        ['Session', row.session_id],
        ['Turn', row.turn_id],
        ['Timestamp', row.event_timestamp],
        ['Model', row.model],
        ['Reasoning', row.effort],
        ['Cwd', row.cwd],
        ['Last call total', number.format(row.total_tokens || 0)],
        ['Last call input', number.format(row.input_tokens || 0)],
        ['Cached input', number.format(row.cached_input_tokens || 0)],
        ['Uncached input', number.format(row.uncached_input_tokens || 0)],
        ['Output', number.format(row.output_tokens || 0)],
        ['Reasoning output', number.format(row.reasoning_output_tokens || 0)],
        ['Estimated cost', money(row.estimated_cost_usd)],
        ['Pricing model', row.pricing_model || 'No configured price'],
        ['Pricing status', row.pricing_estimated ? 'Best-guess estimate' : row.pricing_model ? 'Configured price' : 'No configured price'],
        ['Estimated cache savings', money(row.estimated_cache_savings_usd)],
        ['Efficiency signals', Array.isArray(row.efficiency_flags) && row.efficiency_flags.length ? row.efficiency_flags.join(', ') : 'None'],
        ['Session cumulative', number.format(row.cumulative_total_tokens || 0)],
        ['Context window', number.format(row.model_context_window || 0)],
        ['Context use', pct(row.context_window_percent)],
        ['Source line', `${{row.source_file}}:${{row.line_number}}`],
      ];
      detailEl.innerHTML = '<dl>' + fields.map(([key, value]) => `<dt>${{escapeHtml(key)}}</dt><dd>${{escapeHtml(short(value))}}</dd>`).join('') + '</dl>';
    }}
    [searchEl, modelEl, effortEl, pricingStatusEl, sortEl].forEach(el => el.addEventListener('input', render));
    render();
  </script>
</body>
</html>
"""
