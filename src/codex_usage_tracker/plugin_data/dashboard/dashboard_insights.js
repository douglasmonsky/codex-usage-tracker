(() => {
  function create(deps) {
    const {
      allowanceWindowText,
      applyPreset,
      clearPresetEl,
      clamp,
      creditCoverageRatio,
      credits,
      escapeHtml,
      groupThreads,
      insightCardsEl,
      insightsPanelEl,
      moneyText,
      number,
      onInsightActivated,
      pct,
      presetListEl,
      presetStatusEl,
      pricingConfigured,
      rowAttentionScore,
      rowThreadLabel,
      severityForScore,
      sumUsageCredits,
      t,
      tf,
      threshold,
      usageCreditValue,
    } = deps;

    const presetDefinitions = [
      {
        key: 'highest-cost',
        labelKey: 'preset.highest_cost_threads',
        descriptionKey: 'preset.highest_cost_threads_desc',
        view: 'threads',
        sort: 'cost',
        direction: 'desc',
        captionKey: 'preset.highest_cost_threads_caption',
        matches: () => true,
      },
      {
        key: 'context-bloat',
        labelKey: 'preset.context_bloat',
        descriptionKey: 'preset.context_bloat_desc',
        view: 'calls',
        sort: 'context',
        direction: 'desc',
        captionKey: 'preset.context_bloat_caption',
        matches: row => Number(row.context_window_percent || 0) >= threshold('high_context_percent', 0.6) || Number(row.cumulative_total_tokens || 0) >= threshold('large_cumulative_tokens', 200000),
      },
      {
        key: 'cache-misses',
        labelKey: 'preset.cache_misses',
        descriptionKey: 'preset.cache_misses_desc',
        view: 'calls',
        sort: 'cache',
        direction: 'asc',
        captionKey: 'preset.cache_misses_caption',
        matches: row => Number(row.input_tokens || 0) > 0 && Number(row.cache_ratio || 0) < threshold('low_cache_ratio', 0.3),
      },
      {
        key: 'pricing-gaps',
        labelKey: 'preset.pricing_gaps',
        descriptionKey: 'preset.pricing_gaps_desc',
        view: 'calls',
        sort: 'total',
        direction: 'desc',
        pricingStatus: 'unpriced',
        captionKey: 'preset.pricing_gaps_caption',
        matches: row => !row.pricing_model,
      },
      {
        key: 'estimated-review',
        labelKey: 'preset.estimated_price_review',
        descriptionKey: 'preset.estimated_price_review_desc',
        view: 'calls',
        sort: 'cost',
        direction: 'desc',
        pricingStatus: 'estimated',
        captionKey: 'preset.estimated_price_review_caption',
        matches: row => Boolean(row.pricing_estimated),
      },
      {
        key: 'usage-credits',
        labelKey: 'preset.highest_codex_credits',
        descriptionKey: 'preset.highest_codex_credits_desc',
        view: 'calls',
        sort: 'usage',
        direction: 'desc',
        captionKey: 'preset.highest_codex_credits_caption',
        matches: row => Number(row.usage_credits || 0) > 0,
      },
    ];

    function activePresetDefinition(activePreset) {
      return presetDefinitions.find(preset => preset.key === activePreset) || null;
    }

    function hasPreset(key) {
      return presetDefinitions.some(preset => preset.key === key);
    }

    function presetMatchesRow(row, activePreset) {
      const preset = activePresetDefinition(activePreset);
      return preset ? preset.matches(row) : true;
    }

    function buildInsights(rows) {
      const groups = groupThreads(rows);
      const insights = [];
      const topCostGroup = groups.filter(group => group.estimatedCost > 0).sort((a, b) => b.estimatedCost - a.estimatedCost || b.attentionScore - a.attentionScore)[0];
      if (topCostGroup) {
        insights.push({
          title: t('insight.costliest_thread'),
          value: pricingConfigured() ? moneyText(topCostGroup.estimatedCost) : t('state.not_configured'),
          body: tf('insight.costliest_thread_body', { thread: topCostGroup.label, calls: number.format(topCostGroup.callCount), tokens: number.format(topCostGroup.totalTokens) }),
          severity: severityForScore(topCostGroup.attentionScore),
          action: t('insight.open_thread_timeline'),
          preset: 'highest-cost',
          target: { threadKey: topCostGroup.key, expandThread: true },
        });
      }
      const lowCacheLimit = threshold('low_cache_ratio', 0.3);
      const lowCacheRows = rows.filter(row => Number(row.input_tokens || 0) > 0 && Number(row.cache_ratio || 0) < lowCacheLimit);
      if (lowCacheRows.length) {
        const lowest = lowCacheRows.slice().sort((a, b) => Number(a.cache_ratio || 0) - Number(b.cache_ratio || 0))[0];
        insights.push({
          title: t('insight.low_cache_reuse'),
          value: pct(lowest.cache_ratio),
          body: tf('insight.low_cache_reuse_body', { calls: number.format(lowCacheRows.length), ratio: pct(lowCacheLimit), thread: rowThreadLabel(lowest) }),
          severity: 'medium',
          action: t('insight.apply_cache_misses'),
          preset: 'cache-misses',
          target: { recordId: lowest.record_id },
        });
      }
      const highContextLimit = threshold('high_context_percent', 0.6);
      const highContextRows = rows.filter(row => Number(row.context_window_percent || 0) >= highContextLimit);
      if (highContextRows.length) {
        const highest = highContextRows.slice().sort((a, b) => Number(b.context_window_percent || 0) - Number(a.context_window_percent || 0))[0];
        insights.push({
          title: t('insight.context_bloat'),
          value: pct(highest.context_window_percent),
          body: tf('insight.context_bloat_body', { calls: number.format(highContextRows.length), ratio: pct(highContextLimit) }),
          severity: severityForScore(rowAttentionScore(highest)),
          action: t('insight.apply_context_bloat'),
          preset: 'context-bloat',
          target: { recordId: highest.record_id },
        });
      }
      const usageCredits = sumUsageCredits(rows);
      if (usageCredits > 0) {
        const creditCoverage = creditCoverageRatio(rows);
        const highestUsageRow = rows.filter(row => usageCreditValue(row) !== null).sort((a, b) => Number(usageCreditValue(b) || 0) - Number(usageCreditValue(a) || 0))[0];
        insights.push({
          title: t('insight.codex_allowance_usage'),
          value: `${credits(usageCredits)} ${t('badge.credits')}`,
          body: allowanceWindowText(usageCredits, 'impact') || allowanceWindowText(usageCredits, 'remaining') || tf('insight.credit_coverage_body', { ratio: pct(creditCoverage) }),
          severity: severityForScore(clamp(usageCredits * 2.4, 0, 140)),
          action: t('insight.review_highest_credit'),
          preset: 'usage-credits',
          target: highestUsageRow ? { recordId: highestUsageRow.record_id } : null,
        });
      }
      const unpricedTokens = rows.reduce((sum, row) => sum + (!row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      if (unpricedTokens) {
        const topUnpricedRow = rows.filter(row => !row.pricing_model).sort((a, b) => Number(b.total_tokens || 0) - Number(a.total_tokens || 0))[0];
        insights.push({
          title: t('insight.unpriced_usage'),
          value: number.format(unpricedTokens),
          body: t('insight.unpriced_usage_body'),
          severity: 'review',
          action: t('insight.review_pricing_gaps'),
          preset: 'pricing-gaps',
          target: topUnpricedRow ? { recordId: topUnpricedRow.record_id } : null,
        });
      }
      const estimatedTokens = rows.reduce((sum, row) => sum + (row.pricing_estimated ? Number(row.total_tokens || 0) : 0), 0);
      if (estimatedTokens) {
        const topEstimatedRow = rows.filter(row => row.pricing_estimated).sort((a, b) => Number(b.total_tokens || 0) - Number(a.total_tokens || 0))[0];
        insights.push({
          title: t('insight.estimated_pricing'),
          value: number.format(estimatedTokens),
          body: t('insight.estimated_pricing_body'),
          severity: 'review',
          action: t('insight.review_estimates'),
          preset: 'estimated-review',
          target: topEstimatedRow ? { recordId: topEstimatedRow.record_id } : null,
        });
      }
      const reasoningRows = rows.filter(row => Number(row.reasoning_output_tokens || 0) > 0).sort((a, b) => Number(b.reasoning_output_tokens || 0) - Number(a.reasoning_output_tokens || 0));
      if (reasoningRows[0]) {
        insights.push({
          title: t('insight.reasoning_output_spike'),
          value: number.format(reasoningRows[0].reasoning_output_tokens || 0),
          body: tf('insight.reasoning_spike_body', { thread: rowThreadLabel(reasoningRows[0]) }),
          severity: severityForScore(rowAttentionScore(reasoningRows[0])),
          action: t('insight.inspect_selected_call'),
          view: 'calls',
          sort: 'reasoning',
          target: { recordId: reasoningRows[0].record_id },
        });
      }
      return insights.slice(0, 6);
    }

    function renderPresetControls(activePreset) {
      const preset = activePresetDefinition(activePreset);
      clearPresetEl.hidden = !preset;
      presetStatusEl.textContent = preset
        ? tf('preset.caption', { caption: t(preset.captionKey), description: t(preset.descriptionKey) })
        : t('preset.no_preset');
      presetListEl.innerHTML = presetDefinitions.map(candidate => `
        <button class="preset-card" type="button" data-preset="${escapeHtml(candidate.key)}" aria-pressed="${candidate.key === activePreset ? 'true' : 'false'}">
          <span class="preset-copy"><b>${escapeHtml(t(candidate.labelKey))}</b><span>${escapeHtml(t(candidate.descriptionKey))}</span></span>
          <span class="preset-chip">${escapeHtml(t('action.run'))}</span>
        </button>
      `).join('');
      presetListEl.querySelectorAll('[data-preset]').forEach(button => {
        button.addEventListener('click', () => applyPreset(button.dataset.preset));
      });
    }

    function renderInsightPanel(rows, activeView, activePreset) {
      if (activeView === 'call') {
        insightsPanelEl.hidden = true;
        return;
      }
      if (activeView !== 'insights' && !activePreset) {
        insightsPanelEl.hidden = true;
        return;
      }
      insightsPanelEl.hidden = false;
      renderPresetControls(activePreset);
      const insights = buildInsights(rows);
      if (!insights.length) {
        insightCardsEl.innerHTML = `<div class="empty-state">${escapeHtml(t('state.no_data'))}</div>`;
        return;
      }
      insightCardsEl.innerHTML = insights.map((insight, index) => {
        const severity = insight.severity || 'review';
        return `
          <article class="insight-card" data-severity="${escapeHtml(severity)}">
            <div class="insight-card-header">
              <h3>${escapeHtml(insight.title)}</h3>
              <span class="severity-chip ${escapeHtml(severity)}">${escapeHtml(severity === 'high' ? t('severity.high') : severity === 'medium' ? t('severity.medium') : t('severity.review'))}</span>
            </div>
            <strong>${escapeHtml(insight.value)}</strong>
            <p>${escapeHtml(insight.body)}</p>
            <button class="insight-action" type="button" data-insight-index="${index}">${escapeHtml(insight.action)}</button>
          </article>
        `;
      }).join('');
      insightCardsEl.querySelectorAll('[data-insight-index]').forEach(button => {
        const insight = insights[Number(button.dataset.insightIndex)];
        button.addEventListener('click', () => {
          if (insight.preset) {
            applyPreset(insight.preset, insight.target);
            return;
          }
          onInsightActivated(insight);
        });
      });
    }

    return {
      activePresetDefinition,
      hasPreset,
      presetDefinitions,
      presetMatchesRow,
      renderInsightPanel,
      renderPresetControls,
    };
  }

  window.CodexUsageDashboardInsights = { create };
})();
