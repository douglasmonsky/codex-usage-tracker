(() => {
  const short = (value, fallback = 'Unknown') => value || fallback;

  function payloadRows(nextPayload) {
    return Array.isArray(nextPayload) ? nextPayload : Array.isArray(nextPayload.rows) ? nextPayload.rows : [];
  }

  function payloadLimit(nextPayload) {
    if (!nextPayload || nextPayload.limit === null || nextPayload.limit === undefined) return null;
    const parsed = Number(nextPayload.limit);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }

  function limitValue(limit) {
    return limit === null || limit === undefined ? 'all' : String(limit);
  }

  function optionValueExists(select, value) {
    if (!value) return false;
    return Array.from(select.options || []).some(option => option.value === value);
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function usageCreditValue(row) {
    return row.usage_credits === null || row.usage_credits === undefined ? null : Number(row.usage_credits || 0);
  }

  function rowInputTokens(row) {
    return Number(row.input_tokens || 0);
  }

  function cachedInputTokens(row) {
    return Number(row.cached_input_tokens || 0);
  }

  function uncachedInputTokens(row) {
    return Number(row.uncached_input_tokens || Math.max(rowInputTokens(row) - cachedInputTokens(row), 0));
  }

  function outputTokens(row) {
    return Number(row.output_tokens || 0);
  }

  function rowReasoningTokens(row) {
    return Number(row.reasoning_output_tokens || 0);
  }

  function usageCreditStatusText(row) {
    if (usageCreditValue(row) === null) return 'No mapped Codex credit rate';
    if (row.usage_credit_confidence === 'exact') return 'Official rate-card match';
    if (row.usage_credit_confidence === 'estimated') return 'Inferred model mapping';
    if (row.usage_credit_confidence === 'user_override') return 'User-provided credit rate';
    return short(row.usage_credit_confidence, 'Configured rate');
  }

  function sumUsageCredits(rows) {
    return rows.reduce((sum, row) => {
      const value = usageCreditValue(row);
      return value === null ? sum : sum + value;
    }, 0);
  }

  function creditCoverageRatio(rows) {
    const totalTokens = rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
    const ratedTokens = rows.reduce((sum, row) => sum + (usageCreditValue(row) === null ? 0 : Number(row.total_tokens || 0)), 0);
    return totalTokens ? ratedTokens / totalTokens : 0;
  }

  function isAutoReview(row) {
    return row.model === 'codex-auto-review' || row.subagent_type === 'guardian';
  }

  function isSubagent(row) {
    return row.thread_source === 'subagent' || Boolean(row.subagent_type || row.parent_session_id);
  }

  function sourceLabel(row) {
    if (isAutoReview(row)) return 'Auto-review';
    if (row.subagent_type === 'thread_spawn') {
      return row.agent_role ? `Subagent: ${row.agent_role}` : 'Subagent';
    }
    if (isSubagent(row)) return 'Subagent';
    return 'User';
  }

  function resolvedParentThreadName(row) {
    return row.resolved_parent_thread_name || row.parent_thread_name || '';
  }

  function resolvedParentSessionUpdatedAt(row) {
    return row.resolved_parent_session_updated_at || row.parent_session_updated_at || '';
  }

  function resolveThreadAttachment(row) {
    if (row.thread_attachment_key && row.thread_attachment_label) {
      return {
        key: row.thread_attachment_key,
        label: row.thread_attachment_label,
        relation: row.thread_attachment_relation || 'session',
        parentSessionId: row.thread_attachment_parent_session_id || row.parent_session_id || null,
      };
    }
    if (row.thread_name) {
      return { key: `thread:${row.thread_name}`, label: row.thread_name, relation: 'direct' };
    }
    const parentThreadName = resolvedParentThreadName(row);
    if (row.parent_session_id && parentThreadName) {
      return {
        key: `thread:${parentThreadName}`,
        label: parentThreadName,
        relation: 'explicit parent thread',
        parentSessionId: row.parent_session_id,
      };
    }
    if (row.parent_session_id) {
      return {
        key: `session:${row.parent_session_id}`,
        label: `Parent ${row.parent_session_id}`,
        relation: 'explicit parent',
        parentSessionId: row.parent_session_id,
      };
    }
    return {
      key: `session:${row.session_id || 'unknown'}`,
      label: row.session_id || 'Unknown thread',
      relation: isSubagent(row) ? 'unmatched subagent' : 'session',
    };
  }

  function chronological(a, b) {
    const timeCompare = String(a.event_timestamp || '').localeCompare(String(b.event_timestamp || ''));
    if (timeCompare !== 0) return timeCompare;
    return Number(a.cumulative_total_tokens || 0) - Number(b.cumulative_total_tokens || 0);
  }

  function resolvedThreadRows(rows, row) {
    const key = resolveThreadAttachment(row).key;
    return rows
      .filter(candidate => resolveThreadAttachment(candidate).key === key)
      .sort(chronological);
  }

  function adjacentThreadCalls(rows, row) {
    const calls = resolvedThreadRows(rows, row);
    const index = calls.findIndex(candidate => candidate.record_id === row.record_id);
    return {
      calls,
      index,
      previous: index > 0 ? calls[index - 1] : null,
      next: index >= 0 && index < calls.length - 1 ? calls[index + 1] : null,
    };
  }

  function classifyCacheDiagnostic(row, previous = null, options = {}) {
    const cache = Number(row.cache_ratio || 0);
    const previousCache = previous ? Number(previous.cache_ratio || 0) : null;
    const uncached = uncachedInputTokens(row);
    const previousUncached = previous ? uncachedInputTokens(previous) : 0;
    const coldRatio = Number(options.coldCacheRatio ?? 0.05);
    const warmRatio = Number(options.warmCacheRatio ?? 0.85);
    const previousWarmRatio = Number(options.coldResumePreviousRatio ?? 0.8);
    const significantTokens = Number(options.significantTokens ?? 1000);
    if (row.post_compaction || row.compaction_detected) return 'post_compaction';
    if (previous && previousCache >= previousWarmRatio && cache <= coldRatio && rowInputTokens(row) >= significantTokens) {
      return 'cold';
    }
    if (previous && uncached > Math.max(previousUncached * 2, significantTokens)) {
      return 'spike';
    }
    if (cache >= warmRatio) return 'warm';
    if (cache > coldRatio) return 'partial';
    return 'cold';
  }

  function callAccountingDelta(row, previous) {
    if (!previous) {
      return {
        input: 0,
        cached: 0,
        uncached: 0,
        output: 0,
        reasoning: 0,
        cacheRatio: 0,
      };
    }
    return {
      input: rowInputTokens(row) - rowInputTokens(previous),
      cached: cachedInputTokens(row) - cachedInputTokens(previous),
      uncached: uncachedInputTokens(row) - uncachedInputTokens(previous),
      output: outputTokens(row) - outputTokens(previous),
      reasoning: rowReasoningTokens(row) - rowReasoningTokens(previous),
      cacheRatio: Number(row.cache_ratio || 0) - Number(previous.cache_ratio || 0),
    };
  }

  function compactListSummary(values, fallback = 'Mixed') {
    const unique = [...new Set(values.filter(Boolean))].sort();
    if (!unique.length) return 'Unknown';
    if (unique.length === 1) return unique[0];
    return `${unique[0]} +${unique.length - 1} ${fallback.toLowerCase()}`;
  }

  function threadModelSummary(calls) {
    const models = [...new Set(calls.map(row => row.model).filter(Boolean))].sort();
    if (!models.length) return 'Unknown';
    if (models.length === 1) return models[0];
    const nonReviewModels = models.filter(model => model !== 'codex-auto-review');
    const primary = nonReviewModels.length ? nonReviewModels[0] : models[0];
    return `${primary} +${models.length - 1} models`;
  }

  window.CodexUsageDashboardData = Object.freeze({
    payloadRows,
    payloadLimit,
    limitValue,
    optionValueExists,
    clamp,
    usageCreditValue,
    rowInputTokens,
    cachedInputTokens,
    uncachedInputTokens,
    outputTokens,
    rowReasoningTokens,
    usageCreditStatusText,
    sumUsageCredits,
    creditCoverageRatio,
    isAutoReview,
    isSubagent,
    sourceLabel,
    resolvedParentThreadName,
    resolvedParentSessionUpdatedAt,
    resolveThreadAttachment,
    chronological,
    resolvedThreadRows,
    adjacentThreadCalls,
    classifyCacheDiagnostic,
    callAccountingDelta,
    compactListSummary,
    threadModelSummary,
  });
})();
