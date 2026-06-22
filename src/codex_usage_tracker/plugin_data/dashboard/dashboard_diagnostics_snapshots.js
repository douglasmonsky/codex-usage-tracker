(() => {
  function createSnapshotRenderer(deps) {
    const {
      escapeHtml,
      formatTimestamp,
      moneyText: sharedMoneyText,
      number,
      pct,
      renderState,
      rowInvestigatorLink,
      tokenText,
    } = deps;

    const sections = [
      { key: 'overview', title: 'Overview', path: '/api/diagnostics/overview', refreshPath: '/api/diagnostics/overview/refresh' },
      { key: 'toolOutput', title: 'Tool Output', path: '/api/diagnostics/tool-output', refreshPath: '/api/diagnostics/tool-output/refresh' },
      { key: 'commands', title: 'Commands', path: '/api/diagnostics/commands', refreshPath: '/api/diagnostics/commands/refresh' },
      { key: 'gitInteractions', title: 'Git Interactions', path: '/api/diagnostics/git-interactions', refreshPath: '/api/diagnostics/git-interactions/refresh' },
      { key: 'fileReads', title: 'File Reads', path: '/api/diagnostics/file-reads', refreshPath: '/api/diagnostics/file-reads/refresh' },
      { key: 'fileModifications', title: 'File Modifications', path: '/api/diagnostics/file-modifications', refreshPath: '/api/diagnostics/file-modifications/refresh' },
      { key: 'readProductivity', title: 'Read Productivity', path: '/api/diagnostics/read-productivity', refreshPath: '/api/diagnostics/read-productivity/refresh' },
      { key: 'concentration', title: 'Concentration', path: '/api/diagnostics/concentration', refreshPath: '/api/diagnostics/concentration/refresh' },
      { key: 'usageDrain', title: 'Usage Drain', path: '/api/diagnostics/usage-drain', refreshPath: '/api/diagnostics/usage-drain/refresh' },
    ];

    function renderToolbar({ loading, payloads, refreshStatus, refreshError }) {
      const latest = latestComputed(payloads);
      const scope = historyScope(payloads);
      const statusText = refreshStatus === 'refreshing'
        ? 'Refreshing diagnostics...'
        : refreshStatus === 'error'
          ? `Refresh failed: ${refreshError}`
          : latest
            ? `Last computed ${formatTimestamp(latest)}`
            : loading
              ? 'Loading stored snapshots...'
              : 'No stored snapshots';
      return `
        <div class="diagnostics-toolbar">
          <div>
            <strong>Diagnostics</strong>
            <span>${escapeHtml(`${statusText}${scope ? ` · ${scope}` : ''}`)}</span>
          </div>
          <button class="toolbar-button" type="button" data-diagnostics-refresh ${refreshStatus === 'refreshing' ? 'disabled' : ''}>
            ${escapeHtml(refreshStatus === 'refreshing' ? 'Refreshing...' : 'Refresh diagnostics')}
          </button>
        </div>
      `;
    }

    function renderPanels({ loading, payloads }) {
      const featuredUsageDrain = renderFeaturedUsageDrain(payloads.usageDrain);
      return `
        ${featuredUsageDrain}
        <div class="diagnostics-snapshot-grid">
          ${sections.map(section => renderPanel(section, payloads[section.key], loading)).join('')}
        </div>
      `;
    }

    function renderFeaturedUsageDrain(payload) {
      if (!payload || payload.status !== 'ready') return '';
      const timeSeries = payload?.time_series || {};
      const charts = [];
      if (Array.isArray(timeSeries.visible_usage?.points) && timeSeries.visible_usage.points.length) {
        charts.push(renderVisibleUsageChart(timeSeries.visible_usage));
      }
      if (Array.isArray(timeSeries.weekly_credit_projection?.points) && timeSeries.weekly_credit_projection.points.length) {
        charts.push(renderWeeklyProjectionChart(timeSeries.weekly_credit_projection));
      }
      if (!charts.length) return '';
      return `
        <div class="diagnostics-featured-charts" data-diagnostics-featured="usage-drain">
          ${charts.join('')}
        </div>
      `;
    }

    function renderPanel(section, payload, loading) {
      const meta = snapshotMeta(payload);
      const state = snapshotState(payload, loading);
      const body = state ? renderState(state) : renderBody(section.key, payload);
      return `
        <div class="diagnostics-section diagnostics-snapshot-panel" data-diagnostics-snapshot="${escapeHtml(section.key)}">
          <div class="diagnostics-section-header">
            <div>
              <h3>${escapeHtml(section.title)}</h3>
              <p>${escapeHtml(meta)}</p>
            </div>
            <span>${escapeHtml(snapshotBadge(payload, loading))}</span>
          </div>
          ${body}
        </div>
      `;
    }

    function renderBody(key, payload) {
      if (key === 'overview') return renderOverview(payload);
      if (key === 'toolOutput') return renderToolOutput(payload);
      if (key === 'commands') return renderCommands(payload);
      if (key === 'gitInteractions') return renderGitInteractions(payload);
      if (key === 'fileReads') return renderFileReads(payload);
      if (key === 'fileModifications') return renderFileModifications(payload);
      if (key === 'readProductivity') return renderReadProductivity(payload);
      if (key === 'concentration') return renderConcentration(payload);
      if (key === 'usageDrain') return renderUsageDrain(payload);
      return renderState('No renderer for this diagnostic section.');
    }

    function renderOverview(payload) {
      const overview = payload?.overview || {};
      return renderKeyValueTable([
        ['Usage rows', tokenText(overview.usage_rows)],
        ['Total tokens', tokenText(overview.total_tokens)],
        ['Cached input', tokenText(overview.cached_input_tokens)],
        ['Uncached input', tokenText(overview.uncached_input_tokens)],
        ['Cache ratio', pct(overview.cache_ratio)],
        ['Diagnostic facts', tokenText(overview.diagnostic_fact_rows)],
      ]);
    }

    function renderToolOutput(payload) {
      const summary = payload?.summary || {};
      const functions = Array.isArray(payload?.functions) ? payload.functions.slice(0, 8) : [];
      return `
        ${renderKeyValueTable([
          ['Function calls', tokenText(summary.function_calls)],
          ['Function outputs', tokenText(summary.function_outputs)],
          ['With token count', tokenText(summary.outputs_with_original_token_count)],
          ['Missing token count', tokenText(summary.outputs_missing_original_token_count)],
          ['Original tokens', tokenText(summary.original_token_sum)],
        ])}
        ${renderSimpleTable(
          ['Function', 'Calls', 'Original tokens'],
          functions.map(row => [row.function, tokenText(row.calls), tokenText(row.original_token_sum)]),
          'No function output rows in this snapshot.',
        )}
      `;
    }

    function renderCommands(payload) {
      const commands = Array.isArray(payload?.commands) ? payload.commands.slice(0, 10) : [];
      return renderSimpleTable(
        ['Root', 'Total', 'Children'],
        commands.map(row => [
          row.root,
          tokenText(row.total),
          { html: renderCommandChildren(row.children), numeric: false },
        ]),
        'No command rows in this snapshot.',
      );
    }

    function renderCommandChildren(children) {
      const rows = Array.isArray(children) ? children : [];
      if (!rows.length) {
        return `<span class="diagnostics-muted">${escapeHtml('<none>')}</span>`;
      }
      const childCount = rows.length;
      const label = `${tokenText(childCount)} ${childCount === 1 ? 'child' : 'children'}`;
      return `
        <details class="diagnostics-command-children">
          <summary>
            <span class="diagnostics-command-toggle-icon" aria-hidden="true"></span>
            <span class="diagnostics-command-toggle-closed">${escapeHtml(`Show all ${label}`)}</span>
            <span class="diagnostics-command-toggle-open">${escapeHtml(`Hide ${label}`)}</span>
          </summary>
          <ul>
            ${rows.map(child => `
              <li>
                <span>${escapeHtml(child.child || '<child>')}</span>
                <b>${tokenText(child.count)}</b>
              </li>
            `).join('')}
          </ul>
        </details>
      `;
    }

    function renderGitInteractions(payload) {
      const summary = payload?.summary || {};
      const interactions = Array.isArray(payload?.interactions) ? payload.interactions.slice(0, 10) : [];
      const categories = Array.isArray(payload?.categories) ? payload.categories.slice(0, 8) : [];
      return `
        ${renderKeyValueTable([
          ['Git/GitHub calls', tokenText(summary.git_shell_calls)],
          ['Git commands', tokenText(summary.git_command_calls)],
          ['GitHub CLI commands', tokenText(summary.github_cli_calls)],
          ['With token count', tokenText(summary.interactions_with_original_token_count)],
          ['Missing token count', tokenText(summary.interactions_missing_original_token_count)],
          ['Original tokens', tokenText(summary.original_token_sum)],
        ])}
        ${renderSimpleTable(
          ['Tool', 'Operation', 'Category', 'Calls', 'Original tokens'],
          interactions.map(row => [
            row.root,
            row.operation,
            humanizeMetric(row.category),
            tokenText(row.calls),
            tokenText(row.original_token_sum),
          ]),
          'No Git interaction rows in this snapshot.',
        )}
        ${renderSimpleTable(
          ['Category', 'Count'],
          categories.map(row => [humanizeMetric(row.category), tokenText(row.count)]),
          'No Git interaction categories in this snapshot.',
        )}
      `;
    }

    function renderFileReads(payload) {
      const byReader = Array.isArray(payload?.by_reader) ? payload.by_reader.slice(0, 8) : [];
      const paths = Array.isArray(payload?.top_paths) ? payload.top_paths.slice(0, 8) : [];
      return `
        ${renderSimpleTable(
          ['Reader', 'Reads', 'Allocated tokens'],
          byReader.map(row => [row.reader, tokenText(row.read_events), tokenText(row.allocated_output_token_sum)]),
          'No file-read rows in this snapshot.',
        )}
        ${renderSimpleTable(
          ['Path label', 'Reads', 'Allocated tokens'],
          paths.map(row => [pathLabel(row), tokenText(row.read_events), tokenText(row.allocated_output_token_sum)]),
          'No path rows in this snapshot.',
        )}
      `;
    }

    function renderFileModifications(payload) {
      const summary = payload?.summary || {};
      const paths = Array.isArray(payload?.top_paths) ? payload.top_paths.slice(0, 8) : [];
      const extensions = Array.isArray(payload?.by_extension) ? payload.by_extension.slice(0, 8) : [];
      return `
        ${renderKeyValueTable([
          ['Modification events', tokenText(summary.modification_events)],
          ['Modified path events', tokenText(summary.modified_path_events)],
          ['Unique paths modified', tokenText(summary.unique_paths_modified)],
          ['Largest event path count', tokenText(summary.largest_event_path_count)],
        ])}
        ${renderSimpleTable(
          ['Path label', 'Modifications'],
          paths.map(row => [pathLabel(row), tokenText(row.modification_events)]),
          'No modified path rows in this snapshot.',
        )}
        ${renderSimpleTable(
          ['Extension', 'Count'],
          extensions.map(row => [row.extension, tokenText(row.count)]),
          'No file-extension rows in this snapshot.',
        )}
      `;
    }

    function renderReadProductivity(payload) {
      const byReader = Array.isArray(payload?.by_reader) ? payload.by_reader.slice(0, 8) : [];
      const paths = Array.isArray(payload?.top_modified_paths) ? payload.top_modified_paths.slice(0, 8) : [];
      return `
        ${renderSimpleTable(
          ['Reader', 'Reads', 'Modified later', 'Rate'],
          byReader.map(row => [
            row.reader,
            tokenText(row.read_events),
            tokenText(row.read_events_modified_later),
            pct(row.read_events_modified_later_pct),
          ]),
          'No read-productivity rows in this snapshot.',
        )}
        ${renderSimpleTable(
          ['Path label', 'Modified later', 'Rate'],
          paths.map(row => [
            pathLabel(row),
            tokenText(row.read_events_modified_later),
            pct(row.read_events_modified_later_pct),
          ]),
          'No modified path rows in this snapshot.',
        )}
      `;
    }

    function renderConcentration(payload) {
      const metrics = Array.isArray(payload?.metrics) ? payload.metrics : [];
      const impacts = Array.isArray(payload?.largest_impact_rows) ? payload.largest_impact_rows.slice(0, 8) : [];
      return `
        ${renderSimpleTable(
          ['Metric', 'Share'],
          metrics.filter(row => row.top_n === 1 || row.top_n === 3 || row.top_n === 5)
            .map(row => [concentrationMetricLabel(row), pct(row.share)]),
          'No concentration metrics in this snapshot.',
        )}
        ${renderSimpleTable(
          ['Dimension', 'Label', 'Share', 'Largest'],
          impacts.map(row => [
            concentrationDimensionLabel(row.dimension),
            row.label,
            pct(row.share),
            row.largest_record_id ? { html: rowInvestigatorLink({ record_id: row.largest_record_id }, tokenText(row.largest_call_tokens), true) } : tokenText(row.largest_call_tokens),
          ]),
          'No largest-impact rows in this snapshot.',
        )}
      `;
    }

    function renderUsageDrain(payload) {
      const summary = payload?.summary || {};
      const curves = payload?.thread_cost_curves || {};
      const timeSeries = payload?.time_series || {};
      const highlights = payload?.model_highlights || {};
      const threads = Array.isArray(curves?.threads) ? curves.threads.slice(0, 12) : [];
      return `
        ${renderKeyValueTable([
          ['Usage rows', tokenText(summary.usage_rows)],
          ['Positive usage spans', tokenText(summary.positive_usage_spans)],
          ['Estimated cost', moneyText(summary.estimated_cost_usd)],
          ['Usage credits', numberText(summary.usage_credits)],
          ['Top thread cost share', pct(summary.top_thread_cost_share)],
          ['Best predictive model', summary.best_predictive_model || 'n/a'],
        ])}
        ${renderUsageDrainCostChart(threads)}
        ${renderSimpleTable(
          ['Thread', 'Calls', 'Cost', 'Avg/call', 'Shape', 'First half', 'Largest call'],
          threads.map(row => [
            row.thread,
            tokenText(row.call_count),
            moneyText(row.estimated_cost_usd),
            moneyText(row.avg_cost_usd),
            humanizeMetric(row.shape),
            pct(row.first_half_cost_share),
            pct(row.largest_call_cost_share),
          ]),
          'No thread cost curves in this snapshot.',
        )}
        ${renderPredictiveHighlights(highlights)}
        ${renderAllowanceBreakpoints(highlights.allowance_breakpoints)}
      `;
    }

    function renderVisibleUsageChart(series) {
      const points = Array.isArray(series?.points) ? series.points : [];
      if (!points.length) return renderState('No visible usage time-series points in this snapshot.');
      const width = 760;
      const height = 260;
      const margin = { top: 20, right: 28, bottom: 42, left: 66 };
      const innerWidth = width - margin.left - margin.right;
      const innerHeight = height - margin.top - margin.bottom;
      const timed = points
        .map(point => {
          const used = Number(point.weekly_used_percent);
          return {
            ...point,
            ts: Date.parse(point.timestamp || ''),
            weekly_remaining_percent: Number.isFinite(used) ? Math.max(0, Math.min(100, 100 - used)) : null,
          };
        })
        .filter(point => (
          Number.isFinite(point.ts)
          && point.weekly_remaining_percent !== null
          && point.weekly_remaining_percent !== undefined
        ))
        .sort((left, right) => left.ts - right.ts);
      if (!timed.length) return renderState('No timestamped visible usage points in this snapshot.');
      const minX = Math.min(...timed.map(point => point.ts));
      const maxX = Math.max(...timed.map(point => point.ts));
      const spanX = Math.max(maxX - minX, 1);
      const x = value => margin.left + ((value - minX) / spanX) * innerWidth;
      const y = value => margin.top + innerHeight - (Number(value || 0) / 100) * innerHeight;
      const lineFor = (field, color) => segmentedUsageLines(timed, field, color, x, y);
      const yTicks = [0, 25, 50, 75, 100];
      const xTicks = timeChartTicks(timed, 10);
      return `
        <div class="diagnostics-chart-card">
          <div class="diagnostics-chart-title">
            <strong>Weekly usage over time</strong>
            <span>remaining weekly allowance from indexed calls</span>
          </div>
          <svg class="diagnostics-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Weekly usage remaining over time">
            <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerHeight}" class="diagnostics-axis"></line>
            <line x1="${margin.left}" y1="${margin.top + innerHeight}" x2="${margin.left + innerWidth}" y2="${margin.top + innerHeight}" class="diagnostics-axis"></line>
            ${yTicks.map(tick => `
              <line x1="${margin.left}" y1="${y(tick).toFixed(1)}" x2="${margin.left + innerWidth}" y2="${y(tick).toFixed(1)}" class="diagnostics-gridline"></line>
              <text x="${margin.left - 10}" y="${y(tick).toFixed(1)}" text-anchor="end" dominant-baseline="middle">${escapeHtml(pct(tick / 100))}</text>
            `).join('')}
            ${xTicks.map((point, index) => `
              <line x1="${x(point.ts).toFixed(1)}" y1="${margin.top + innerHeight}" x2="${x(point.ts).toFixed(1)}" y2="${margin.top + innerHeight + 5}" class="diagnostics-axis"></line>
              <text x="${x(point.ts).toFixed(1)}" y="${margin.top + innerHeight + 24}" text-anchor="${tickTextAnchor(index, xTicks.length)}">${escapeHtml(shortDate(point.timestamp))}</text>
            `).join('')}
            ${lineFor('weekly_remaining_percent', '#059669')}
            <text x="${margin.left + innerWidth / 2}" y="${height - 8}" text-anchor="middle">Time</text>
            <text x="18" y="${margin.top + innerHeight / 2}" transform="rotate(-90 18 ${margin.top + innerHeight / 2})" text-anchor="middle">Usage remaining</text>
          </svg>
          <div class="diagnostics-chart-legend">
            <span><i class="diagnostics-series-1"></i>Weekly remaining</span>
          </div>
        </div>
      `;
    }

    function renderWeeklyProjectionChart(projection) {
      const points = Array.isArray(projection?.points) ? projection.points : [];
      if (!points.length) return renderState('No weekly projection points in this snapshot.');
      const chartPoints = weeklyProjectionChartPoints(points);
      if (!chartPoints.length) return renderState('No known-plan weekly projection points in this snapshot.');
      const chartSubtitle = weeklyProjectionSubtitle(chartPoints);
      const layout = weeklyProjectionChartLayout(chartPoints.length);
      const width = layout.width;
      const height = 300;
      const margin = { top: 20, right: 28, bottom: 46, left: 92 };
      const innerWidth = width - margin.left - margin.right;
      const innerHeight = height - margin.top - margin.bottom;
      const yTicks = niceAxisTicks(Math.max(1, ...chartPoints.map(point => Number(point.ci_high || point.projected_weekly_credits || 0))));
      const maxY = yTicks[yTicks.length - 1] || 1;
      const x = index => margin.left + (chartPoints.length === 1 ? innerWidth / 2 : (index / (chartPoints.length - 1)) * innerWidth);
      const y = value => {
        const numeric = Math.max(0, Math.min(maxY, Number(value || 0)));
        return margin.top + innerHeight - (numeric / maxY) * innerHeight;
      };
      const line = chartPoints
        .map((point, index) => `${x(index).toFixed(1)},${y(point.projected_weekly_credits).toFixed(1)}`)
        .join(' ');
      const colors = diagnosticsChartColors();
      const series = weeklyProjectionPlanSeries(chartPoints);
      const colorForPlan = key => colors[Math.max(series.findIndex(group => group.key === key), 0) % colors.length];
      const trendLines = weeklyProjectionTrendLines(series, x, y, colorForPlan);
      const hasTrendLines = trendLines.trim().length > 0;
      const seriesLines = series.map(group => {
        if (group.points.length < 2) return '';
        const pointText = group.points
          .map(item => `${x(item.index).toFixed(1)},${y(item.point.projected_weekly_credits).toFixed(1)}`)
          .join(' ');
        return `<polyline points="${escapeHtml(pointText)}" fill="none" stroke="${colorForPlan(group.key)}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></polyline>`;
      }).join('');
      const markers = chartPoints.map((point, index) => `
        <circle cx="${x(index).toFixed(1)}" cy="${y(point.projected_weekly_credits).toFixed(1)}" r="3.6" fill="${colorForPlan(weeklyProjectionPlanKey(point))}" stroke="#ffffff" stroke-width="1.4"></circle>
      `).join('');
      const bars = chartPoints.map((point, index) => {
        if (point.ci_low === null || point.ci_low === undefined || point.ci_high === null || point.ci_high === undefined) {
          return '';
        }
        const center = x(index);
        const low = y(point.ci_low);
        const high = y(point.ci_high);
        return `
          <line x1="${center.toFixed(1)}" y1="${high.toFixed(1)}" x2="${center.toFixed(1)}" y2="${low.toFixed(1)}" class="diagnostics-confidence-bar"></line>
          <line x1="${(center - 5).toFixed(1)}" y1="${high.toFixed(1)}" x2="${(center + 5).toFixed(1)}" y2="${high.toFixed(1)}" class="diagnostics-confidence-bar"></line>
          <line x1="${(center - 5).toFixed(1)}" y1="${low.toFixed(1)}" x2="${(center + 5).toFixed(1)}" y2="${low.toFixed(1)}" class="diagnostics-confidence-bar"></line>
        `;
      }).join('');
      const xTicks = indexedChartTicks(chartPoints, layout.tickLimit);
      return `
        <div class="diagnostics-chart-card">
          <div class="${chartWidthClass('diagnostics-chart-title', layout.classSuffix)}">
            <strong>Projected weekly credits over time</strong>
            <span>${escapeHtml(chartSubtitle)}</span>
          </div>
          <svg class="${chartWidthClass('diagnostics-line-chart', layout.classSuffix)}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Projected weekly credits over time">
            <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerHeight}" class="diagnostics-axis"></line>
            <line x1="${margin.left}" y1="${margin.top + innerHeight}" x2="${margin.left + innerWidth}" y2="${margin.top + innerHeight}" class="diagnostics-axis"></line>
            ${yTicks.map(tick => `
              <line x1="${margin.left}" y1="${y(tick).toFixed(1)}" x2="${margin.left + innerWidth}" y2="${y(tick).toFixed(1)}" class="diagnostics-gridline"></line>
              <text x="${margin.left - 10}" y="${y(tick).toFixed(1)}" text-anchor="end" dominant-baseline="middle">${escapeHtml(numberText(tick))}</text>
            `).join('')}
            ${xTicks.map(({ point, index }) => `
              <line x1="${x(index).toFixed(1)}" y1="${margin.top + innerHeight}" x2="${x(index).toFixed(1)}" y2="${margin.top + innerHeight + 5}" class="diagnostics-axis"></line>
              <text x="${x(index).toFixed(1)}" y="${margin.top + innerHeight + 24}" text-anchor="${tickTextAnchor(index, chartPoints.length)}">${escapeHtml(weeklyProjectionTickLabel(point))}</text>
            `).join('')}
            ${bars}
            ${series.length > 1 ? '' : `<polyline points="${escapeHtml(line)}" fill="none" stroke="${colors[0]}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></polyline>`}
            ${series.length > 1 ? seriesLines : ''}
            ${markers}
            ${trendLines}
            <text x="${margin.left + innerWidth / 2}" y="${height - 8}" text-anchor="middle">Weekly reset window</text>
            <text x="18" y="${margin.top + innerHeight / 2}" transform="rotate(-90 18 ${margin.top + innerHeight / 2})" text-anchor="middle">Projected credits</text>
          </svg>
          <div class="${chartWidthClass('diagnostics-chart-legend', layout.classSuffix)}">
            ${weeklyProjectionLegend(series)}
            ${hasTrendLines ? '<span><i class="diagnostics-trend-swatch"></i>Trend per plan</span>' : ''}
          </div>
        </div>
        ${renderSimpleTable(
          ['Week', 'Plan', 'Observed %', 'Credits', 'Projected/week', 'Confidence'],
          chartPoints.slice(-6).map(point => [
            point.label,
            humanizeMetric(point.rate_limit_plan_type || 'unknown'),
            pct(Number(point.observed_usage_delta_percent || 0) / 100),
            numberText(point.observed_standard_usage_credits),
            numberText(point.projected_weekly_credits),
            humanizeMetric(point.confidence),
          ]),
          'No weekly projection points in this snapshot.',
        )}
      `;
    }

    function weeklyProjectionChartLayout(pointCount) {
      const count = Math.max(1, Number(pointCount || 1));
      if (count > 40) return { width: 2200, classSuffix: 'xwide', tickLimit: 14 };
      if (count > 24) return { width: 1520, classSuffix: 'wide', tickLimit: 12 };
      if (count > 12) return { width: 1040, classSuffix: 'medium', tickLimit: 10 };
      return { width: 760, classSuffix: '', tickLimit: Math.min(8, count) };
    }

    function chartWidthClass(baseClass, suffix) {
      return suffix ? `${baseClass} ${baseClass}-${suffix}` : baseClass;
    }

    function weeklyProjectionChartPoints(points) {
      const knownPlanPoints = points.filter(point => isKnownProjectionPlan(point));
      return knownPlanPoints.sort((left, right) => {
        const leftTime = Date.parse(left.start_event_timestamp || left.end_event_timestamp || '');
        const rightTime = Date.parse(right.start_event_timestamp || right.end_event_timestamp || '');
        if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) return leftTime - rightTime;
        return String(left.label || '').localeCompare(String(right.label || ''));
      });
    }

    function isKnownProjectionPlan(point) {
      const key = weeklyProjectionPlanKey(point);
      return key !== 'unknown' && key !== 'missing';
    }

    function weeklyProjectionSubtitle(points) {
      const plans = Array.from(new Set(points.map(point => point.rate_limit_plan_type || 'unknown')));
      if (plans.length === 1) {
        return `${humanizeMetric(plans[0])} plan windows with descriptive confidence bars`;
      }
      return `${tokenText(plans.length)} plan types shown; trend requires 3+ medium/high windows per plan`;
    }

    function weeklyProjectionTickLabel(point) {
      const label = point.label || shortDate(point.end_event_timestamp);
      return String(label || '').replace(/^Reset\s+/i, '');
    }

    function weeklyProjectionPlanKey(point) {
      return point.rate_limit_plan_type || 'unknown';
    }

    function weeklyProjectionPlanSeries(points) {
      const groups = new Map();
      points.forEach((point, index) => {
        const key = weeklyProjectionPlanKey(point);
        if (!groups.has(key)) {
          groups.set(key, { key, label: humanizeMetric(key), points: [] });
        }
        groups.get(key).points.push({ point, index });
      });
      return Array.from(groups.values());
    }

    function weeklyProjectionLegend(series) {
      return series.map((group, index) => `
        <span><i class="diagnostics-series-${index % diagnosticsChartColors().length}"></i>${escapeHtml(group.label)}</span>
      `).join('');
    }

    function weeklyProjectionTrendLines(series, x, y, colorForPlan) {
      return series.map(group => weeklyProjectionTrendLine(group, x, y, colorForPlan(group.key))).join('');
    }

    function weeklyProjectionTrendLine(group, x, y, color) {
      const trendPoints = group.points
        .filter(item => item.point.confidence === 'medium' || item.point.confidence === 'high');
      if (trendPoints.length < 3) return '';
      const values = trendPoints.map(item => Number(item.point.projected_weekly_credits || 0));
      const indexes = trendPoints.map(item => item.index);
      const xMean = indexes.reduce((total, value) => total + value, 0) / indexes.length;
      const yMean = values.reduce((total, value) => total + value, 0) / values.length;
      const denom = indexes.reduce((total, index) => total + Math.pow(index - xMean, 2), 0);
      if (!denom) return '';
      const slope = values.reduce((total, value, offset) => total + ((indexes[offset] - xMean) * (value - yMean)), 0) / denom;
      const intercept = yMean - slope * xMean;
      const firstIndex = indexes[0];
      const lastIndex = indexes[indexes.length - 1];
      const first = intercept + slope * firstIndex;
      const last = intercept + slope * lastIndex;
      return `<line x1="${x(firstIndex).toFixed(1)}" y1="${y(first).toFixed(1)}" x2="${x(lastIndex).toFixed(1)}" y2="${y(last).toFixed(1)}" class="diagnostics-trend-line" stroke="${color}"></line>`;
    }

    function diagnosticsChartColors() {
      return ['#2563eb', '#059669', '#dc2626', '#7c3aed', '#ea580c', '#0891b2', '#be123c', '#4d7c0f', '#0f766e', '#9333ea', '#b45309', '#475569'];
    }

    function niceAxisTicks(maxValue, maxTicks = 5) {
      const numeric = Math.max(1, Number(maxValue || 1));
      const step = niceAxisStep(numeric / Math.max(maxTicks - 1, 1));
      const maxTick = Math.ceil(numeric / step) * step;
      const ticks = [];
      for (let tick = 0; tick <= maxTick + (step / 2); tick += step) {
        ticks.push(tick);
      }
      return ticks.length >= 2 ? ticks : [0, maxTick || 1];
    }

    function niceAxisStep(rawStep) {
      const magnitude = Math.pow(10, Math.floor(Math.log10(Math.max(rawStep, 1))));
      const normalized = rawStep / magnitude;
      if (normalized <= 1) return magnitude;
      if (normalized <= 2) return 2 * magnitude;
      if (normalized <= 5) return 5 * magnitude;
      return 10 * magnitude;
    }

    function tickTextAnchor(index, total) {
      if (index === 0) return 'start';
      if (index === total - 1) return 'end';
      return 'middle';
    }

    function timeChartTicks(points, maxTicks) {
      if (!points.length || maxTicks <= 0) return [];
      if (points.length <= maxTicks) return points;
      const minTs = Math.min(...points.map(point => point.ts));
      const maxTs = Math.max(...points.map(point => point.ts));
      const span = Math.max(maxTs - minTs, 1);
      const ticks = [];
      for (let tick = 0; tick < maxTicks; tick += 1) {
        const target = minTs + (span * tick / Math.max(maxTicks - 1, 1));
        ticks.push({ ts: target, timestamp: new Date(target).toISOString() });
      }
      return ticks;
    }

    function segmentedUsageLines(points, field, color, x, y) {
      const segments = [];
      let current = [];
      let previousValue = null;
      points.forEach(point => {
        const value = point[field];
        if (value === null || value === undefined) {
          if (current.length) segments.push(current);
          current = [];
          previousValue = null;
          return;
        }
        const numeric = Number(value);
        if (previousValue !== null && numeric > previousValue + 0.001) {
          if (current.length) segments.push(current);
          current = [];
        }
        current.push(point);
        previousValue = numeric;
      });
      if (current.length) segments.push(current);
      return segments
        .filter(segment => segment.length >= 2)
        .map(segment => {
          const line = segment
            .map(point => `${x(point.ts).toFixed(1)},${y(point[field]).toFixed(1)}`)
            .join(' ');
          return `<polyline points="${escapeHtml(line)}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></polyline>`;
        })
        .join('');
    }

    function indexedChartTicks(points, maxTicks) {
      if (!points.length || maxTicks <= 0) return [];
      if (points.length <= maxTicks) {
        return points.map((point, index) => ({ point, index }));
      }
      const lastIndex = points.length - 1;
      const indexes = new Set();
      for (let tick = 0; tick < maxTicks; tick += 1) {
        indexes.add(Math.round(tick * lastIndex / Math.max(maxTicks - 1, 1)));
      }
      indexes.add(0);
      indexes.add(lastIndex);
      return Array.from(indexes)
        .sort((left, right) => left - right)
        .map(index => ({ point: points[index], index }));
    }

    function renderUsageDrainCostChart(threads) {
      if (!threads.length) return renderState('No thread cost curves in this snapshot.');
      const width = 760;
      const height = 300;
      const margin = { top: 20, right: 28, bottom: 46, left: 72 };
      const innerWidth = width - margin.left - margin.right;
      const innerHeight = height - margin.top - margin.bottom;
      const maxX = Math.max(1, ...threads.map(thread => Number(thread.call_count || 0)));
      const maxY = Math.max(0.01, ...threads.map(thread => Number(thread.estimated_cost_usd || 0)));
      const colors = ['#2563eb', '#059669', '#dc2626', '#7c3aed', '#ea580c', '#0891b2', '#be123c', '#4d7c0f', '#0f766e', '#9333ea', '#b45309', '#475569'];
      const x = value => margin.left + (Number(value || 0) / maxX) * innerWidth;
      const y = value => margin.top + innerHeight - (Number(value || 0) / maxY) * innerHeight;
      const xTicks = [0, Math.round(maxX / 2), maxX];
      const yTicks = [0, maxY / 2, maxY];
      const lines = threads.map((thread, index) => {
        const points = Array.isArray(thread.points) ? thread.points : [];
        const pointText = points.map(point => `${x(point.call_index).toFixed(1)},${y(point.cumulative_cost_usd).toFixed(1)}`).join(' ');
        if (!pointText) return '';
        return `<polyline points="${escapeHtml(pointText)}" fill="none" stroke="${colors[index % colors.length]}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></polyline>`;
      }).join('');
      const legend = threads.slice(0, 8).map((thread, index) => `
        <span><i class="diagnostics-series-${index % colors.length}"></i>${escapeHtml(truncateText(thread.thread, 34))}</span>
      `).join('');
      return `
        <div class="diagnostics-chart-card">
          <div class="diagnostics-chart-title">
            <strong>Cumulative estimated cost by thread</strong>
            <span>calls on x-axis, cumulative cost on y-axis</span>
          </div>
          <svg class="diagnostics-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative estimated cost by thread">
            <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerHeight}" class="diagnostics-axis"></line>
            <line x1="${margin.left}" y1="${margin.top + innerHeight}" x2="${margin.left + innerWidth}" y2="${margin.top + innerHeight}" class="diagnostics-axis"></line>
            ${yTicks.map(tick => `
              <line x1="${margin.left}" y1="${y(tick).toFixed(1)}" x2="${margin.left + innerWidth}" y2="${y(tick).toFixed(1)}" class="diagnostics-gridline"></line>
              <text x="${margin.left - 10}" y="${y(tick).toFixed(1)}" text-anchor="end" dominant-baseline="middle">${escapeHtml(moneyText(tick))}</text>
            `).join('')}
            ${xTicks.map(tick => `
              <line x1="${x(tick).toFixed(1)}" y1="${margin.top + innerHeight}" x2="${x(tick).toFixed(1)}" y2="${margin.top + innerHeight + 5}" class="diagnostics-axis"></line>
              <text x="${x(tick).toFixed(1)}" y="${margin.top + innerHeight + 24}" text-anchor="middle">${escapeHtml(tokenText(tick))}</text>
            `).join('')}
            ${lines}
            <text x="${margin.left + innerWidth / 2}" y="${height - 8}" text-anchor="middle">Call index within thread</text>
            <text x="18" y="${margin.top + innerHeight / 2}" transform="rotate(-90 18 ${margin.top + innerHeight / 2})" text-anchor="middle">Cumulative cost</text>
          </svg>
          <div class="diagnostics-chart-legend">${legend}</div>
        </div>
      `;
    }

    function renderPredictiveHighlights(highlights) {
      const predictive = highlights?.predictive_modeling || {};
      const best = predictive.best_mae_model || predictive.best_r2_model || {};
      const accounting = highlights?.token_accounting || {};
      return renderSimpleTable(
        ['Predictive metric', 'Value'],
        [
          ['Best by MAE', predictive.best_by_holdout_mae || 'n/a'],
          ['Best by R2', predictive.best_by_holdout_r2 || 'n/a'],
          ['Best MAE', best.mae === null || best.mae === undefined ? 'n/a' : numberText(best.mae)],
          ['Best R2', best.r2 === null || best.r2 === undefined ? 'n/a' : numberText(best.r2)],
          ['Best Pearson', best.pearson === null || best.pearson === undefined ? 'n/a' : numberText(best.pearson)],
          ['Credit-to-visible-delta R2', numberText(accounting.credits_to_visible_delta?.r2)],
        ],
        'No predictive highlights in this snapshot.',
      );
    }

    function renderAllowanceBreakpoints(breakpoints) {
      const segments = Array.isArray(breakpoints?.segments) ? breakpoints.segments.slice(0, 6) : [];
      return `
        ${renderSimpleTable(
          ['Allowance metric', 'Value'],
          [
            ['Spans', tokenText(breakpoints?.span_count)],
            ['Global credits / 1%', numberText(breakpoints?.global_mean_credits_per_percent)],
            ['Piecewise SSE reduction', pct(breakpoints?.piecewise_sse_reduction_share)],
            ['Global credit-to-delta R2', numberText(breakpoints?.global_credit_to_delta_r2)],
            ['Piecewise credit-to-delta R2', numberText(breakpoints?.piecewise_credit_to_delta_r2)],
          ],
          'No allowance-breakpoint highlights in this snapshot.',
        )}
        ${renderSimpleTable(
          ['Segment', 'Rows', 'Mean credits / 1%', 'R2'],
          segments.map(row => [
            tokenText(row.segment_index),
            tokenText(row.n),
            numberText(row.mean_credits_per_percent),
            numberText(row.credit_to_delta_r2),
          ]),
          'No allowance-breakpoint segments in this snapshot.',
        )}
      `;
    }

    function readoutMetric(label, count) {
      return `<span><b>${number.format(Number(count || 0))}</b>${escapeHtml(label)}</span>`;
    }

    function readyCount(payloads) {
      return sections.filter(section => payloads[section.key]?.status === 'ready').length;
    }

    function latestComputed(payloads) {
      return sections
        .map(section => payloads[section.key]?.snapshot?.computed_at || '')
        .filter(Boolean)
        .sort()
        .pop() || '';
    }

    function historyScope(payloads) {
      const scope = sections
        .map(section => payloads[section.key]?.snapshot?.history_scope || payloads[section.key]?.history_scope || '')
        .find(Boolean);
      return scope ? `history ${scope}` : '';
    }

    function snapshotMeta(payload) {
      const snapshot = payload?.snapshot;
      if (snapshot) {
        const computed = snapshot.computed_at ? formatTimestamp(snapshot.computed_at) : 'unknown time';
        const scope = snapshot.history_scope || 'active';
        const logs = tokenText(snapshot.source_logs_scanned);
        return `last computed ${computed} · history ${scope} · logs scanned ${logs}`;
      }
      if (payload?.history_scope) return `history ${payload.history_scope} · no stored snapshot`;
      return 'no stored snapshot';
    }

    function snapshotBadge(payload, loading) {
      if (loading && !payload) return 'loading';
      if (!payload) return 'empty';
      if (payload.status === 'missing') return 'stale';
      if (payload.status === 'ready') return payload.refreshed ? 'refreshed' : 'stored';
      return payload.status || 'unknown';
    }

    function snapshotState(payload, loading) {
      if (loading && !payload) return 'Loading stored diagnostics...';
      if (!payload) return 'No diagnostic payload returned.';
      if (payload.status === 'missing') return 'No stored snapshot yet. Refresh diagnostics to compute this section.';
      if (payload.status !== 'ready') return `Snapshot status: ${payload.status || 'unknown'}.`;
      return '';
    }

    function renderKeyValueTable(rows) {
      return renderSimpleTable(['Metric', 'Value'], rows, 'No metrics in this snapshot.');
    }

    function renderSimpleTable(headers, rows, emptyMessage) {
      if (!rows.length) return renderState(emptyMessage);
      const numericColumns = headers.map((_, index) => columnNumeric(rows, index));
      const head = headers.map((header, index) => `<th${numericColumns[index] ? ' class="num"' : ''}>${escapeHtml(header)}</th>`).join('');
      const body = rows.map(row => `
        <tr>${row.map((cell, index) => `<td${numericColumns[index] ? ' class="num"' : ''}>${cellHtml(cell)}</td>`).join('')}</tr>
      `).join('');
      return `
        <div class="diagnostics-table-wrap diagnostics-mini-table-wrap">
          <table class="diagnostics-table diagnostics-mini-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    function columnNumeric(rows, index) {
      if (index === 0) return false;
      const values = rows
        .map(row => row[index])
        .filter(value => value !== null && value !== undefined && value !== '');
      if (!values.length) return false;
      return values.every(value => cellNumeric(value));
    }

    function cellHtml(value) {
      if (value === null || value === undefined || value === '') return '';
      if (typeof value === 'object' && value.html) return value.html;
      return escapeHtml(String(value));
    }

    function cellNumeric(value) {
      if (typeof value === 'object' && value) {
        if (value.numeric === true) return true;
        if (value.numeric === false || value.html) return false;
      }
      if (typeof value === 'number') return Number.isFinite(value);
      const text = String(value || '').trim();
      if (!text || text.toLowerCase() === 'n/a') return true;
      return /^[$+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$/.test(text);
    }

    function numberText(value) {
      if (value === null || value === undefined || value === '') return 'n/a';
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return 'n/a';
      return number.format(Math.round(numeric * 1000) / 1000);
    }

    function moneyText(value) {
      if (typeof sharedMoneyText === 'function') return sharedMoneyText(value);
      if (value === null || value === undefined) return 'No price';
      const numeric = Number(value || 0);
      if (numeric > 0 && numeric < 0.01) return `$${numeric.toFixed(4)}`;
      return `$${new Intl.NumberFormat([], {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric)}`;
    }

    function pathLabel(row) {
      const label = row.path_label || 'path';
      const hash = row.path_hash ? ` · ${String(row.path_hash).slice(0, 6)}` : '';
      return `${label}${hash}`;
    }

    function concentrationMetricLabel(row) {
      const topN = Number(row?.top_n || 0);
      const dimension = concentrationDimensionLabel(row?.dimension);
      if (topN > 0 && dimension) return `Top ${topN} ${dimension.toLowerCase()} share`;
      return humanizeMetric(row?.metric || 'metric');
    }

    function concentrationDimensionLabel(value) {
      return {
        source_log: 'Source/session',
        cwd: 'Project/cwd',
        day: 'Day',
      }[value] || humanizeMetric(value || '');
    }

    function humanizeMetric(value) {
      return String(value || '')
        .split('_')
        .filter(Boolean)
        .map(part => part.slice(0, 1).toUpperCase() + part.slice(1))
        .join(' ');
    }

    function truncateText(value, length) {
      const text = String(value || '');
      if (text.length <= length) return text;
      return `${text.slice(0, Math.max(length - 1, 1))}…`;
    }

    function shortDate(value) {
      const date = new Date(value || '');
      if (Number.isNaN(date.getTime())) return '';
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }

    return {
      historyScope,
      latestComputed,
      readoutMetric,
      readyCount,
      renderPanels,
      renderToolbar,
      sections,
    };
  }

  window.CodexUsageDashboardDiagnosticSnapshots = { create: createSnapshotRenderer };
})();
