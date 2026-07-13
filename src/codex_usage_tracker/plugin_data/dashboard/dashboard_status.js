(() => {
  const NON_ACTIONABLE_PARSER_DIAGNOSTICS = new Set([
    'duplicate_cumulative_total',
  ]);

  function createDashboardStatus(deps) {
    const {
      allowanceImpactElement,
      allowanceReconcileElement,
      allowanceSourceElement,
      creditCoverageRatio,
      credits,
      formatTimestamp,
      formatTimestampTitle,
      getAllowanceConfigured,
      getAllowanceError,
      getAllowanceSource,
      getAllowanceWindows,
      getData,
      getObservedUsage,
      getParserDiagnostics,
      getPricingConfigured,
      getPricingSnapshotWarning,
      getPricingSource,
      getProjectMetadataPrivacy,
      getRateCardError,
      liveStatusElement,
      number,
      parserDiagnosticsElement,
      pct,
      pricingSourceElement,
      privacyModeElement,
      setFastTooltip,
      short,
      t,
      tf,
      usageCreditValue,
    } = deps;
    let liveStatusKey = window.location.protocol !== 'file:' ? 'badge.live' : 'status.static';
    let liveStatusDetail = '';

    function allowanceWindowText(totalCredits, mode = 'impact') {
      const allowanceWindows = getAllowanceWindows();
      if (!allowanceWindows.length) return '';
      const labels = allowanceWindows.map(window => {
        const label = short(window.label || window.key, 'Window');
        const total = Number(window.total_credits || 0);
        const remainingCredits = window.remaining_credits === null || window.remaining_credits === undefined ? null : Number(window.remaining_credits);
        const remainingPercent = window.remaining_percent === null || window.remaining_percent === undefined ? null : Number(window.remaining_percent);
        if (mode === 'remaining-card' && remainingPercent !== null && Number.isFinite(remainingPercent)) {
          return `${label} ${pct(remainingPercent)}`;
        }
        if (mode === 'remaining-card' && remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${tf('allowance.cr_left', { value: credits(remainingCredits) })}`;
        }
        if (mode === 'impact' && total > 0) {
          return `${label} ${tf('allowance.of_allowance', { ratio: pct(totalCredits / total) })}`;
        }
        if (mode === 'impact' && remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${tf('allowance.used_vs_remaining', { used: credits(totalCredits), remaining: credits(remainingCredits) })}`;
        }
        if (remainingPercent !== null && Number.isFinite(remainingPercent)) {
          return `${label} ${tf('allowance.remaining', { value: pct(remainingPercent) })}`;
        }
        if (remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${tf('allowance.credits_remaining', { value: credits(remainingCredits) })}`;
        }
        if (total > 0) {
          return `${label} ${tf('allowance.of_total', { used: credits(totalCredits), total: credits(total) })}`;
        }
        return tf('allowance.window_configured', { label });
      });
      return labels.join(mode === 'remaining-card' ? '\n' : ' · ');
    }

    function allowanceImpactText(totalCredits) {
      const observed = observedUsageText();
      if (observed) return observed;
      const windowImpact = allowanceWindowText(totalCredits, 'remaining-card') || allowanceWindowText(totalCredits, 'impact');
      if (windowImpact) return windowImpact;
      if (getAllowanceError()) return t('state.allowance_config_error');
      return t('action.set_limits');
    }

    function observedUsageText() {
      const observed = getObservedUsage() || {};
      const windows = Array.isArray(observed.windows) ? observed.windows : [];
      if (!observed.available || !windows.length) return '';
      return windows
        .map(window => observedWindowText(window))
        .filter(Boolean)
        .join('\n');
    }

    function observedWindowText(window) {
      const remaining = observedRemainingPercent(window.used_percent);
      if (!remaining) return '';
      return `${observedWindowLabel(window)}: ${remaining}`;
    }

    function observedWindowLabel(window) {
      const raw = short(window.label || window.key, 'Usage');
      if (String(window.key || '').toLowerCase() === 'weekly' || raw.toLowerCase() === 'weekly') {
        return t('allowance.window_weekly');
      }
      return raw;
    }

    function observedUsageTooltip() {
      const observed = getObservedUsage() || {};
      const windows = Array.isArray(observed.windows) ? observed.windows : [];
      if (!observed.available || !windows.length) return '';
      return [
        t('allowance.observed_source_hint'),
        observedReconciliationTooltip(observed),
        observed.observed_at ? tf('allowance.observed_last', { age: observedAgeText(observed.observed_at) }) : '',
        observed.plan_type ? tf('allowance.observed_plan', { plan: observed.plan_type }) : '',
        observed.limit_id ? tf('allowance.observed_limit', { limit: observed.limit_id }) : '',
        ...windows.map(window => observedWindowTooltip(window)).filter(Boolean),
      ].filter(Boolean).join(' ');
    }

    function observedReconciliationTooltip(observed) {
      const reconciliation = observed.reconciliation || {};
      if (!reconciliation.recommended) return '';
      return tf('allowance.live_check_recommended', {
        count: reconciliation.consecutive_alternate_rows || 0,
        limit: reconciliation.latest_limit_id || 'alternate Codex limit',
      });
    }

    function observedWindowTooltip(window) {
      const used = observedPercent(window.used_percent);
      if (!used) return '';
      const remaining = observedRemainingPercent(window.used_percent);
      const reset = observedResetText(window.resets_at);
      const label = observedWindowLabel(window);
      const usage = remaining
        ? `${label}: ${tf('allowance.used_vs_remaining', { used, remaining })}`
        : tf('allowance.observed_window', { label, used });
      return reset ? `${usage} ${tf('allowance.resets', { resets: reset })}` : usage;
    }

    function observedPercent(value) {
      if (value === null || value === undefined || value === '') return '';
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return '';
      const digits = Math.abs(numeric) >= 10 ? 0 : 1;
      return `${numeric.toFixed(digits)}%`;
    }

    function observedRemainingPercent(value) {
      if (value === null || value === undefined || value === '') return '';
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return '';
      const remaining = Math.max(0, Math.min(100, 100 - numeric));
      const digits = Math.abs(remaining) >= 10 ? 0 : 1;
      return `${remaining.toFixed(digits)}%`;
    }

    function observedResetText(value) {
      if (value === null || value === undefined || value === '') return '';
      const numeric = Number(value);
      if (!Number.isFinite(numeric) || numeric <= 0) return '';
      return formatTimestamp(new Date(numeric * 1000).toISOString(), '');
    }

    function observedAgeText(value) {
      const observedAt = new Date(value);
      if (Number.isNaN(observedAt.getTime())) return formatTimestamp(value, value);
      const elapsedSeconds = Math.max(0, Math.floor((Date.now() - observedAt.getTime()) / 1000));
      if (elapsedSeconds < 60) return t('allowance.observed_age_now');
      if (elapsedSeconds < 3600) return tf('allowance.observed_age_minutes', { count: Math.floor(elapsedSeconds / 60) });
      if (elapsedSeconds < 86400) return tf('allowance.observed_age_hours', { count: Math.floor(elapsedSeconds / 3600) });
      return tf('allowance.observed_age_days', { count: Math.floor(elapsedSeconds / 86400) });
    }

    function rowAllowanceImpact(row) {
      const value = usageCreditValue(row);
      if (value === null) return t('allowance.row_no_rate');
      const impact = allowanceWindowText(value, 'impact');
      return impact || tf('allowance.counted', { value: credits(value) });
    }

    function updateAllowanceSourceLine() {
      const sourceEl = allowanceSourceElement;
      const allowanceSource = getAllowanceSource();
      const allowanceWindows = getAllowanceWindows();
      const allowanceError = getAllowanceError();
      const rateCardError = getRateCardError();
      const sourceName = allowanceSource.name || 'Codex credit rates';
      const coverage = creditCoverageRatio(getData());
      sourceEl.textContent = t('badge.credits');
      sourceEl.dataset.state = coverage > 0 ? 'ready' : 'missing';
      setFastTooltip(sourceEl, [
        allowanceSource.url ? `${t('pricing.source')}: ${allowanceSource.url}` : '',
        allowanceSource.fetched_at ? `rate card snapshot ${allowanceSource.fetched_at}` : '',
        tf('allowance.credit_rates', { source: sourceName }),
        tf('allowance.credit_coverage', { ratio: pct(coverage) }),
        allowanceWindows.length ? tf('allowance.windows', { windows: allowanceWindows.map(window => short(window.label || window.key)).join(', ') }) : t('allowance.init_hint'),
        allowanceWindows.some(window => window.reset_at) ? tf('allowance.resets', { resets: allowanceWindows.map(window => window.reset_at ? `${short(window.label || window.key)} ${formatTimestamp(window.reset_at, window.reset_at)}` : '').filter(Boolean).join('; ') }) : '',
        allowanceError ? `${t('state.allowance_config_error')}: ${allowanceError}` : '',
        rateCardError ? tf('allowance.rate_card_error', { error: rateCardError }) : '',
      ].filter(Boolean).join(' '));
    }

    function updatePricingSourceLine() {
      const sourceEl = pricingSourceElement;
      const pricingConfigured = getPricingConfigured();
      const pricingSource = getPricingSource();
      const pricingSnapshotWarning = getPricingSnapshotWarning();
      if (pricingConfigured && pricingSource.url) {
        const sourceParts = [
          pricingSource.name || t('pricing.source'),
          pricingSource.tier ? tf('pricing.tier', { tier: pricingSource.tier }) : '',
          pricingSource.fetched_at ? tf('pricing.fetched', { time: formatTimestamp(pricingSource.fetched_at) }) : '',
          pricingSource.pinned ? t('pricing.pinned') : '',
        ].filter(Boolean);
        sourceEl.textContent = t('badge.costs');
        sourceEl.dataset.state = 'ready';
        setFastTooltip(sourceEl, pricingSource.fetched_at
          ? tf('pricing.title_fetched', { parts: sourceParts.join(' · '), url: pricingSource.url, time: formatTimestampTitle(pricingSource.fetched_at), warning: pricingSnapshotWarning ? ` ${pricingSnapshotWarning}` : '' })
          : tf('pricing.title', { parts: sourceParts.join(' · '), warning: pricingSnapshotWarning ? ` ${pricingSnapshotWarning}` : '' }));
      } else {
        sourceEl.textContent = pricingConfigured ? t('badge.costs') : t('badge.no_costs');
        sourceEl.dataset.state = pricingConfigured ? 'ready' : 'missing';
        setFastTooltip(sourceEl, pricingConfigured ? (pricingSnapshotWarning || '') : t('pricing.configure_hint'));
      }
    }

    function updateParserDiagnosticsLine() {
      const sourceEl = parserDiagnosticsElement;
      const entries = Object.entries(getParserDiagnostics() || {})
        .filter(([key, value]) => (
          Number(value || 0) > 0
          && !NON_ACTIONABLE_PARSER_DIAGNOSTICS.has(key)
        ));
      if (!entries.length) {
        sourceEl.hidden = true;
        sourceEl.textContent = '';
        setFastTooltip(sourceEl, '');
        return;
      }
      const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
      sourceEl.hidden = false;
      sourceEl.textContent = t('badge.parser_warnings');
      sourceEl.dataset.state = 'missing';
      setFastTooltip(sourceEl, tf('parser.warnings_title', { count: number.format(total), entries: entries.map(([key, value]) => `${key}=${value}`).join(', ') }));
    }

    function updatePrivacyModeLine() {
      const sourceEl = privacyModeElement;
      const projectMetadataPrivacy = getProjectMetadataPrivacy();
      const mode = projectMetadataPrivacy.mode || 'normal';
      sourceEl.textContent = mode === 'normal' ? t('badge.metadata_normal') : tf('badge.metadata_mode', { mode });
      sourceEl.dataset.state = mode === 'normal' ? 'ready' : 'missing';
      setFastTooltip(sourceEl, mode === 'normal'
        ? t('privacy.normal_title')
        : [
            tf('privacy.mode', { mode }),
            projectMetadataPrivacy.cwd_redacted ? t('privacy.cwd_redacted') : '',
            projectMetadataPrivacy.project_names_redacted ? t('privacy.project_names_redacted') : '',
            projectMetadataPrivacy.git_remote_label_hidden ? t('privacy.git_remote_label_hidden') : '',
            projectMetadataPrivacy.relative_cwd_hidden ? t('privacy.relative_cwd_hidden') : '',
            projectMetadataPrivacy.git_branch_hidden ? t('privacy.git_branch_hidden') : '',
            projectMetadataPrivacy.tags_hidden ? t('privacy.tags_hidden') : '',
            projectMetadataPrivacy.aliases_preserved ? t('privacy.aliases_preserved') : '',
          ].filter(Boolean).join(' '));
    }

    function updateAllowanceImpact(totalCredits) {
      allowanceImpactElement.textContent = allowanceImpactText(totalCredits);
      setFastTooltip(
        allowanceImpactElement,
        observedUsageTooltip() || allowanceWindowText(totalCredits, 'remaining') || t('allowance.title_hint'),
      );
      updateAllowanceReconciliation();
    }

    function updateAllowanceReconciliation() {
      if (!allowanceReconcileElement) return;
      const observed = getObservedUsage() || {};
      const tooltip = observedReconciliationTooltip(observed);
      const show = Boolean(observed.reconciliation && observed.reconciliation.recommended);
      allowanceReconcileElement.hidden = !show;
      if (!show) {
        setFastTooltip(allowanceReconcileElement, '');
        return;
      }
      allowanceReconcileElement.textContent = t('allowance.live_check_short');
      setFastTooltip(allowanceReconcileElement, tooltip || t('allowance.observed_source_hint'));
    }

    function renderLiveStatus() {
      const label = t(liveStatusKey);
      const detail = liveStatusDetail || label;
      liveStatusElement.textContent = label;
      setFastTooltip(liveStatusElement, detail);
      liveStatusElement.dataset.state = liveStatusKey === 'status.refresh_error' ? 'error' : 'ready';
    }

    function updateLiveStatus(statusKey, detail = '') {
      liveStatusKey = statusKey;
      liveStatusDetail = detail;
      renderLiveStatus();
    }

    return {
      allowanceImpactText,
      allowanceWindowText,
      renderLiveStatus,
      rowAllowanceImpact,
      updateAllowanceImpact,
      updateAllowanceSourceLine,
      updateLiveStatus,
      updateParserDiagnosticsLine,
      updatePricingSourceLine,
      updatePrivacyModeLine,
    };
  }

  window.CodexUsageDashboardStatus = { create: createDashboardStatus };
})();
