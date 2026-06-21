(() => {
  function createSnapshotRenderer(deps) {
    const {
      escapeHtml,
      formatTimestamp,
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
      { key: 'fileReads', title: 'File Reads', path: '/api/diagnostics/file-reads', refreshPath: '/api/diagnostics/file-reads/refresh' },
      { key: 'readProductivity', title: 'Read Productivity', path: '/api/diagnostics/read-productivity', refreshPath: '/api/diagnostics/read-productivity/refresh' },
      { key: 'concentration', title: 'Concentration', path: '/api/diagnostics/concentration', refreshPath: '/api/diagnostics/concentration/refresh' },
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
      return `
        <div class="diagnostics-snapshot-grid">
          ${sections.map(section => renderPanel(section, payloads[section.key], loading)).join('')}
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
      if (key === 'fileReads') return renderFileReads(payload);
      if (key === 'readProductivity') return renderReadProductivity(payload);
      if (key === 'concentration') return renderConcentration(payload);
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
          <summary>${escapeHtml(label)}</summary>
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
      const head = headers.map(header => `<th>${escapeHtml(header)}</th>`).join('');
      const body = rows.map(row => `
        <tr>${row.map((cell, index) => `<td${cellNumeric(cell, index) ? ' class="num"' : ''}>${cellHtml(cell)}</td>`).join('')}</tr>
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

    function cellHtml(value) {
      if (value === null || value === undefined || value === '') return '';
      if (typeof value === 'object' && value.html) return value.html;
      return escapeHtml(String(value));
    }

    function cellNumeric(value, index) {
      if (index === 0) return false;
      if (typeof value === 'object' && value && value.numeric === false) return false;
      return true;
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
