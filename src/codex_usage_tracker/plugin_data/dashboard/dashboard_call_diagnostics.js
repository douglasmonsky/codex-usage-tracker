(() => {
  function createCallDiagnostics(deps) {
    const {
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
    } = deps;

    function callMetricCard(label, value, badge = '', title = '') {
      const cardTooltip = title || `${label}: ${value}${badge ? ` - ${badge}` : ''}`;
      return `
        <div class="call-metric-card" ${tooltipAttributes(cardTooltip)}>
          <span ${tooltipAttributes(label)}>${escapeHtml(label)}</span>
          <strong ${tooltipAttributes(value)}>${escapeHtml(value)}</strong>
          ${badge ? `<small ${tooltipAttributes(badge)}>${escapeHtml(badge)}</small>` : ''}
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

    function renderInvestigationReadout(
      row,
      previous,
      diagnostic,
      callPosition,
      stats,
    ) {
      const exact = `${number.format(rowInputTokens(row))} input tokens = ${number.format(cachedInputTokens(row))} cached + ${number.format(uncachedInputTokens(row))} uncached; ${number.format(outputTokens(row))} output tokens; ${pct(row.cache_ratio)} cache reuse.`;
      const derived = previous
        ? deltaInterpretation(row, previous)
        : 'No previous call is loaded for this resolved thread, so call-to-call deltas are unavailable.';
      const evidence = stats
        ? `Evidence analyzed: ${number.format(stats.totalEntries)} selected-turn entries, ${number.format(stats.visibleChars)} visible redacted chars, ${number.format(stats.visibleTokenEstimate)} visible tokens via ${stats.estimator}. ${stats.serializedDeferred ? 'Fast serialized estimate only; full serialized grouping is deferred.' : `Serialized local upper bound: ${number.format(stats.serializedTokens)} tokens from ${number.format(stats.serializedChars)} raw JSON chars.`} ${number.format(stats.entries)} entries rendered initially.`
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

    return {
      callMetricCard,
      renderCacheVerdict,
      renderDeltaCards,
      renderInvestigationReadout,
    };
  }

  window.CodexUsageCallDiagnostics = Object.freeze({ create: createCallDiagnostics });
})();
