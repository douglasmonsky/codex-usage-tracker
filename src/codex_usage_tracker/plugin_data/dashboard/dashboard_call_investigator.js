(() => {
  function createCallInvestigator(deps) {
    const {
      number,
      pct,
      escapeHtml,
      short,
      formatTimestamp,
      formatDuration,
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
      fetchCallRecord,
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
    const contextUiState = new Map();
    const callDiagnostics = window.CodexUsageCallDiagnostics.create({
      number,
      pct,
      escapeHtml,
      t,
      tf,
      tooltipAttributes,
      rowInputTokens,
      cachedInputTokens,
      uncachedInputTokens,
      outputTokens,
      rowReasoningTokens,
      callAccountingDelta,
      cacheDiagnostic,
      signedNumber,
      signedPct,
      threshold,
    });
    const {
      callMetricCard,
      renderCacheVerdict,
      renderDeltaCards,
      renderInvestigationReadout,
    } = callDiagnostics;

    function runtime() {
      return getContextRuntime ? getContextRuntime() : {};
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
      const uncached = uncachedInputTokens(row);
      const serialized = payload.serialized_evidence || {};
      const serializedTokens = Number(serialized.raw_json_token_estimate || 0);
      const serializedChars = Number(serialized.raw_json_char_count || 0);
      const serializedDeferred = Boolean(serialized.deferred || serialized.deferred_buckets);
      const serializedBound = serializedTokens > 0 ? Math.min(serializedTokens, uncached) : 0;
      const visibleGap = Math.max(uncached - visibleTokenEstimate, 0);
      const serializedCandidate = serializedBound > visibleTokenEstimate ? serializedBound - visibleTokenEstimate : 0;
      const remainingAfterSerialized = serializedTokens > 0 ? Math.max(uncached - Math.max(visibleTokenEstimate, serializedBound), 0) : visibleGap;
      return {
        entries: entries.length,
        totalEntries: Number.isFinite(totalEntries) ? totalEntries : entries.length,
        visibleChars,
        visibleTokenEstimate,
        estimator: payload.visible_token_estimator || 'chars_per_4_fallback',
        visibleGap,
        hiddenGap: visibleGap,
        serializedTokens,
        serializedChars,
        serializedLineCount: Number(serialized.raw_line_count || 0),
        serializedEstimator: serialized.token_estimator || payload.visible_token_estimator || 'chars_per_4_fallback',
        serializedDeferred,
        serializedCandidate,
        remainingAfterSerialized,
        serializedBuckets: Array.isArray(serialized.buckets) ? serialized.buckets : [],
        serializedUpperBound: Boolean(serialized.upper_bound),
        contextMode: payload.context_mode || 'quick',
        source: payload.source || {},
      };
    }

    function contextDisabledAttr() {
      const fileMode = window.location.protocol === 'file:';
      const { apiToken, contextApiEnabled } = runtime();
      return fileMode || !apiToken || !contextApiEnabled ? ' disabled' : '';
    }

    function metadataValue(value, fallback = t('state.none')) {
      if (value === null || value === undefined || value === '') return fallback;
      return String(value);
    }

    function parentUpdatedAt(row) {
      return row.resolved_parent_session_updated_at || row.parent_session_updated_at || '';
    }

    function renderMetadataField(label, value) {
      return `
        <div class="metadata-field">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `;
    }

    function renderAggregateMetadata(row) {
      const sourceLine = row.source_file
        ? `${row.source_file}:${row.line_number || ''}`
        : t('state.unknown');
      const fields = [
        [t('filter.session'), metadataValue(row.session_id)],
        [t('detail.turn'), metadataValue(row.turn_id)],
        [t('table.initiated'), callInitiatorText(row)],
        [t('detail.thread_source'), metadataValue(row.thread_source, t('source.user'))],
        [t('detail.subagent_type'), metadataValue(row.subagent_type)],
        [t('detail.agent_role'), metadataValue(row.agent_role)],
        [t('detail.agent_nickname'), metadataValue(row.agent_nickname)],
        [t('detail.parent_session'), metadataValue(row.parent_session_id)],
        [t('detail.parent_updated'), parentUpdatedAt(row) ? formatTimestamp(parentUpdatedAt(row)) : t('state.none')],
        [t('detail.cwd'), metadataValue(row.cwd, t('state.unknown'))],
        [t('detail.project_cwd'), metadataValue(row.project_relative_cwd || '.', '.')],
        [t('detail.git_branch'), metadataValue(row.git_branch, t('state.unknown'))],
        [t('detail.remote_label'), metadataValue(row.git_remote_label)],
        [t('detail.remote_hash'), metadataValue(row.git_remote_hash)],
        [t('detail.credit_note'), metadataValue(row.usage_credit_note)],
        [t('detail.source_line'), sourceLine],
        [t('detail.context_window'), number.format(row.model_context_window || 0)],
      ];
      return `
        <section class="call-diagnostic-section metadata">
          <div class="section-heading compact">
            <h3>${escapeHtml(`${t('detail.raw_identifiers')} + ${t('detail.source_file_line')}`)}</h3>
            <span class="evidence-chip derived">${escapeHtml(t('detail.source_file_line'))}</span>
          </div>
          <div class="call-metadata-grid">
            ${fields.map(([label, value]) => renderMetadataField(label, value)).join('')}
          </div>
        </section>
      `;
    }

    function renderCallNavigation(row, previous, next) {
      const backUrl = tableUrlForRow(row);
      const previousRecordId = previous?.record_id || row.previous_record_id || '';
      const nextRecordId = next?.record_id || row.next_record_id || '';
      return `
        <div class="call-nav">
          <a class="toolbar-button" href="${escapeHtml(backUrl)}" data-dashboard-route="calls">${escapeHtml(t('button.back_to_dashboard'))}</a>
          <button class="toolbar-button" type="button" data-call-nav-record="${escapeHtml(previousRecordId)}" ${previousRecordId ? '' : 'disabled'}>${escapeHtml(t('button.previous_call'))}</button>
          <button class="toolbar-button" type="button" data-call-nav-record="${escapeHtml(nextRecordId)}" ${nextRecordId ? '' : 'disabled'}>${escapeHtml(t('button.next_call'))}</button>
          <button class="toolbar-button" type="button" data-copy-call-link="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.copy_link'))}</button>
        </div>
      `;
    }

    function renderCallInvestigator(rows) {
      const rowByRecordId = getRowByRecordId();
      const row = rowByRecordId.get(getSelectedRecordId()) || rows.find(candidate => candidate.record_id === getSelectedRecordId());
      if (row?.record_id) captureContextUiState(row.record_id);
      updateLoadMoreControl({ total: 0, end: 0 }, 'table.calls');
      pagerEl.hidden = true;
      tableTitleEl.textContent = t('dashboard.view.call');
      tableCaptionEl.textContent = getSelectedRecordId()
        ? tf('caption.call_investigator', { record: short(getSelectedRecordId(), '').slice(0, 12) })
        : t('call.open_hint');
      if (!row) {
        const selectedRecordId = getSelectedRecordId();
        if (selectedRecordId && fetchCallRecord) {
          rowsEl.innerHTML = `<tr><td class="empty-state" colspan="14">${escapeHtml(t('context.loading'))}</td></tr>`;
          detailEl.textContent = t('dashboard.detail.empty');
          fetchCallRecord(selectedRecordId).then(fetchedRow => {
            if (!fetchedRow && getSelectedRecordId() === selectedRecordId) {
              rowsEl.innerHTML = `<tr><td class="empty-state" colspan="14">${escapeHtml(t('call.not_found'))}</td></tr>`;
            }
          });
          return;
        }
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="14">${escapeHtml(t('call.not_found'))}</td></tr>`;
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
      const serializedUpperBoundValue = evidenceStats && evidenceStats.serializedTokens
        ? `~${number.format(evidenceStats.serializedTokens)} tokens`
        : 'Not loaded yet';
      const serializedCandidateValue = evidenceStats
        ? `~${number.format(evidenceStats.serializedCandidate)} tokens`
        : 'Not loaded yet';
      const remainingAfterSerializedValue = evidenceStats
        ? `~${number.format(evidenceStats.remainingAfterSerialized)} tokens`
        : 'Not loaded yet';
      rowsEl.innerHTML = `
        <tr class="call-investigator-row">
          <td colspan="14">
            <article class="call-investigator" data-record-id="${escapeHtml(row.record_id || '')}">
              <header class="call-investigator-header">
                <div>
                  <p class="eyebrow">${escapeHtml(t('dashboard.view.call'))}</p>
                  <h3>${escapeHtml(threadLabel)}</h3>
                  <p class="muted">${escapeHtml(formatTimestamp(row.event_timestamp))} · ${escapeHtml(short(row.model))} · ${escapeHtml(translateEffort(short(row.effort)))} · ${callInitiatorPuck(row)}</p>
                </div>
                ${renderCallNavigation(row, previous, next)}
              </header>
              ${renderInvestigationReadout(row, previous, diagnostic, callPosition, evidenceStats)}
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
                  ${callMetricCard(t('table.initiated'), callInitiatorText(row), t('call.exact_label'))}
                  ${callMetricCard(t('metric.estimated_cost'), moneyText(row.estimated_cost_usd), pricingStatusText(row))}
                  ${callMetricCard(t('metric.codex_credits'), creditsText(usageCreditValue(row)), usageCreditStatusLabel(row), usageCreditsWithStatus(row))}
                </div>
              </section>
              ${renderAggregateMetadata(row)}
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
                <div class="call-metric-grid context-attribution">
                  ${callMetricCard(t('metric.uncached_input'), number.format(uncachedInputTokens(row)), t('call.exact_label'))}
                  ${callMetricCard(t('call.visible_estimate'), visibleEstimateValue, evidenceStats ? `${number.format(evidenceStats.visibleChars)} analyzed chars · ${evidenceStats.estimator}` : t('call.evidence_label'))}
                  ${callMetricCard(t('call.serialized_upper_bound'), serializedUpperBoundValue, evidenceStats ? `${number.format(evidenceStats.serializedChars)} raw JSON chars · ${evidenceStats.serializedEstimator}${evidenceStats.serializedDeferred ? ` · ${t('call.serialized_quick_hint')}` : ''}` : t('call.evidence_label'))}
                  ${callMetricCard(t('call.hidden_estimate'), hiddenEstimateValue, evidenceStats ? t('call.visible_gap') : t('call.evidence_label'))}
                  ${callMetricCard(t('call.serialized_candidate'), serializedCandidateValue, evidenceStats ? t('call.serialized_candidate_hint') : t('call.evidence_label'))}
                  ${callMetricCard(t('call.remaining_after_serialized'), remainingAfterSerializedValue, evidenceStats ? t('call.remaining_after_serialized_hint') : t('call.evidence_label'))}
                </div>
                ${renderSerializedEvidenceBreakdown(row, evidenceStats)}
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
        restoreContextUiState(row.record_id, article);
        bindContextUiState(row.record_id, article);
        maybeAutoloadEvidence(row, article);
      }
      detailEl.textContent = t('dashboard.detail.empty');
    }

    function captureContextUiState(recordId) {
      const article = rowsEl.querySelector(`.call-investigator[data-record-id="${cssEscape(recordId)}"]`);
      if (!article) return;
      const openEntries = new Set();
      const scrollTops = new Map();
      article.querySelectorAll('.context-entry[data-context-entry-key]').forEach(entry => {
        const key = entry.getAttribute('data-context-entry-key') || '';
        if (!key) return;
        if (entry.tagName.toLowerCase() === 'details' && entry.open) openEntries.add(key);
        const scroller = entry.querySelector('pre');
        if (scroller && scroller.scrollTop > 0) scrollTops.set(key, scroller.scrollTop);
      });
      contextUiState.set(recordId, { openEntries, scrollTops });
    }

    function restoreContextUiState(recordId, root) {
      const saved = contextUiState.get(recordId || '');
      if (!saved) return;
      root.querySelectorAll('.context-entry[data-context-entry-key]').forEach(entry => {
        const key = entry.getAttribute('data-context-entry-key') || '';
        if (!key) return;
        if (entry.tagName.toLowerCase() === 'details' && saved.openEntries.has(key)) {
          entry.open = true;
        }
        const scrollTop = saved.scrollTops.get(key);
        const scroller = entry.querySelector('pre');
        if (scroller && scrollTop) {
          window.requestAnimationFrame(() => {
            scroller.scrollTop = scrollTop;
          });
        }
      });
    }

    function bindContextUiState(recordId, root) {
      if (!recordId) return;
      root.querySelectorAll('.context-entry[data-context-entry-key]').forEach(entry => {
        const key = entry.getAttribute('data-context-entry-key') || '';
        if (!key) return;
        if (entry.tagName.toLowerCase() === 'details') {
          entry.addEventListener('toggle', () => {
            rememberContextEntryOpen(recordId, key, entry.open);
          });
        }
        const scroller = entry.querySelector('pre');
        if (scroller) {
          scroller.addEventListener('scroll', () => {
            rememberContextEntryScroll(recordId, key, scroller.scrollTop);
          }, { passive: true });
        }
      });
    }

    function ensureContextUiState(recordId) {
      const key = recordId || '';
      if (!contextUiState.has(key)) {
        contextUiState.set(key, { openEntries: new Set(), scrollTops: new Map() });
      }
      return contextUiState.get(key);
    }

    function rememberContextEntryOpen(recordId, entryKey, open) {
      const saved = ensureContextUiState(recordId);
      if (open) {
        saved.openEntries.add(entryKey);
      } else {
        saved.openEntries.delete(entryKey);
      }
    }

    function rememberContextEntryScroll(recordId, entryKey, scrollTop) {
      const saved = ensureContextUiState(recordId);
      if (scrollTop > 0) {
        saved.scrollTops.set(entryKey, scrollTop);
      } else {
        saved.scrollTops.delete(entryKey);
      }
    }

    function cssEscape(value) {
      if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value || '');
      return String(value || '').replace(/["\\]/g, '\\$&');
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

    function renderSerializedEvidenceBreakdown(row, stats) {
      if (!stats || !stats.serializedTokens) return '';
      const requestState = contextStateForRow(row);
      const disabled = contextDisabledAttr();
      const fullAnalysisButton = stats.serializedDeferred && requestState.mode !== 'full' && !disabled
        ? `<button class="context-button secondary serialized-action" type="button" data-context-full-analysis>${escapeHtml(t('button.full_serialized_analysis'))}</button>`
        : '';
      if (stats.serializedDeferred) {
        return `
          <div class="serialized-breakdown deferred">
            <div class="serialized-breakdown-heading">
              <strong>${escapeHtml(t('call.serialized_breakdown'))}</strong>
              <span>${escapeHtml(t('call.serialized_deferred'))}</span>
            </div>
            ${fullAnalysisButton}
          </div>
        `;
      }
      const buckets = stats.serializedBuckets.slice(0, 6);
      const bucketHtml = buckets.map(bucket => `
        <div class="serialized-bucket">
          <span>${escapeHtml(bucket.label || bucket.key || t('state.unknown'))}</span>
          <strong>${number.format(Number(bucket.token_estimate || 0))}</strong>
          <small>${escapeHtml(tf('call.serialized_bucket_detail', { count: number.format(Number(bucket.count || 0)), chars: number.format(Number(bucket.char_count || 0)) }))}</small>
          ${bucket.note ? `<small>${escapeHtml(bucket.note)}</small>` : ''}
        </div>
      `).join('');
      return `
        <div class="serialized-breakdown">
          <div class="serialized-breakdown-heading">
            <strong>${escapeHtml(t('call.serialized_breakdown'))}</strong>
            <span>${escapeHtml(t('call.serialized_bound_hint'))}</span>
          </div>
          <div class="serialized-bucket-grid">
            ${bucketHtml || `<p class="muted">${escapeHtml(t('state.no_data'))}</p>`}
          </div>
        </div>
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
      root.querySelectorAll('[data-context-full-analysis]').forEach(button => {
        button.addEventListener('click', () => {
          loadContext(row, { mode: 'full' }, contextResult);
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
        mode: 'quick',
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
      next.mode = next.mode === 'full' ? 'full' : 'quick';
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
      captureContextUiState(row.record_id);
      contextPayloadState.set(row.record_id, { status: 'loading' });
      target.innerHTML = `<p class="context-note">${escapeHtml(t('context.loading'))}</p>`;
      const requestState = nextContextState(row, options);
      const params = new URLSearchParams({ record_id: row.record_id });
      params.set('mode', requestState.mode || 'quick');
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
        restoreContextUiState(row.record_id, target);
        bindContextUiState(row.record_id, target);
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

    function formatTimingValue(milliseconds) {
      const value = Number(milliseconds);
      if (!Number.isFinite(value) || value < 0) return '';
      return formatDuration(value / 1000, '');
    }

    function renderContextTimingMeta(entry) {
      const timing = entry?.action_timing || {};
      if (!timing || typeof timing !== 'object') return '';
      const chips = [];
      const sinceStart = formatTimingValue(timing.since_turn_start_ms);
      const sincePrevious = formatTimingValue(timing.since_previous_entry_ms);
      const reportedDuration = formatTimingValue(timing.reported_duration_ms);
      if (sinceStart) {
        chips.push(`<span class="context-entry-timing" title="Elapsed from selected turn start">T+${escapeHtml(sinceStart)}</span>`);
      }
      if (sincePrevious) {
        chips.push(`<span class="context-entry-timing" title="Gap since previous evidence entry">+${escapeHtml(sincePrevious)}</span>`);
      }
      if (reportedDuration) {
        chips.push(`<span class="context-entry-timing duration" title="Duration reported by this event">${escapeHtml(t('table.duration'))} ${escapeHtml(reportedDuration)}</span>`);
      }
      return chips.join('');
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
        const entryKey = contextEntryKey(entry, index);
        const metaParts = [
          formatTimestamp(entry.timestamp, ''),
          entry.line_number ? tf('context.line', { line: entry.line_number }) : '',
        ].filter(Boolean);
        const timingMeta = renderContextTimingMeta(entry);
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
              ${metaParts.length ? `<span>${escapeHtml(metaParts.join(' - '))}</span>` : ''}
              ${timingMeta}
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
            <details class="context-entry context-entry-collapsed" data-context-entry-key="${escapeHtml(entryKey)}">
              <summary class="context-entry-summary">
                <span class="context-entry-title">${escapeHtml(entry.label || entry.type || 'entry')}</span>
                <span class="context-entry-meta">
                  ${metaParts.length ? `<span>${escapeHtml(metaParts.join(' - '))}</span>` : ''}
                  ${timingMeta}
                </span>
              </summary>
              ${bodyHtml}
            </details>
          `;
        }
        return `
          <div class="context-entry context-entry-current" data-context-entry-key="${escapeHtml(entryKey)}">
            ${header}
            ${bodyHtml}
          </div>
        `;
      }).join('');
      return `<p class="context-note">${escapeHtml(note)}</p>${contextLimitActions(payload)}${body || `<p class="context-note">${escapeHtml(t('state.no_context_entries'))}</p>`}`;
    }

    function contextEntryKey(entry, index) {
      const line = entry.line_number || '';
      const type = entry.type || '';
      const label = entry.label || '';
      return `${line || `index-${index}`}:${type}:${label}`;
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
