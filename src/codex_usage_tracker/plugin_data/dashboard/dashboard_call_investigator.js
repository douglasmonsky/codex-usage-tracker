(() => {
  function createCallInvestigator(deps) {
    const {
      number,
      pct,
      escapeHtml,
      short,
      formatTimestamp,
      t,
      tf,
      moneyText,
      creditsText,
      tooltipAttributes,
      usageCreditValue,
      rowInputTokens,
      cachedInputTokens,
      uncachedInputTokens,
      outputTokens,
      rowReasoningTokens,
      callAccountingDelta,
      cacheDiagnostic,
      adjacentCalls,
      rowThreadLabel,
      rowAttachment,
      translateEffort,
      pricingStatusText,
      usageCreditStatusLabel,
      usageCreditsWithStatus,
      callInitiatorPuck,
      callInitiatorText,
      tableUrlForRow,
      signedNumber,
      signedPct,
      threshold,
      getSelectedRecordId,
      setSelectedRecordId,
      getRowByRecordId,
      getContextRuntime,
      setContextApiEnabled,
      renderDashboard,
      showDetail,
      updateLoadMoreControl,
      rowsEl,
      detailEl,
      pagerEl,
      tableTitleEl,
      tableCaptionEl,
      defaultContextEntries,
    } = deps;
    const contextRequestState = new Map();
    const contextPayloadState = new Map();

    function runtime() {
      return getContextRuntime ? getContextRuntime() : {};
    }

    function callMetricCard(label, value, badge = '', title = '') {
      return `
        <div class="call-metric-card" ${title ? tooltipAttributes(title) : ''}>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          ${badge ? `<small>${escapeHtml(badge)}</small>` : ''}
        </div>
      `;
    }

    function callDiagnosticPucks(row, previous) {
      const primary = cacheDiagnostic(row, previous);
      const pucks = [`<span class="flag signal-puck diagnostic-${escapeHtml(primary.key)}">${escapeHtml(primary.label)}</span>`];
      if (previous && uncachedInputTokens(row) > Math.max(uncachedInputTokens(previous) * 2, 1000) && primary.key !== 'spike') {
        pucks.push(`<span class="flag signal-puck diagnostic-spike">${escapeHtml(t('call.cache_spike'))}</span>`);
      }
      if (Number(row.context_window_percent || 0) >= threshold('high_context_percent', 0.6)) {
        pucks.push(`<span class="flag signal-puck">${escapeHtml(t('flag.high_context_use'))}</span>`);
      }
      return pucks.join('');
    }

    function deltaComparisonRows(row, previous) {
      if (!previous) return [];
      const delta = callAccountingDelta(row, previous);
      return [
        {
          label: t('metric.last_call_input'),
          value: signedNumber(delta.input),
          detail: `${number.format(rowInputTokens(previous))} -> ${number.format(rowInputTokens(row))}`,
        },
        {
          label: t('metric.cached_input'),
          value: signedNumber(delta.cached),
          detail: `${number.format(cachedInputTokens(previous))} -> ${number.format(cachedInputTokens(row))}`,
        },
        {
          label: t('metric.uncached_input'),
          value: signedNumber(delta.uncached),
          detail: `${number.format(uncachedInputTokens(previous))} -> ${number.format(uncachedInputTokens(row))}`,
        },
        {
          label: t('metric.output'),
          value: signedNumber(delta.output),
          detail: `${number.format(outputTokens(previous))} -> ${number.format(outputTokens(row))}`,
        },
        {
          label: t('metric.reasoning_output'),
          value: signedNumber(delta.reasoning),
          detail: `${number.format(rowReasoningTokens(previous))} -> ${number.format(rowReasoningTokens(row))}`,
        },
        {
          label: t('metric.cache_ratio'),
          value: signedPct(delta.cacheRatio),
          detail: `${pct(previous.cache_ratio)} -> ${pct(row.cache_ratio)}`,
        },
      ];
    }

    function renderCacheVerdict(row, previous, diagnostic, callPosition) {
      const delta = previous ? callAccountingDelta(row, previous) : null;
      const deltaLine = delta
        ? `${t('metric.uncached_input')}: ${signedNumber(delta.uncached)}. ${t('metric.cached_input')}: ${signedNumber(delta.cached)}. ${t('metric.cache_ratio')}: ${signedPct(delta.cacheRatio)}.`
        : t('call.no_previous');
      return `
        <div class="cache-verdict">
          <div class="cache-verdict-main">
            <div class="flags">${callDiagnosticPucks(row, previous)}</div>
            <p>${escapeHtml(diagnostic.body)}</p>
          </div>
          <div class="cache-verdict-meta">
            <span>${escapeHtml(`${t('metric.cache_ratio')}: ${pct(row.cache_ratio)}`)}</span>
            <span>${escapeHtml(deltaLine)}</span>
            <span>${escapeHtml(tf('call.position', { position: callPosition }))}</span>
          </div>
        </div>
      `;
    }

    function renderDeltaCards(row, previous) {
      if (!previous) {
        return `<p class="muted">${escapeHtml(t('call.no_previous'))}</p>`;
      }
      return `
        <p class="diagnostic-interpretation">${escapeHtml(deltaInterpretation(row, previous))}</p>
        <div class="call-delta-grid">
          ${deltaComparisonRows(row, previous).map(item => callMetricCard(item.label, item.value, item.detail)).join('')}
        </div>
      `;
    }

    function contextStateRecord(row) {
      const key = row.record_id || '';
      return key ? contextPayloadState.get(key) : null;
    }

    function loadedContextPayload(row) {
      const record = contextStateRecord(row);
      return record && record.status === 'loaded' ? record.payload : null;
    }

    function contextEvidenceStats(row) {
      const payload = loadedContextPayload(row);
      if (!payload) return null;
      const entries = Array.isArray(payload.entries) ? payload.entries : [];
      const omitted = payload.omitted || {};
      const totalEntries = Number(omitted.total_entries ?? entries.length);
      const visibleChars = Number(payload.visible_char_count ?? entries.reduce((sum, entry) => sum + String(entry.text || '').length, 0));
      const fallbackEstimate = Math.ceil(visibleChars / 4);
      const visibleTokenEstimate = Number(payload.visible_token_estimate ?? fallbackEstimate);
      const hiddenGap = Math.max(uncachedInputTokens(row) - visibleTokenEstimate, 0);
      return {
        entries: entries.length,
        totalEntries: Number.isFinite(totalEntries) ? totalEntries : entries.length,
        visibleChars,
        visibleTokenEstimate,
        estimator: payload.visible_token_estimator || 'chars_per_4_fallback',
        hiddenGap,
        source: payload.source || {},
      };
    }

    function contextDisabledAttr() {
      const fileMode = window.location.protocol === 'file:';
      const { apiToken, contextApiEnabled } = runtime();
      return fileMode || !apiToken || !contextApiEnabled ? ' disabled' : '';
    }

    function deltaInterpretation(row, previous) {
      const delta = callAccountingDelta(row, previous);
      const uncached = delta.uncached;
      const cached = delta.cached;
      if (uncached > 0 && cached < 0) {
        return `Fresh input rose by ${number.format(uncached)} while cached input fell by ${number.format(Math.abs(cached))}; this is the classic cache-drop profile.`;
      }
      if (uncached > 0) {
        return `Fresh input increased by ${number.format(uncached)} from the previous call; inspect evidence for new files, tool results, or rewritten context.`;
      }
      if (uncached < 0 && cached >= 0) {
        return `Fresh input fell by ${number.format(Math.abs(uncached))} while cached input increased, so this call is reusing context more efficiently than the previous one.`;
      }
      return 'Token accounting is broadly stable compared with the previous call in this resolved thread.';
    }

    function diagnosticNextStep(row, diagnostic, previous) {
      if (diagnostic.key === 'post-compaction') {
        return 'Check the loaded evidence for an explicit compaction marker or replacement history before interpreting the cache delta.';
      }
      if (diagnostic.key === 'cold') {
        return 'Compare the previous call, then inspect the loaded evidence to see what fresh context was sent after the cache miss.';
      }
      if (diagnostic.key === 'spike') {
        return 'Inspect the most recent evidence entries first; the spike is in fresh uncached input, not cached history.';
      }
      if (diagnostic.key === 'warm') {
        return `Cache reuse is healthy; focus on the ${number.format(uncachedInputTokens(row))} uncached tokens that were still billed as fresh input.`;
      }
      if (previous) return 'Use the delta cards to locate whether the change is cached input, uncached input, or output/reasoning.';
      return 'Use the loaded evidence if the aggregate totals are not enough to understand this isolated call.';
    }

    function renderInvestigationReadout(row, previous, diagnostic, callPosition) {
      const exact = `${number.format(rowInputTokens(row))} input tokens = ${number.format(cachedInputTokens(row))} cached + ${number.format(uncachedInputTokens(row))} uncached; ${number.format(outputTokens(row))} output tokens; ${pct(row.cache_ratio)} cache reuse.`;
      const derived = previous
        ? deltaInterpretation(row, previous)
        : 'No previous call is loaded for this resolved thread, so call-to-call deltas are unavailable.';
      const stats = contextEvidenceStats(row);
      const evidence = stats
        ? `Evidence analyzed: ${number.format(stats.totalEntries)} selected-turn entries, ${number.format(stats.visibleChars)} visible redacted chars, ${number.format(stats.visibleTokenEstimate)} visible tokens via ${stats.estimator}. ${number.format(stats.entries)} entries rendered initially.`
        : 'Evidence is loading from the local JSONL source. Aggregate token counts are exact, but visible-context attribution needs that runtime evidence.';
      return `
        <section class="call-diagnostic-section readout">
          <div class="section-heading compact">
            <h3>Investigation readout</h3>
            <span class="evidence-chip exact">Exact + derived + on-demand evidence</span>
          </div>
          <div class="readout-grid">
            <div class="readout-card">
              <span>Exact callback accounting</span>
              <p>${escapeHtml(exact)}</p>
            </div>
            <div class="readout-card">
              <span>Compared with previous call</span>
              <p>${escapeHtml(derived)}</p>
            </div>
            <div class="readout-card">
              <span>Evidence state</span>
              <p>${escapeHtml(evidence)}</p>
            </div>
            <div class="readout-card">
              <span>Next diagnostic move</span>
              <p>${escapeHtml(diagnosticNextStep(row, diagnostic, previous))}</p>
              <small>${escapeHtml(tf('call.position', { position: callPosition }))}</small>
            </div>
          </div>
        </section>
      `;
    }

    function renderCallNavigation(row, previous, next) {
      const backUrl = tableUrlForRow(row);
      return `
        <div class="call-nav">
          <a class="toolbar-button" href="${escapeHtml(backUrl)}">${escapeHtml(t('button.back_to_dashboard'))}</a>
          <button class="toolbar-button" type="button" data-call-nav-record="${escapeHtml(previous?.record_id || '')}" ${previous ? '' : 'disabled'}>${escapeHtml(t('button.previous_call'))}</button>
          <button class="toolbar-button" type="button" data-call-nav-record="${escapeHtml(next?.record_id || '')}" ${next ? '' : 'disabled'}>${escapeHtml(t('button.next_call'))}</button>
          <button class="toolbar-button" type="button" data-copy-call-link="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.copy_link'))}</button>
        </div>
      `;
    }

    function renderCallInvestigator(rows) {
      const rowByRecordId = getRowByRecordId();
      const row = rowByRecordId.get(getSelectedRecordId()) || rows.find(candidate => candidate.record_id === getSelectedRecordId());
      updateLoadMoreControl({ total: 0, end: 0 }, 'table.calls');
      pagerEl.hidden = true;
      tableTitleEl.textContent = t('dashboard.view.call');
      tableCaptionEl.textContent = getSelectedRecordId()
        ? tf('caption.call_investigator', { record: short(getSelectedRecordId(), '').slice(0, 12) })
        : t('call.open_hint');
      if (!row) {
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="11">${escapeHtml(t('call.not_found'))}</td></tr>`;
        detailEl.textContent = t('dashboard.detail.empty');
        return;
      }
      setSelectedRecordId(row.record_id || getSelectedRecordId());
      const { calls, index, previous, next } = adjacentCalls(row);
      const diagnostic = cacheDiagnostic(row, previous);
      const threadLabel = rowThreadLabel(row);
      const callPosition = index >= 0 ? `${number.format(index + 1)} / ${number.format(calls.length)}` : t('state.unknown');
      const evidenceStats = contextEvidenceStats(row);
      const visibleEstimateValue = evidenceStats
        ? `~${number.format(evidenceStats.visibleTokenEstimate)} tokens`
        : 'Not loaded yet';
      const hiddenEstimateValue = evidenceStats
        ? `~${number.format(evidenceStats.hiddenGap)} tokens`
        : 'Not loaded yet';
      rowsEl.innerHTML = `
        <tr class="call-investigator-row">
          <td colspan="11">
            <article class="call-investigator" data-record-id="${escapeHtml(row.record_id || '')}">
              <header class="call-investigator-header">
                <div>
                  <p class="eyebrow">${escapeHtml(t('dashboard.view.call'))}</p>
                  <h3>${escapeHtml(threadLabel)}</h3>
                  <p class="muted">${escapeHtml(formatTimestamp(row.event_timestamp))} · ${escapeHtml(short(row.model))} · ${escapeHtml(translateEffort(short(row.effort)))} · ${callInitiatorPuck(row)}</p>
                </div>
                ${renderCallNavigation(row, previous, next)}
              </header>
              ${renderInvestigationReadout(row, previous, diagnostic, callPosition)}
              <section class="call-diagnostic-section exact">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.exact_accounting'))}</h3>
                  <span class="evidence-chip exact">${escapeHtml(t('call.exact_label'))}</span>
                </div>
                <div class="call-metric-grid">
                  ${callMetricCard(t('metric.last_call_input'), number.format(rowInputTokens(row)), t('metric.last_call_total'))}
                  ${callMetricCard(t('metric.cached_input'), number.format(cachedInputTokens(row)), pct(row.cache_ratio))}
                  ${callMetricCard(t('metric.uncached_input'), number.format(uncachedInputTokens(row)), t('call.exact_label'))}
                  ${callMetricCard(t('metric.output'), number.format(outputTokens(row)), t('metric.reasoning_output'))}
                  ${callMetricCard(t('table.source'), callInitiatorText(row), t('call.exact_label'))}
                  ${callMetricCard(t('metric.estimated_cost'), moneyText(row.estimated_cost_usd), pricingStatusText(row))}
                  ${callMetricCard(t('metric.codex_credits'), creditsText(usageCreditValue(row)), usageCreditStatusLabel(row), usageCreditsWithStatus(row))}
                </div>
              </section>
              <section class="call-diagnostic-section delta">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.cache_accounting_delta'))}</h3>
                  <span class="evidence-chip derived">${escapeHtml(t('call.derived_label'))}</span>
                </div>
                ${renderCacheVerdict(row, previous, diagnostic, callPosition)}
                ${renderDeltaCards(row, previous)}
              </section>
              <section class="call-diagnostic-section context">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.context_estimate'))}</h3>
                  <span class="evidence-chip estimated">${escapeHtml(t('call.estimated_label'))}</span>
                </div>
                <div class="call-metric-grid two">
                  ${callMetricCard(t('metric.uncached_input'), number.format(uncachedInputTokens(row)), t('call.exact_label'))}
                  ${callMetricCard(t('call.visible_estimate'), visibleEstimateValue, evidenceStats ? `${number.format(evidenceStats.visibleChars)} analyzed chars · ${evidenceStats.estimator}` : t('call.evidence_label'))}
                  ${callMetricCard(t('call.hidden_estimate'), hiddenEstimateValue, evidenceStats ? 'Uncached input minus visible estimate' : t('call.evidence_label'))}
                </div>
                <p class="muted">${escapeHtml(t('call.context_estimate_hint'))}</p>
              </section>
              <section class="call-diagnostic-section raw-evidence">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.raw_evidence'))}</h3>
                  <span class="evidence-chip evidence">${escapeHtml(t('call.evidence_label'))}</span>
                </div>
                ${contextControls(row, { automatic: true })}
              </section>
            </article>
          </td>
        </tr>
      `;
      const article = rowsEl.querySelector('.call-investigator');
      if (article) {
        bindContextButtons(row, article);
        maybeAutoloadEvidence(row, article);
      }
      detailEl.textContent = t('dashboard.detail.empty');
    }

    function contextControls(row, options = {}) {
      const automatic = Boolean(options.automatic);
      const { apiToken, contextApiEnabled } = runtime();
      const fileMode = window.location.protocol === 'file:';
      const apiMissing = !apiToken;
      const apiDisabled = !contextApiEnabled;
      const disabled = contextDisabledAttr();
      const hint = fileMode
        ? t('context.file_hint')
        : apiMissing
          ? t('context.token_required')
          : apiDisabled
            ? t('context.disabled_hint')
            : t('context.ready_hint');
      const enableButton = !fileMode && !apiMissing && apiDisabled
        ? `<button class="context-button" type="button" data-context-enable>${escapeHtml(t('button.enable_context_loading'))}</button>`
        : '';
      const stored = contextStateRecord(row);
      const requestState = contextStateForRow(row);
      const toolOutputToggle = stored?.status === 'loaded' && !disabled
        ? `<button class="context-button secondary" type="button" data-context-toggle-tool-output>${escapeHtml(requestState.includeToolOutput ? t('button.hide_tool_output') : t('button.show_tool_output'))}</button>`
        : '';
      const manualLoadButton = !automatic && stored?.status !== 'loaded'
        ? `<button class="context-button" type="button" data-context-load${disabled}>${escapeHtml(t('button.show_turn_evidence'))}</button>`
        : '';
      const actionHtml = [manualLoadButton, toolOutputToggle, enableButton].filter(Boolean).join('');
      const resultHtml = stored?.status === 'loaded'
        ? renderContext(stored.payload)
        : stored?.status === 'loading'
          ? `<p class="context-note">${escapeHtml(t('context.loading'))}</p>`
          : stored?.status === 'error'
            ? `<p class="context-note">${escapeHtml(stored.message)}</p>`
            : `<p class="context-note">${escapeHtml(automatic && !disabled ? t('context.auto_loading') : hint)}</p>`;
      return `
        ${actionHtml ? `<div class="context-actions">${actionHtml}</div>` : ''}
        <div id="contextResult" class="context-result">${resultHtml}</div>
      `;
    }

    function bindContextButtons(row, root = detailEl) {
      const contextResult = root.querySelector('#contextResult');
      root.querySelectorAll('[data-context-load]').forEach(button => {
        button.addEventListener('click', () => {
          loadContext(row, defaultContextRequest(), contextResult);
        });
      });
      root.querySelectorAll('[data-context-toggle-tool-output]').forEach(button => {
        button.addEventListener('click', () => {
          const current = contextStateForRow(row);
          loadContext(row, { includeToolOutput: !current.includeToolOutput }, contextResult);
        });
      });
      root.querySelectorAll('[data-context-enable]').forEach(button => {
        button.addEventListener('click', () => enableContextApi(row, contextResult));
      });
      root.querySelectorAll('[data-context-compaction-history]').forEach(button => {
        if (contextResult && contextResult.contains(button)) return;
        button.addEventListener('click', () => {
          loadContext(row, { includeCompactionHistory: true }, contextResult);
        });
      });
      if (contextResult) {
        contextResult.addEventListener('click', event => {
          if (!(event.target instanceof Element)) return;
          const button = event.target.closest('[data-context-entry-load-output], [data-context-load-older], [data-context-compaction-history]');
          if (!button) return;
          if (button.matches('[data-context-entry-load-output]')) {
            loadContext(row, { includeToolOutput: true }, contextResult);
            return;
          }
          if (button.matches('[data-context-load-older]')) {
            loadContext(row, { maxEntries: Number(button.dataset.contextMaxEntries || 0) }, contextResult);
            return;
          }
          if (button.matches('[data-context-compaction-history]')) {
            loadContext(row, { includeCompactionHistory: true }, contextResult);
          }
        });
      }
    }

    function maybeAutoloadEvidence(row, root) {
      if (!row.record_id || contextStateRecord(row)) return;
      const { apiToken, contextApiEnabled } = runtime();
      if (!apiToken || !contextApiEnabled || window.location.protocol === 'file:') return;
      const target = root.querySelector('#contextResult');
      window.setTimeout(() => {
        if (!contextStateRecord(row)) {
          loadContext(row, defaultContextRequest(), target);
        }
      }, 0);
    }

    async function enableContextApi(row, targetElement = null) {
      const target = targetElement || document.getElementById('contextResult');
      if (!target) return;
      target.innerHTML = `<p class="context-note">${escapeHtml(t('context.loading'))}</p>`;
      try {
        const params = new URLSearchParams({ enabled: '1', _: String(Date.now()) });
        const { apiToken } = runtime();
        const response = await fetch(`/api/context-settings?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(tf('context.settings_http', { status: response.status }));
        }
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error);
        setContextApiEnabled(Boolean(payload.context_api_enabled));
        if (runtime().activeView === 'call') {
          renderDashboard();
        } else {
          showDetail(row);
          const nextTarget = document.getElementById('contextResult');
          if (nextTarget && runtime().contextApiEnabled) {
            nextTarget.innerHTML = `<p class="context-note">${escapeHtml(t('context.enabled_note'))}</p>`;
          }
        }
      } catch (error) {
        target.innerHTML = `<p class="context-note">${escapeHtml(error.message || String(error))}</p>`;
      }
    }

    function contextStateForRow(row) {
      const key = row.record_id || '';
      return key && contextRequestState.has(key)
        ? contextRequestState.get(key)
        : defaultContextRequest();
    }

    function defaultContextRequest() {
      return {
        includeToolOutput: true,
        includeCompactionHistory: false,
        maxChars: 0,
        maxEntries: defaultContextEntries,
      };
    }

    function nextContextState(row, options) {
      const base = contextStateForRow(row);
      const updates = typeof options === 'boolean' ? { includeToolOutput: options } : (options || {});
      const next = { ...base, ...updates };
      next.includeToolOutput = Boolean(next.includeToolOutput);
      next.includeCompactionHistory = Boolean(next.includeCompactionHistory);
      if (next.maxEntries === undefined) next.maxEntries = defaultContextEntries;
      if (next.maxChars === undefined) next.maxChars = null;
      if (row.record_id) contextRequestState.set(row.record_id, next);
      return next;
    }

    async function loadContext(row, options = {}, targetElement = null) {
      const target = targetElement || document.getElementById('contextResult');
      if (!target) return;
      if (!row.record_id) {
        target.innerHTML = `<p class="context-note">${escapeHtml(t('context.no_record_id'))}</p>`;
        return;
      }
      contextPayloadState.set(row.record_id, { status: 'loading' });
      target.innerHTML = `<p class="context-note">${escapeHtml(t('context.loading'))}</p>`;
      const requestState = nextContextState(row, options);
      const params = new URLSearchParams({ record_id: row.record_id });
      if (requestState.includeToolOutput) params.set('include_tool_output', '1');
      if (requestState.includeCompactionHistory) params.set('include_compaction_history', '1');
      if (requestState.maxChars !== null && requestState.maxChars !== undefined) {
        params.set('max_chars', String(requestState.maxChars));
      }
      if (requestState.maxEntries !== null && requestState.maxEntries !== undefined) {
        params.set('max_entries', String(requestState.maxEntries));
      }
      try {
        const { apiToken } = runtime();
        const response = await fetch(`/api/context?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) {
          const errorText = response.status === 404
            ? t('context.api_unavailable')
            : tf('context.api_http', { status: response.status });
          throw new Error(errorText);
        }
        const payload = await response.json();
        contextPayloadState.set(row.record_id, { status: 'loaded', payload });
        target.innerHTML = renderContext(payload);
        if (runtime().activeView === 'call') renderDashboard();
      } catch (error) {
        const message = error.message || String(error);
        contextPayloadState.set(row.record_id, { status: 'error', message });
        target.innerHTML = `<p class="context-note">${escapeHtml(message)}</p>`;
      }
    }

    function contextLimitActions(payload) {
      const omitted = payload.omitted || {};
      const buttons = [];
      const maxEntries = Number(omitted.max_entries || defaultContextEntries);
      if (Number(omitted.older_entries || 0) > 0) {
        const nextEntries = maxEntries > 0 ? Math.max(maxEntries + defaultContextEntries, maxEntries * 2) : 0;
        buttons.push(`<button class="context-entry-action" type="button" data-context-load-older data-context-max-entries="${escapeHtml(String(nextEntries))}">${escapeHtml(t('button.load_older_context'))}</button>`);
      }
      return buttons.length ? `<div class="context-followup-actions">${buttons.join('')}</div>` : '';
    }

    function tokenUsageNumber(value) {
      const numeric = Number(value || 0);
      return Number.isFinite(numeric) ? number.format(numeric) : '0';
    }

    function tokenUsageRows(usage) {
      if (!usage || typeof usage !== 'object') return '';
      const input = Number(usage.input_tokens || 0);
      const cached = Number(usage.cached_input_tokens || 0);
      const uncached = Number(usage.uncached_input_tokens ?? Math.max(input - cached, 0));
      return `
        <td>${escapeHtml(tokenUsageNumber(input))}</td>
        <td>${escapeHtml(tokenUsageNumber(cached))}</td>
        <td>${escapeHtml(tokenUsageNumber(uncached))}</td>
        <td>${escapeHtml(tokenUsageNumber(usage.output_tokens))}</td>
        <td>${escapeHtml(tokenUsageNumber(usage.reasoning_output_tokens))}</td>
        <td>${escapeHtml(tokenUsageNumber(usage.total_tokens))}</td>
      `;
    }

    function tokenUsageScopeLabel(entry, payload, index) {
      const sourceLine = Number(payload?.source?.line_number || 0);
      if (sourceLine && Number(entry.line_number || 0) === sourceLine) return t('context.token_scope_selected');
      if (index === 0) return t('context.token_scope_previous');
      return t('context.token_scope_earlier');
    }

    function renderContextTokenUsage(entry, payload, index) {
      const usage = entry.token_usage || {};
      const rows = [
        [tokenUsageScopeLabel(entry, payload, index), usage.last_token_usage],
        [t('context.token_scope_session'), usage.total_token_usage],
      ].filter(([, value]) => value && typeof value === 'object');
      if (!rows.length) return '';
      return `
        <div class="context-token-breakdown" aria-label="${escapeHtml(t('context.token_breakdown'))}">
          <table>
            <thead>
              <tr>
                <th>${escapeHtml(t('context.token_type'))}</th>
                <th>${escapeHtml(t('context.token_input'))}</th>
                <th>${escapeHtml(t('context.token_cached'))}</th>
                <th>${escapeHtml(t('context.token_uncached'))}</th>
                <th>${escapeHtml(t('context.token_output'))}</th>
                <th>${escapeHtml(t('context.token_reasoning'))}</th>
                <th>${escapeHtml(t('context.token_total'))}</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(([label, usageValue]) => `<tr><th>${escapeHtml(label)}</th>${tokenUsageRows(usageValue)}</tr>`).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderContextCompaction(entry) {
      const compaction = entry.compaction || {};
      if (!compaction.replacement_history_available) return '';
      const replacementEntries = Array.isArray(compaction.replacement_history) ? compaction.replacement_history : [];
      const history = replacementEntries.length
        ? `
          <div class="context-replacement-history" tabindex="0" aria-label="${escapeHtml(t('context.compaction_replacement'))}">
            <h4>${escapeHtml(t('context.compaction_replacement'))}</h4>
            ${replacementEntries.map(item => `
              <div class="context-replacement-entry">
                <strong>${escapeHtml(item.label || 'replacement item')}</strong>
                <pre>${escapeHtml(item.text || '')}</pre>
              </div>
            `).join('')}
          </div>
        `
        : `<button class="context-entry-action" type="button" data-context-compaction-history>${escapeHtml(t('button.show_compaction_history'))}</button>`;
      return `
        <div class="context-compaction">
          <strong>${escapeHtml(t('context.compaction_detected'))}</strong>
          <span>${escapeHtml(tf('context.compaction_replacement_count', { count: number.format(compaction.replacement_entry_count || 0) }))}</span>
          ${history}
        </div>
      `;
    }

    function renderThreadAnchors(payload) {
      const anchors = payload.call_anchors || payload.thread_anchors || {};
      if (!anchors.available) return '';
      const seen = new Set();
      const candidates = [
        ['before', t('context.anchor_before'), anchors.before_message || anchors.selected_lead_in],
        ['latest', t('context.anchor_latest'), anchors.latest_message || anchors.after_message],
      ].filter(([, , anchor]) => anchor && anchor.text).filter(([, , anchor]) => {
        const identity = `${anchor.line_number || ''}:${anchor.role || ''}:${anchor.text || ''}`;
        if (seen.has(identity)) return false;
        seen.add(identity);
        return true;
      });
      if (!candidates.length) return '';
      return `
        <div class="context-anchor-panel">
          <div class="context-anchor-header">
            <div>
              <strong>${escapeHtml(t('context.thread_anchors'))}</strong>
              <span>${escapeHtml(t('context.thread_anchors_hint'))}</span>
            </div>
            <span>${escapeHtml(tf('context.anchor_count', { count: number.format(anchors.message_count || candidates.length) }))}</span>
          </div>
          <div class="context-anchor-grid">
            ${candidates.map(([key, label, anchor]) => renderThreadAnchorCard(key, label, anchor)).join('')}
          </div>
        </div>
      `;
    }

    function renderThreadAnchorCard(key, label, anchor) {
      const role = anchor.role || 'unknown';
      const meta = [
        formatTimestamp(anchor.timestamp, ''),
        anchor.line_number ? tf('context.line', { line: anchor.line_number }) : '',
      ].filter(Boolean).join(' - ');
      return `
        <div class="context-anchor-card context-anchor-${escapeHtml(key)}">
          <div class="context-anchor-card-head">
            <span>${escapeHtml(label)}</span>
            <span class="context-anchor-role">${escapeHtml(role)}</span>
          </div>
          ${meta ? `<div class="context-anchor-meta">${escapeHtml(meta)}</div>` : ''}
          <pre>${escapeHtml(anchor.text || '')}</pre>
        </div>
      `;
    }

    function contextEntryWindow(entries, payload) {
      const sourceLine = Number(payload?.source?.line_number || 0);
      const selectedIndex = entries.findIndex(entry => sourceLine && Number(entry.line_number || 0) === sourceLine);
      if (selectedIndex < 0) {
        return {
          start: Math.max(entries.length - 3, 0),
          end: Math.max(entries.length - 1, 0),
        };
      }
      let previousTokenIndex = -1;
      entries.forEach((entry, index) => {
        if (index < selectedIndex && entry && entry.token_usage) previousTokenIndex = index;
      });
      return {
        start: Math.max(previousTokenIndex + 1, 0),
        end: selectedIndex,
      };
    }

    function contextEntryBelongsToSelectedCall(index, windowRange) {
      return index >= windowRange.start && index <= windowRange.end;
    }

    function renderContext(payload) {
      const entries = Array.isArray(payload.entries) ? payload.entries : [];
      const source = payload.source || {};
      const omitted = payload.omitted || {};
      const note = [
        t('context.local_redacted'),
        payload.include_tool_output ? t('context.tool_included') : t('context.tool_omitted'),
        source.file ? tf('context.source', { file: source.file, line: source.line_number || '' }) : '',
        omitted.older_entries ? tf('context.older_omitted', { count: number.format(omitted.older_entries) }) : '',
        omitted.over_budget_chars ? tf('context.chars_omitted', { count: number.format(omitted.over_budget_chars) }) : '',
        Number(omitted.max_chars || 0) === 0 ? t('context.no_char_limit_active') : '',
      ].filter(Boolean).join(' ');
      const tokenEntryIndexes = new Map();
      entries.filter(entry => entry && entry.token_usage).forEach((entry, index) => {
        tokenEntryIndexes.set(entry, index);
      });
      const entryWindow = contextEntryWindow(entries, payload);
      const body = entries.map((entry, index) => {
        const meta = [formatTimestamp(entry.timestamp, ''), entry.line_number ? tf('context.line', { line: entry.line_number }) : ''].filter(Boolean).join(' - ');
        const outputAction = entry.tool_output_omitted && !payload.include_tool_output
          ? `<button class="context-entry-action" type="button" data-context-entry-load-output>${escapeHtml(t('button.show_tool_output'))}</button>`
          : '';
        const tokenUsage = renderContextTokenUsage(entry, payload, tokenEntryIndexes.get(entry) || 0);
        const compaction = renderContextCompaction(entry);
        const currentCallEntry = contextEntryBelongsToSelectedCall(index, entryWindow);
        const header = `
          <div class="context-entry-header">
            <span class="context-entry-title">${escapeHtml(entry.label || entry.type || 'entry')}</span>
            <span class="context-entry-meta">
              ${meta ? `<span>${escapeHtml(meta)}</span>` : ''}
              ${outputAction}
            </span>
          </div>
        `;
        const bodyHtml = `
          ${tokenUsage}
          ${compaction}
          <pre>${escapeHtml(entry.text || '')}</pre>
        `;
        if (!currentCallEntry) {
          return `
            <details class="context-entry context-entry-collapsed">
              <summary class="context-entry-summary">
                <span class="context-entry-title">${escapeHtml(entry.label || entry.type || 'entry')}</span>
                <span class="context-entry-meta">${meta ? escapeHtml(meta) : ''}</span>
              </summary>
              ${bodyHtml}
            </details>
          `;
        }
        return `
          <div class="context-entry context-entry-current">
            ${header}
            ${bodyHtml}
          </div>
        `;
      }).join('');
      return `<p class="context-note">${escapeHtml(note)}</p>${renderThreadAnchors(payload)}${contextLimitActions(payload)}${body || `<p class="context-note">${escapeHtml(t('state.no_context_entries'))}</p>`}`;
    }

    return Object.freeze({
      bindContextButtons,
      contextControls,
      contextStateRecord,
      renderCallInvestigator,
      renderContext,
    });
  }

  window.CodexUsageCallInvestigator = Object.freeze({ create: createCallInvestigator });
})();
