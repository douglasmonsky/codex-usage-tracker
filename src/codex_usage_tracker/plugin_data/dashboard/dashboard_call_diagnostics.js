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
        return tf('call.delta.cache_drop', {
          uncached: number.format(uncached),
          cached: number.format(Math.abs(cached)),
        });
      }
      if (uncached > 0) {
        return tf('call.delta.uncached_increase', { uncached: number.format(uncached) });
      }
      if (uncached < 0 && cached >= 0) {
        return tf('call.delta.uncached_decrease_cached_increase', {
          uncached: number.format(Math.abs(uncached)),
        });
      }
      return t('call.delta.stable');
    }

    function diagnosticNextStep(row, diagnostic, previous) {
      if (diagnostic.key === 'post-compaction') {
        return t('call.next_step.post_compaction');
      }
      if (diagnostic.key === 'cold') {
        return t('call.next_step.cold');
      }
      if (diagnostic.key === 'spike') {
        return t('call.next_step.spike');
      }
      if (diagnostic.key === 'warm') {
        return tf('call.next_step.warm', { uncached: number.format(uncachedInputTokens(row)) });
      }
      if (previous) return t('call.next_step.delta');
      return t('call.next_step.isolated');
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
      const exact = tf('call.readout.exact_body', {
        input: number.format(rowInputTokens(row)),
        cached: number.format(cachedInputTokens(row)),
        uncached: number.format(uncachedInputTokens(row)),
        output: number.format(outputTokens(row)),
        cache: pct(row.cache_ratio),
      });
      const derived = previous
        ? deltaInterpretation(row, previous)
        : t('call.readout.previous_unavailable');
      const serializedDetail = stats
        ? (
          stats.serializedDeferred
            ? t('call.readout.evidence_serialized_deferred')
            : tf('call.readout.evidence_serialized_bound', {
              tokens: number.format(stats.serializedTokens),
              chars: number.format(stats.serializedChars),
            })
        )
        : '';
      const evidence = stats
        ? tf('call.readout.evidence_analyzed', {
          totalEntries: number.format(stats.totalEntries),
          visibleChars: number.format(stats.visibleChars),
          visibleTokens: number.format(stats.visibleTokenEstimate),
          estimator: stats.estimator,
          serializedDetail,
          renderedEntries: number.format(stats.entries),
        })
        : t('call.readout.evidence_loading');
      return `
        <section class="call-diagnostic-section readout">
          <div class="section-heading compact">
            <h3>${escapeHtml(t('call.readout.title'))}</h3>
            <span class="evidence-chip exact">${escapeHtml(t('call.readout.badge'))}</span>
          </div>
          <div class="readout-grid">
            <div class="readout-card">
              <span>${escapeHtml(t('call.readout.exact_label'))}</span>
              <p>${escapeHtml(exact)}</p>
            </div>
            <div class="readout-card">
              <span>${escapeHtml(t('call.readout.previous_label'))}</span>
              <p>${escapeHtml(derived)}</p>
            </div>
            <div class="readout-card">
              <span>${escapeHtml(t('call.readout.evidence_label'))}</span>
              <p>${escapeHtml(evidence)}</p>
            </div>
            <div class="readout-card">
              <span>${escapeHtml(t('call.readout.next_label'))}</span>
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
