(() => {
  function create(deps) {
    const {
      allowanceWindowText,
      attachmentRelationText,
      callInitiatorPuck,
      callInitiatorText,
      copyCallLink,
      credits,
      detailEl,
      escapeHtml,
      formatTimestamp,
      getActiveView,
      getCallInvestigator,
      isPricingConfigured,
      moneyText,
      number,
      openInvestigator,
      pct,
      recommendationSummary,
      resolvedParentSessionUpdatedAt,
      resolvedParentThreadName,
      rowAllowanceImpact,
      rowAttachment,
      short,
      sourceLabelText,
      t,
      tf,
      threshold,
      translateEfficiencyFlag,
      translatedField,
      usageCreditStatusLabel,
      usageCreditValue,
      usageCreditsWithStatus,
    } = deps;

    function pricingStatusText(row) {
      if (!row.pricing_model) return t('state.no_configured_price');
      return row.pricing_estimated ? t('state.best_guess_estimate') : t('state.configured_price');
    }

    function nextActionForRow(row) {
      if (row.recommended_action || row.recommended_action_key) {
        return translatedField(row.recommended_action_key, row.recommended_action);
      }
      if (!row.pricing_model) return t('action.configure_pricing');
      if (Number(row.cache_ratio || 0) < 0.3 && Number(row.input_tokens || 0) > 0) return t('action.compare_fresh_input');
      if (Number(row.context_window_percent || 0) >= 0.6) return t('action.inspect_thread_timeline');
      if (Number(row.reasoning_output_tokens || 0) > Number(row.output_tokens || 0)) return t('action.review_reasoning_effort');
      return t('action.use_aggregate_first');
    }

    function fieldsList(fields, className = 'detail-kv') {
      return `<dl class="${className}">${fields.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(short(value))}</dd>`).join('')}</dl>`;
    }

    function detailCollapse(title, fields) {
      return `
        <details class="detail-collapse">
          <summary>${escapeHtml(title)}</summary>
          <div class="detail-collapse-body">${fieldsList(fields)}</div>
        </details>
      `;
    }

    function timelineSeverity(value) {
      if (value >= 0.65) return 'high';
      if (value >= 0.35) return 'medium';
      return 'low';
    }

    function timelineWidth(value) {
      return `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`;
    }

    function renderThreadTimeline(group) {
      const calls = group.calls.slice(-5);
      if (!calls.length) return `<p>${escapeHtml(t('detail.timeline_empty'))}</p>`;
      return `<div class="timeline-list">${calls.map(row => {
        const contextUse = Number(row.context_window_percent || 0);
        return `
          <div class="timeline-item">
            <div class="timeline-time">${escapeHtml(formatTimestamp(row.event_timestamp, t('state.unknown')))}</div>
            <div>
              <div class="timeline-title">${callInitiatorPuck(row)} ${escapeHtml(short(row.model))}</div>
              <div class="timeline-meta">${escapeHtml(tf('detail.timeline_meta', { tokens: number.format(row.total_tokens || 0), cost: moneyText(row.estimated_cost_usd), credits: usageCreditValue(row) === null ? t('credit.no_rate') : `${credits(usageCreditValue(row))} ${t('badge.credits')}`, cache: pct(row.cache_ratio) }))}</div>
              <div class="timeline-meta">${escapeHtml(recommendationSummary(row))}</div>
              <div class="signal-strip">
                <span class="flag">${escapeHtml(tf('detail.timeline_context', { value: pct(contextUse) }))}</span>
                <span class="flag">${escapeHtml(pricingStatusText(row))}</span>
              </div>
              <div class="mini-bar" title="${escapeHtml(t('metric.context_use'))} ${escapeHtml(pct(contextUse))}"><span class="${timelineSeverity(contextUse)}" style="width: ${timelineWidth(contextUse)}"></span></div>
            </div>
          </div>
        `;
      }).join('')}</div>`;
    }

    function bindDetailButtons(row, includeEvidence = true) {
      const openButton = detailEl.querySelector('[data-open-investigator-record]');
      const copyButton = detailEl.querySelector('[data-copy-call-link]');
      if (openButton) openButton.addEventListener('click', () => openInvestigator(row));
      if (copyButton) copyButton.addEventListener('click', () => copyCallLink(row));
      const investigator = getCallInvestigator();
      if (includeEvidence && investigator) investigator.bindContextButtons(row);
    }

    function showDetail(row) {
      const attachment = rowAttachment(row);
      const includeEvidence = getActiveView() !== 'call';
      const flagValues = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
      const explanationKeys = Array.isArray(row.flag_explanation_keys) ? row.flag_explanation_keys : [];
      const flags = flagValues.length ? flagValues.map((flag, index) => translateEfficiencyFlag(row, flag, index)).join(', ') : t('state.none');
      const whyFlagged = Array.isArray(row.flag_explanations) && row.flag_explanations.length
        ? row.flag_explanations.map((explanation, index) => translatedField(explanationKeys[index], explanation)).join(' ')
        : recommendationSummary(row);
      const investigator = getCallInvestigator();
      detailEl.innerHTML = `
        <div class="detail-stack">
          <div class="detail-card primary">
            <h3>${escapeHtml(t('detail.cost_usage_context'))}</h3>
            <div class="detail-action-row">
              <button class="context-button" type="button" data-open-investigator-record="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.open_investigator'))}</button>
              <button class="context-button secondary" type="button" data-copy-call-link="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.copy_link'))}</button>
            </div>
            ${fieldsList([
              [t('metric.estimated_cost'), moneyText(row.estimated_cost_usd)],
              [t('metric.codex_credits'), usageCreditsWithStatus(row)],
              [t('detail.allowance_impact'), rowAllowanceImpact(row)],
              [t('metric.cache_ratio'), pct(row.cache_ratio)],
              [t('metric.uncached_input'), number.format(row.uncached_input_tokens || 0)],
              [t('metric.context_use'), pct(row.context_window_percent)],
              [t('detail.pricing_status'), pricingStatusText(row)],
              [t('detail.next_action'), nextActionForRow(row)],
              [t('detail.why_flagged'), whyFlagged],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.thread_narrative'))}</h3>
            <div class="detail-source-line">${callInitiatorPuck(row)}<span>${escapeHtml(sourceLabelText(row))}</span></div>
            ${fieldsList([
              [t('table.thread'), attachment.label],
              [t('filter.project'), row.project_name || t('state.unknown')],
              [t('detail.project_tags'), Array.isArray(row.project_tags) && row.project_tags.length ? row.project_tags.join(', ') : t('state.none')],
              [t('detail.thread_attachment'), attachmentRelationText(attachment.relation)],
              [t('table.source'), callInitiatorText(row)],
              [t('detail.parent_thread'), resolvedParentThreadName(row) || t('state.none')],
              [t('detail.timestamp'), formatTimestamp(row.event_timestamp)],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.token_pricing_breakdown'))}</h3>
            ${fieldsList([
              [t('metric.last_call_total'), number.format(row.total_tokens || 0)],
              [t('metric.last_call_input'), number.format(row.input_tokens || 0)],
              [t('metric.cached_input'), number.format(row.cached_input_tokens || 0)],
              [t('metric.output'), number.format(row.output_tokens || 0)],
              [t('metric.reasoning_output'), number.format(row.reasoning_output_tokens || 0)],
              [t('metric.session_cumulative'), number.format(row.cumulative_total_tokens || 0)],
              [t('detail.pricing_model'), row.pricing_model || t('state.no_configured_price')],
              [t('detail.credit_model'), row.usage_credit_model || t('credit.no_mapped_rate')],
              [t('detail.credit_confidence'), usageCreditStatusLabel(row)],
              [t('detail.credit_source'), t(row.usage_credit_source) || t('state.none')],
              [t('detail.credit_source_fetched'), row.usage_credit_fetched_at || t('state.unknown')],
              [t('detail.credit_tier'), t(row.usage_credit_tier) || t('state.unknown')],
              [t('detail.cache_savings'), moneyText(row.estimated_cache_savings_usd)],
              [t('detail.efficiency_signals'), flags],
            ])}
          </div>
          ${detailCollapse(t('detail.raw_identifiers'), [
            [t('filter.session'), row.session_id],
            [t('detail.turn'), row.turn_id],
            [t('detail.thread_source'), row.thread_source || t('source.user')],
            [t('detail.subagent_type'), row.subagent_type || t('state.none')],
            [t('detail.agent_role'), row.agent_role || t('state.none')],
            [t('detail.agent_nickname'), row.agent_nickname || t('state.none')],
            [t('detail.credit_note'), row.usage_credit_note || t('state.none')],
            [t('detail.parent_session'), row.parent_session_id || t('state.none')],
            [t('detail.parent_updated'), resolvedParentSessionUpdatedAt(row) ? formatTimestamp(resolvedParentSessionUpdatedAt(row)) : t('state.none')],
            [t('detail.cwd'), row.cwd],
            [t('detail.project_cwd'), row.project_relative_cwd || '.'],
            [t('detail.git_branch'), row.git_branch || t('state.unknown')],
            [t('detail.remote_label'), row.git_remote_label || t('state.none')],
            [t('detail.remote_hash'), row.git_remote_hash || t('state.none')],
          ])}
          ${detailCollapse(t('detail.source_file_line'), [
            [t('detail.source_line'), `${row.source_file}:${row.line_number}`],
            [t('detail.context_window'), number.format(row.model_context_window || 0)],
          ])}
          ${includeEvidence && investigator ? investigator.contextControls(row) : ''}
        </div>
      `;
      bindDetailButtons(row, includeEvidence);
    }

    function showThreadDetail(group) {
      const lifecycle = group.lifecycle || {};
      detailEl.innerHTML = `
        <div class="detail-stack">
          <div class="detail-card primary">
            <h3>${escapeHtml(t('detail.thread_attention_summary'))}</h3>
            ${fieldsList([
              [t('metric.estimated_cost'), isPricingConfigured() ? moneyText(group.estimatedCost) : t('state.not_configured')],
              [t('metric.codex_credits'), tf('credit.with_status', { value: credits(group.usageCredits), status: group.creditStatus })],
              [t('detail.allowance_impact'), allowanceWindowText(group.usageCredits, 'impact') || allowanceWindowText(group.usageCredits, 'remaining') || tf('allowance.counted', { value: credits(group.usageCredits) })],
              [t('metric.attention_score'), number.format(Math.round(group.attentionScore))],
              [t('metric.cache_ratio'), pct(group.cacheRatio)],
              [t('metric.max_context_use'), pct(group.maxContextUse)],
              [t('detail.pricing_status'), group.pricingStatus],
              [t('detail.next_action'), lifecycle.action || (group.maxContextUse >= threshold('high_context_percent', 0.6) || group.cacheRatio < threshold('low_cache_ratio', 0.3) ? t('action.inspect_thread_timeline') : t('action.expand_or_select_recommendations'))],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.thread_lifecycle'))}</h3>
            ${fieldsList([
              [t('detail.first_expensive_turn'), lifecycle.firstExpensiveRow ? `${formatTimestamp(lifecycle.firstExpensiveRow.event_timestamp)} · ${tf('detail.call_number', { number: number.format((lifecycle.firstExpensiveIndex || 0) + 1) })}` : t('detail.no_above_thresholds')],
              [t('detail.largest_cumulative_jump'), lifecycle.largestJumpRow ? tf('detail.tokens_at', { tokens: number.format(lifecycle.largestJump), time: formatTimestamp(lifecycle.largestJumpRow.event_timestamp) }) : t('state.none')],
              [t('metric.cache_trend'), `${lifecycle.cacheTrend >= 0 ? '+' : ''}${pct(lifecycle.cacheTrend || 0)}`],
              [t('metric.context_trend'), `${lifecycle.contextTrend >= 0 ? '+' : ''}${pct(lifecycle.contextTrend || 0)}`],
              [t('detail.subagent_before_spike'), lifecycle.subagentBeforeSpike ? t('state.yes') : t('state.no')],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.thread_timeline'))}</h3>
            ${renderThreadTimeline(group)}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.relationships'))}</h3>
            ${fieldsList([
              [t('table.thread'), group.label],
              [t('detail.calls'), number.format(group.callCount)],
              [t('detail.subagent_calls'), number.format(group.subagentCount)],
              [t('detail.auto_review_calls'), number.format(group.autoReviewCount)],
              [t('detail.attached_calls'), number.format(group.attachedCount)],
              [t('detail.spawned_from'), group.parentThreadLabel || t('state.none')],
              [t('detail.spawned_threads'), number.format(group.childThreadCount || 0)],
              [t('detail.spawned_child_calls'), number.format(group.childCallCount || 0)],
            ])}
          </div>
          ${detailCollapse(t('detail.secondary_thread_fields'), [
            [t('detail.latest_activity'), formatTimestamp(group.latestActivity)],
            [t('metric.total_tokens'), number.format(group.totalTokens)],
            [t('detail.efficiency_signals'), number.format(group.signalCount)],
            [t('detail.model_mix'), group.modelSummary],
            [t('detail.reasoning_mix'), group.effortSummary],
          ])}
        </div>
      `;
    }

    return {
      pricingStatusText,
      showDetail,
      showThreadDetail,
    };
  }

  window.CodexUsageDashboardDetails = { create };
})();
