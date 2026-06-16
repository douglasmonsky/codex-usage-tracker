(function () {
  function create(deps) {
    const {
      cachedInputTokens,
      callInitiatorText,
      chronological,
      clamp,
      compareValues,
      effortTooltipText,
      isAutoReview,
      isSubagent,
      outputTokens,
      resolvedParentThreadName,
      rowAttachment,
      rowThreadLabel,
      sumUsageCredits,
      t,
      textValue,
      tf,
      topRecommendation,
      translateEffort,
      uncachedInputTokens,
      usageCreditValue,
    } = deps;

    function signalCount(row) {
      return Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0;
    }

    function usageImpactWindow(row, key = 'secondary') {
      const impact = row && row.usage_impact && typeof row.usage_impact === 'object'
        ? row.usage_impact[key]
        : null;
      return impact && typeof impact === 'object' ? impact : null;
    }

    function usageImpactValue(row, key = 'secondary') {
      const window = usageImpactWindow(row, key);
      return window ? Number(window.estimate_percent || 0) : 0;
    }

    function aggregateUsageImpact(rows) {
      return {
        primary: aggregateUsageImpactWindow(rows, 'primary'),
        secondary: aggregateUsageImpactWindow(rows, 'secondary'),
      };
    }

    function aggregateUsageImpactWindow(rows, key) {
      const windows = rows.map(row => usageImpactWindow(row, key)).filter(Boolean);
      if (!windows.length) return null;
      const first = windows[0];
      const bases = [...new Set(windows.map(window => window.basis).filter(Boolean))];
      return {
        schema: 'codex-usage-tracker-usage-impact-estimate-v1',
        label: first.label,
        window_minutes: first.window_minutes,
        estimate_percent: windows.reduce((sum, window) => sum + Number(window.estimate_percent || 0), 0),
        lower_percent: windows.reduce((sum, window) => sum + Number(window.lower_percent || 0), 0),
        upper_percent: windows.reduce((sum, window) => sum + Number(window.upper_percent || 0), 0),
        observed_delta_percent: windows.reduce((sum, window) => sum + Number(window.observed_delta_percent || 0), 0),
        interval_call_count: rows.length,
        basis: bases.length === 1 ? bases[0] : 'mixed',
        resets_at: first.resets_at,
      };
    }

    function rowAttentionScore(row) {
      const costScore = clamp(Number(row.estimated_cost_usd || 0) * 24, 0, 60);
      const tokenScore = clamp(Number(row.total_tokens || 0) / 2500, 0, 36);
      const lowCacheScore = Number(row.input_tokens || 0) > 0 ? clamp((0.5 - Number(row.cache_ratio || 0)) * 70, 0, 35) : 0;
      const contextScore = clamp(Number(row.context_window_percent || 0) * 42, 0, 42);
      const pricingScore = row.pricing_model ? (row.pricing_estimated ? 12 : 0) : 30;
      const usageScore = clamp(Number(row.usage_credits || 0) * 2.5, 0, 48);
      return costScore + usageScore + tokenScore + lowCacheScore + contextScore + pricingScore + signalCount(row) * 12;
    }

    function threadAttentionScore(group) {
      const costScore = clamp(Number(group.estimatedCost || 0) * 24, 0, 72);
      const tokenScore = clamp(Number(group.totalTokens || 0) / 3500, 0, 42);
      const lowCacheScore = clamp((0.55 - Number(group.cacheRatio || 0)) * 70, 0, 38);
      const contextScore = clamp(Number(group.maxContextUse || 0) * 45, 0, 45);
      const pricingScore = group.pricingStatusCode === 'no_price' ? 36 : group.pricingStatusCode === 'estimated' || group.pricingStatusCode === 'mixed' ? 18 : 0;
      const usageScore = clamp(Number(group.usageCredits || 0) * 2.4, 0, 72);
      const relationScore = (group.subagentCount || 0) * 4 + (group.autoReviewCount || 0) * 6 + (group.attachedCount || 0) * 3;
      return costScore + usageScore + tokenScore + lowCacheScore + contextScore + pricingScore + relationScore + Number(group.signalCount || 0) * 10;
    }

    function severityForScore(score, hasPricingGap = false) {
      if (score >= 95) return 'high';
      if (score >= 48) return 'medium';
      return hasPricingGap ? 'review' : 'review';
    }

    function directional(compareResult, sortDirection) {
      return sortDirection === 'asc' ? compareResult : -compareResult;
    }

    function callSortValue(row, key) {
      if (key === 'attention') return rowAttentionScore(row);
      if (key === 'cache') return Number(row.cache_ratio || 0);
      if (key === 'context') return Number(row.context_window_percent || 0);
      if (key === 'cost') return Number(row.estimated_cost_usd || 0);
      if (key === 'effort') return textValue(row.effort);
      if (key === 'initiator') return textValue(callInitiatorText(row));
      if (key === 'model') return textValue(row.model);
      if (key === 'cached') return cachedInputTokens(row);
      if (key === 'uncached') return uncachedInputTokens(row);
      if (key === 'output') return outputTokens(row);
      if (key === 'reasoning') return Number(row.reasoning_output_tokens || 0);
      if (key === 'signals') return signalCount(row);
      if (key === 'thread') return textValue(rowThreadLabel(row));
      if (key === 'time') return String(row.event_timestamp || '');
      if (key === 'usage_impact') return usageImpactValue(row, 'secondary');
      if (key === 'usage') return Number(row.usage_credits || 0);
      return Number(row.total_tokens || 0);
    }

    function compareCalls(a, b, sortKey, sortDirection) {
      const primary = directional(compareValues(callSortValue(a, sortKey), callSortValue(b, sortKey)), sortDirection);
      if (primary !== 0) return primary;
      const timeFallback = String(b.event_timestamp || '').localeCompare(String(a.event_timestamp || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.record_id || '').localeCompare(String(b.record_id || ''));
    }

    function threadCallSortValue(row, key) {
      if (key === 'cache') return Number(row.cache_ratio || 0);
      if (key === 'cost') return Number(row.estimated_cost_usd || 0);
      if (key === 'effort') return textValue(row.effort);
      if (key === 'initiator') return textValue(callInitiatorText(row));
      if (key === 'model') return textValue(row.model);
      if (key === 'cached') return cachedInputTokens(row);
      if (key === 'uncached') return uncachedInputTokens(row);
      if (key === 'output') return outputTokens(row);
      if (key === 'reasoning') return Number(row.reasoning_output_tokens || 0);
      if (key === 'signals') return signalCount(row);
      if (key === 'source') return textValue(callInitiatorText(row));
      if (key === 'time') return String(row.event_timestamp || '');
      if (key === 'usage_impact') return usageImpactValue(row, 'secondary');
      return Number(row.total_tokens || 0);
    }

    function compareThreadCalls(a, b, sortKey, sortDirection) {
      const comparison = compareValues(
        threadCallSortValue(a, sortKey),
        threadCallSortValue(b, sortKey),
      );
      const primary = sortDirection === 'asc' ? comparison : -comparison;
      if (primary !== 0) return primary;
      const timeFallback = String(b.event_timestamp || '').localeCompare(String(a.event_timestamp || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.record_id || '').localeCompare(String(b.record_id || ''));
    }

    function sortedThreadCalls(calls, sortKey, sortDirection) {
      return calls.slice().sort((a, b) => compareThreadCalls(a, b, sortKey, sortDirection));
    }

    function threadSortValue(group, key) {
      if (key === 'attention') return group.attentionScore;
      if (key === 'cache') return group.cacheRatio;
      if (key === 'context') return group.maxContextUse;
      if (key === 'cost') return group.estimatedCost;
      if (key === 'effort') return textValue(group.effortSummary);
      if (key === 'model') return textValue(group.modelSummary);
      if (key === 'cached') return group.cachedTokens;
      if (key === 'uncached') return group.uncachedTokens;
      if (key === 'output') return group.outputTokens;
      if (key === 'reasoning') return group.reasoningOutputTokens;
      if (key === 'signals') return group.signalCount;
      if (key === 'thread') return textValue(group.label);
      if (key === 'time') return String(group.latestActivity || '');
      if (key === 'usage_impact') return usageImpactValue(group, 'secondary');
      if (key === 'usage') return group.usageCredits;
      return group.totalTokens;
    }

    function compareThreads(a, b, sortKey, sortDirection) {
      const primary = directional(compareValues(threadSortValue(a, sortKey), threadSortValue(b, sortKey)), sortDirection);
      if (primary !== 0) return primary;
      const timeFallback = String(b.latestActivity || '').localeCompare(String(a.latestActivity || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.label || '').localeCompare(String(b.label || ''));
    }

    function sortThreads(groups, sortKey, sortDirection) {
      groups.sort((a, b) => compareThreads(a, b, sortKey, sortDirection));
      return groups;
    }

    function relationshipTime(group) {
      return String(group.relationshipLatestActivity || group.latestActivity || '');
    }

    function compareTopLevelThreads(a, b, sortKey, sortDirection) {
      if (sortKey === 'time' && sortDirection === 'desc') {
        const relationshipCompare = relationshipTime(b).localeCompare(relationshipTime(a));
        if (relationshipCompare !== 0) return relationshipCompare;
      }
      return compareThreads(a, b, sortKey, sortDirection);
    }

    function compactSummaryText(values, fallbackKey) {
      const unique = [...new Set(values.filter(Boolean))].sort();
      if (!unique.length) return t('state.unknown');
      if (unique.length === 1) return fallbackKey === 'table.more_efforts' ? translateEffort(unique[0]) : unique[0];
      return tf(fallbackKey, {
        model: unique[0],
        effort: fallbackKey === 'table.more_efforts' ? translateEffort(unique[0]) : unique[0],
        count: unique.length - 1,
      });
    }

    function threadModelSummaryText(calls) {
      const models = [...new Set(calls.map(row => row.model).filter(Boolean))].sort();
      if (!models.length) return t('state.unknown');
      if (models.length === 1) return models[0];
      const nonReviewModels = models.filter(model => model !== 'codex-auto-review');
      const primary = nonReviewModels.length ? nonReviewModels[0] : models[0];
      return tf('table.more_models', { model: primary, count: models.length - 1 });
    }

    function dominantParentThread(calls, ownLabel) {
      const counts = new Map();
      for (const row of calls) {
        const parent = resolvedParentThreadName(row);
        if (!parent || parent === ownLabel) continue;
        counts.set(parent, (counts.get(parent) || 0) + 1);
      }
      const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      return ranked.length ? ranked[0][0] : '';
    }

    function arrangeThreadGroups(groups, sortKey, sortDirection) {
      const byLabel = new Map(groups.map(group => [group.label, group]));
      for (const group of groups) {
        group.childThreadCount = 0;
        group.childCallCount = 0;
        group.relationshipLatestActivity = group.latestActivity;
        group.parentVisible = Boolean(group.parentThreadLabel && byLabel.has(group.parentThreadLabel));
        group.renderAsChild = false;
      }
      for (const group of groups) {
        if (!group.parentVisible) continue;
        const parent = byLabel.get(group.parentThreadLabel);
        parent.childThreadCount += 1;
        parent.childCallCount += group.callCount;
        if (String(group.latestActivity || '') > String(parent.relationshipLatestActivity || '')) {
          parent.relationshipLatestActivity = group.latestActivity;
        }
      }
      if (sortKey !== 'time' || sortDirection !== 'desc') {
        return sortThreads(groups, sortKey, sortDirection);
      }
      const childrenByParent = new Map();
      for (const group of groups) {
        if (!group.parentVisible) continue;
        if (!childrenByParent.has(group.parentThreadLabel)) childrenByParent.set(group.parentThreadLabel, []);
        childrenByParent.get(group.parentThreadLabel).push(group);
      }
      const display = [];
      const topLevel = groups.filter(group => !group.parentVisible).sort((a, b) => compareTopLevelThreads(a, b, sortKey, sortDirection));
      const displayed = new Set();
      function appendGroup(group, renderAsChild = false) {
        if (displayed.has(group.key)) return;
        displayed.add(group.key);
        group.renderAsChild = renderAsChild;
        display.push(group);
        const children = (childrenByParent.get(group.label) || []).sort((a, b) => compareThreads(a, b, sortKey, sortDirection));
        for (const child of children) appendGroup(child, true);
      }
      for (const group of topLevel) {
        appendGroup(group, false);
      }
      return display;
    }

    function pricingStatusCodeFor(rows) {
      const priced = rows.filter(row => row.pricing_model);
      const estimated = rows.filter(row => row.pricing_estimated);
      if (priced.length === 0) return 'no_price';
      if (estimated.length === rows.length) return 'estimated';
      if (estimated.length > 0 || priced.length < rows.length) return 'mixed';
      return 'configured';
    }

    function pricingStatusFor(rows) {
      return {
        no_price: t('state.no_price'),
        estimated: t('state.estimated'),
        mixed: t('state.mixed'),
        configured: t('state.configured'),
      }[pricingStatusCodeFor(rows)];
    }

    function creditStatusFor(rows) {
      const rated = rows.filter(row => usageCreditValue(row) !== null);
      const estimated = rows.filter(row => row.usage_credit_confidence === 'estimated');
      if (rated.length === 0) return t('credit.no_mapped_rate');
      if (estimated.length === rows.length) return t('credit.estimated_mapping');
      if (estimated.length > 0 || rated.length < rows.length) return t('state.mixed');
      return t('credit.official_match');
    }

    function threadLifecycle(calls, highCost, highContext) {
      let largestJump = 0;
      let largestJumpRow = null;
      for (let index = 1; index < calls.length; index += 1) {
        const previous = Number(calls[index - 1].cumulative_total_tokens || 0);
        const current = Number(calls[index].cumulative_total_tokens || 0);
        const jump = Math.max(current - previous, Number(calls[index].total_tokens || 0), 0);
        if (jump > largestJump) {
          largestJump = jump;
          largestJumpRow = calls[index];
        }
      }
      const firstExpensiveIndex = calls.findIndex(row => Number(row.estimated_cost_usd || 0) >= highCost || Number(row.context_window_percent || 0) >= highContext);
      const firstExpensiveRow = firstExpensiveIndex >= 0 ? calls[firstExpensiveIndex] : null;
      const first = calls[0] || {};
      const last = calls[calls.length - 1] || {};
      const cacheTrend = Number(last.cache_ratio || 0) - Number(first.cache_ratio || 0);
      const contextTrend = Number(last.context_window_percent || 0) - Number(first.context_window_percent || 0);
      const spikeIndex = largestJumpRow ? calls.indexOf(largestJumpRow) : -1;
      const subagentBeforeSpike = spikeIndex > 0 && calls.slice(0, spikeIndex).some(row => isSubagent(row) || isAutoReview(row));
      const topAction = calls.map(topRecommendation).filter(Boolean)[0];
      let action = topAction
        ? topAction.action
        : t('action.expand_or_select_recommendations');
      if (contextTrend >= 0.15 || Number(last.context_window_percent || 0) >= highContext) {
        action = t('action.review_context_growth');
      } else if (cacheTrend <= -0.25) {
        action = t('action.check_cache_drop');
      } else if (subagentBeforeSpike) {
        action = t('action.compare_subagent_calls');
      }
      return {
        firstExpensiveRow,
        firstExpensiveIndex,
        largestJump,
        largestJumpRow,
        cacheTrend,
        contextTrend,
        subagentBeforeSpike,
        action,
      };
    }

    function groupThreads(rows, sortKey, sortDirection, thresholds) {
      const highCost = thresholds.highCost;
      const highContext = thresholds.highContext;
      const map = new Map();
      for (const row of rows) {
        const attachment = rowAttachment(row);
        const key = attachment.key;
        if (!map.has(key)) {
          map.set(key, { key, label: attachment.label, rows: [] });
        }
        map.get(key).rows.push(row);
      }
      const groups = [...map.values()].map(group => {
        const calls = group.rows.slice().sort(chronological);
        const totalTokens = calls.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
        const inputTokens = calls.reduce((sum, row) => sum + Number(row.input_tokens || 0), 0);
        const cachedTokens = calls.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0);
        const uncachedTokens = calls.reduce((sum, row) => sum + uncachedInputTokens(row), 0);
        const outputTokensTotal = calls.reduce((sum, row) => sum + outputTokens(row), 0);
        const reasoningOutputTokens = calls.reduce((sum, row) => sum + Number(row.reasoning_output_tokens || 0), 0);
        const estimatedCost = calls.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
        const usageCredits = sumUsageCredits(calls);
        const usageImpact = aggregateUsageImpact(calls);
        const signalTotal = calls.reduce((sum, row) => sum + signalCount(row), 0);
        const latestActivity = calls.reduce((latest, row) => String(row.event_timestamp || '') > latest ? String(row.event_timestamp || '') : latest, '');
        const maxContextUse = calls.reduce((max, row) => Math.max(max, Number(row.context_window_percent || 0)), 0);
        const subagentCount = calls.filter(isSubagent).length;
        const autoReviewCount = calls.filter(isAutoReview).length;
        const attachedCount = calls.filter(row => rowAttachment(row).relation !== 'direct' && rowAttachment(row).relation !== 'session').length;
        const modelSummary = threadModelSummaryText(calls);
        const effortSummary = compactSummaryText(calls.map(row => row.effort), 'table.more_efforts');
        const effortTooltip = effortTooltipText(calls.map(row => row.effort));
        const parentThreadLabel = dominantParentThread(calls, group.label);
        const lifecycle = threadLifecycle(calls, highCost, highContext);
        return {
          key: group.key,
          label: group.label,
          calls,
          callCount: calls.length,
          latestActivity,
          parentThreadLabel,
          modelSummary,
          effortSummary,
          effortTooltip,
          totalTokens,
          cachedTokens,
          uncachedTokens,
          outputTokens: outputTokensTotal,
          reasoningOutputTokens,
          estimatedCost,
          usageCredits,
          usage_impact: usageImpact,
          cacheRatio: inputTokens ? cachedTokens / inputTokens : 0,
          maxContextUse,
          pricingStatusCode: pricingStatusCodeFor(calls),
          pricingStatus: pricingStatusFor(calls),
          creditStatus: creditStatusFor(calls),
          signalCount: signalTotal,
          subagentCount,
          autoReviewCount,
          attachedCount,
          lifecycle,
          attentionScore: 0,
        };
      });
      for (const group of groups) {
        group.attentionScore = threadAttentionScore(group);
      }
      return arrangeThreadGroups(groups, sortKey, sortDirection);
    }

    return {
      compareCalls,
      groupThreads,
      rowAttentionScore,
      severityForScore,
      signalCount,
      sortedThreadCalls,
      usageImpactValue,
    };
  }

  window.CodexUsageDashboardAnalysis = { create };
})();
