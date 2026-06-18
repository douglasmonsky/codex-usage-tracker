(function () {
  function create(deps) {
    const {
      credits,
      dataCachedInputTokens,
      dataOutputTokens,
      dataUncachedInputTokens,
      escapeHtml,
      isAutoReview,
      isSubagent,
      number,
      short,
      t,
      tf,
      tooltipAttributes,
      translateEffort,
      translateEfficiencyFlag,
      usageCreditValue,
    } = deps;

    function usageCreditStatusLabel(row) {
      if (usageCreditValue(row) === null) return t('allowance.row_no_rate');
      if (row.usage_credit_confidence === 'exact') return t('credit.official_match');
      if (row.usage_credit_confidence === 'estimated') return t('credit.inferred_mapping');
      if (row.usage_credit_confidence === 'user_override') return t('credit.user_rate');
      return short(row.usage_credit_confidence, t('credit.configured_rate'));
    }

    function sourceLabelText(row) {
      if (isAutoReview(row)) return t('source.auto_review');
      if (row.subagent_type === 'thread_spawn') {
        return row.agent_role ? tf('source.subagent_role', { role: row.agent_role }) : t('source.subagent');
      }
      if (isSubagent(row)) return t('source.subagent');
      return t('source.user');
    }

    function callInitiatorReasonText(row) {
      return {
        user_message: 'First model call after a user message',
        tool_result: 'Continuation after tool output',
        post_compaction: 'Post-compaction continuation',
        agent_continuation: 'Codex continuation',
        thread_source: sourceLabelText(row),
        no_signal: 'No source event signal found',
        source_unavailable: 'Source event metadata unavailable',
        missing_source: 'Source event metadata unavailable',
      }[row.call_initiator_reason] || sourceLabelText(row);
    }

    function callInitiator(row) {
      const derived = String(row.call_initiator || '').toLowerCase();
      if (derived === 'user' || derived === 'codex') {
        return {
          key: derived,
          label: derived === 'codex' ? t('source.codex_initiated') : t('source.user_initiated'),
          shortLabel: derived === 'codex' ? 'Codex' : t('source.user'),
          source: callInitiatorReasonText(row),
        };
      }
      if (derived === 'unknown') {
        return {
          key: 'unknown',
          label: t('state.unknown'),
          shortLabel: t('state.unknown'),
          source: callInitiatorReasonText(row),
        };
      }
      const codexInitiated = isAutoReview(row)
        || isSubagent(row)
        || (row.thread_source && row.thread_source !== 'user');
      return {
        key: codexInitiated ? 'codex' : 'user',
        label: codexInitiated ? t('source.codex_initiated') : t('source.user_initiated'),
        shortLabel: codexInitiated ? 'Codex' : t('source.user'),
        source: sourceLabelText(row),
      };
    }

    function callInitiatorText(row) {
      const initiator = callInitiator(row);
      return `${initiator.label} - ${initiator.source}`;
    }

    function callInitiatorPuck(row) {
      const initiator = callInitiator(row);
      const title = `${initiator.label}: ${initiator.source}`;
      return `<span class="initiator-puck initiator-${escapeHtml(initiator.key)}" ${tooltipAttributes(title)}>${escapeHtml(initiator.shortLabel)}</span>`;
    }

    function callInitiatorCell(row) {
      const initiator = callInitiator(row);
      return `
        <div class="initiator-cell" ${tooltipAttributes(`${initiator.label}: ${initiator.source}`)}>
          ${callInitiatorPuck(row)}
        </div>
      `;
    }

    function threadInitiatorSummary(group) {
      const counts = (group.calls || []).reduce((acc, row) => {
        const key = callInitiator(row).key || 'unknown';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }, {});
      const total = Math.max(Number(group.callCount || 0), 1);
      const items = [
        ['user', t('source.user'), counts.user || 0],
        ['codex', 'Codex', counts.codex || 0],
        ['unknown', t('state.unknown'), counts.unknown || 0],
      ].filter(([, , count]) => count > 0);
      return `
        <div class="initiator-summary">
          ${items.map(([key, label, count]) => `
            <span class="initiator-puck initiator-${escapeHtml(key)}" ${tooltipAttributes(`${label}: ${number.format(count)} / ${number.format(total)} ${t('table.calls')}`)}>${escapeHtml(label)} ${escapeHtml(number.format(count))}</span>
          `).join('')}
        </div>
      `;
    }

    function attachmentRelationText(relation) {
      return {
        direct: t('thread.direct'),
        session: t('thread.session'),
        'explicit parent thread': t('thread.explicit_parent_thread'),
        'explicit parent': t('thread.explicit_parent'),
        'unmatched subagent': t('thread.unmatched_subagent'),
      }[relation] || relation || t('state.unknown');
    }

    function usageCreditsWithStatus(row) {
      const value = usageCreditValue(row);
      return value === null
        ? t('credit.no_mapped_rate')
        : tf('credit.with_status', { value: credits(value), status: usageCreditStatusLabel(row) });
    }

    function costUsageCell(costText, creditValue) {
      const usage = creditValue === null || creditValue === undefined ? t('credit.no_rate') : credits(creditValue);
      return `<span class="cost-cell" ${tooltipAttributes(`${t('metric.codex_credits')}: ${usage}`)}>${escapeHtml(costText)}</span>`;
    }

    function cachedInputTokens(row) {
      return dataCachedInputTokens(row);
    }

    function uncachedInputTokens(row) {
      return dataUncachedInputTokens(row);
    }

    function outputTokens(row) {
      return dataOutputTokens(row);
    }

    function tokenNumberCell(value, label) {
      return `<span class="token-number" ${tooltipAttributes(`${label}: ${number.format(value)}`)}>${escapeHtml(number.format(value))}</span>`;
    }

    function totalTokenCell(row) {
      const total = Number(row.total_tokens || 0);
      const title = [
        `${t('metric.total_tokens')}: ${number.format(total)}`,
        `${t('metric.cached_input')}: ${number.format(cachedInputTokens(row))}`,
        `${t('metric.uncached_input')}: ${number.format(uncachedInputTokens(row))}`,
        `${t('metric.output_tokens')}: ${number.format(outputTokens(row))}`,
        Number(row.reasoning_output_tokens || 0) ? `${t('metric.reasoning_output')}: ${number.format(row.reasoning_output_tokens || 0)}` : '',
      ].filter(Boolean).join(' - ');
      return `<span class="token-number token-total" ${tooltipAttributes(title)}>${escapeHtml(number.format(total))}</span>`;
    }

    function cachedTokenCell(row) {
      return tokenNumberCell(cachedInputTokens(row), t('metric.cached_input'));
    }

    function uncachedTokenCell(row) {
      return tokenNumberCell(uncachedInputTokens(row), t('metric.uncached_input'));
    }

    function outputTokenCell(row) {
      return tokenNumberCell(outputTokens(row), t('metric.output_tokens'));
    }

    function reasoningTokenCell(row) {
      return tokenNumberCell(Number(row.reasoning_output_tokens || 0), t('metric.reasoning_output'));
    }

    function effortTooltipText(values) {
      const unique = [...new Set(values.filter(Boolean).map(value => translateEffort(short(value))))].sort();
      return unique.length ? unique.join(' - ') : t('state.unknown');
    }

    function effortCell(label, tooltip) {
      return `<span class="effort-cell" ${tooltipAttributes(tooltip || label)}>${escapeHtml(label)}</span>`;
    }

    function signalPuckLabel(row, flag, index) {
      return translateEfficiencyFlag(row, flag, index);
    }

    function signalPuckAbbreviation(flag, label) {
      const byFlag = {
        'context-bloat': 'CTX',
        'elevated-context-use': 'CTX',
        'elevated-context': 'CTX',
        'expensive-low-output-call': 'LO',
        'estimated-pricing': 'EST',
        'high-context-use': 'CTX',
        'high-estimated-cost': '$',
        'high-cost': '$',
        'high-reasoning-share': 'RSN',
        'large-thread': 'BIG',
        'low-cache-reuse': 'CACHE',
        'low-cache': 'CACHE',
        'low-output': 'LO',
        'pricing-gap': 'PRICE',
        'reasoning-spike': 'RSN',
        'subagent-attribution': 'SUB',
      };
      const normalized = String(flag || '').toLowerCase().replace(/[_\s]+/g, '-');
      if (byFlag[normalized]) return byFlag[normalized];
      const words = String(label || flag || '')
        .replace(/[^a-zA-Z0-9 ]/g, ' ')
        .split(/\s+/)
        .filter(Boolean);
      if (!words.length) return '?';
      if (words.length === 1) return words[0].slice(0, 4).toUpperCase();
      return words.slice(0, 3).map(word => word[0]).join('').toUpperCase();
    }

    function renderSignalPucks(row, flags, max = 3, emptyLabel = '') {
      if (!flags.length) return emptyLabel ? `<span class="muted">${escapeHtml(emptyLabel)}</span>` : '';
      const visible = flags.slice(0, max);
      const pucks = visible.map((flag, index) => {
        const label = signalPuckLabel(row, flag, index);
        return `<span class="flag signal-puck" ${tooltipAttributes(label)}>${escapeHtml(signalPuckAbbreviation(flag, label))}</span>`;
      });
      if (flags.length > max) {
        const remaining = flags.slice(max).map((flag, offset) => signalPuckLabel(row, flag, max + offset)).join(' - ');
        pucks.push(`<span class="flag signal-puck more" ${tooltipAttributes(remaining)}>+${escapeHtml(flags.length - max)}</span>`);
      }
      return pucks.join('');
    }

    return {
      attachmentRelationText,
      cachedInputTokens,
      cachedTokenCell,
      callInitiator,
      callInitiatorCell,
      callInitiatorPuck,
      callInitiatorReasonText,
      callInitiatorText,
      costUsageCell,
      effortCell,
      effortTooltipText,
      outputTokenCell,
      outputTokens,
      reasoningTokenCell,
      renderSignalPucks,
      signalPuckAbbreviation,
      signalPuckLabel,
      sourceLabelText,
      threadInitiatorSummary,
      tokenNumberCell,
      totalTokenCell,
      uncachedInputTokens,
      uncachedTokenCell,
      usageCreditsWithStatus,
      usageCreditStatusLabel,
    };
  }

  window.CodexUsageDashboardCells = { create };
})();
