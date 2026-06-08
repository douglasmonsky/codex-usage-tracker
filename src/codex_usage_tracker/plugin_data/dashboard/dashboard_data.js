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

  function usageCreditStatusText(row) {
    if (row.usage_credit_confidence === 'not_applicable') return 'Not applicable';
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
    const applicableCreditRows = rows.filter(row => row.usage_credit_confidence !== 'not_applicable');
    const totalTokens = applicableCreditRows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
    const ratedTokens = applicableCreditRows.reduce((sum, row) => sum + (usageCreditValue(row) === null ? 0 : Number(row.total_tokens || 0)), 0);
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
    compactListSummary,
    threadModelSummary,
  });
})();
