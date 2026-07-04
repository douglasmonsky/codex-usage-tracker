import type { DiagnosticSnapshotMap, DiagnosticSnapshotPayload } from '../../api/diagnostics';
import type { CallRow, DashboardModel } from '../../api/types';

export function fallbackDiagnosticSnapshots(model: DashboardModel): DiagnosticSnapshotMap {
  const calls = model.calls;
  const totalTokens = calls.reduce((sum, call) => sum + call.totalTokens, 0);
  const inputTokens = calls.reduce((sum, call) => sum + call.input, 0);
  const uncachedInput = calls.reduce((sum, call) => sum + call.uncachedInput, 0);
  const cachedInput = Math.max(inputTokens - uncachedInput, 0);
  const topThreadRows = groupedCalls(calls, call => call.thread)
    .map(group => ({
      dimension: 'thread',
      label: group.label,
      share: totalTokens ? group.totalTokens / totalTokens : 0,
      total_tokens: group.totalTokens,
      usage_rows: group.calls.length,
      largest_record_id: group.largest.id,
      largest_call_tokens: group.largest.totalTokens,
    }))
    .slice(0, 5);

  return {
    overview: fallbackPayload('overview', {
      overview: {
        usage_rows: calls.length,
        total_tokens: totalTokens,
        input_tokens: inputTokens,
        cached_input_tokens: cachedInput,
        uncached_input_tokens: uncachedInput,
        cache_ratio: inputTokens ? cachedInput / inputTokens : 0,
        thread_count: new Set(calls.map(call => call.thread)).size,
        model_count: new Set(calls.map(call => call.model)).size,
      },
    }),
    toolOutput: fallbackPayload('tool-output', {
      summary: {
        function_calls: calls.filter(call => call.tags.length).length,
        function_outputs: calls.length,
        original_token_sum: totalTokens,
      },
      functions: tagRows(calls, call => call.tags),
    }),
    commands: fallbackPayload('commands', {
      summary: {
        shell_function_calls: calls.length,
        command_root_count: new Set(calls.flatMap(call => call.tags)).size,
        missing_command: calls.filter(call => !call.tags.length).length,
      },
    commands: tagRows(calls, call => call.tags).map(item => ({
      root: item.function,
      total: item.calls,
      children: [],
      largest_record_id: item.largest_record_id,
      largest_call_tokens: item.largest_call_tokens,
    })),
  }),
    gitInteractions: fallbackPayload('git-interactions', {
      summary: {
        git_shell_calls: calls.filter(call => call.gitBranch || call.gitRemoteLabel).length,
        git_command_calls: calls.filter(call => call.gitBranch).length,
        github_cli_calls: calls.filter(call => call.gitRemoteLabel === 'github').length,
      },
    interactions: groupedCalls(calls, call => call.gitBranch || 'unknown-branch').map(group => ({
      root: 'git',
      operation: group.label,
      category: 'branch',
      calls: group.calls.length,
      largest_record_id: group.largest.id,
      largest_call_tokens: group.largest.totalTokens,
    })),
  }),
    fileReads: fallbackPayload('file-reads', {
      summary: {
        read_events: calls.filter(call => call.sourceFile).length,
        allocated_output_token_sum: calls.reduce((sum, call) => sum + call.output, 0),
      },
    by_reader: groupedCalls(calls, call => call.projectRelativeCwd || call.cwd || 'project').map(group => ({
      reader: group.label,
      read_events: group.calls.length,
      allocated_output_token_sum: group.calls.reduce((sum, call) => sum + call.output, 0),
      largest_record_id: group.largest.id,
      largest_call_tokens: group.largest.totalTokens,
    })),
  }),
    fileModifications: fallbackPayload('file-modifications', {
      summary: {
        modification_events: calls.filter(call => call.tags.includes('file-heavy') || call.tags.includes('large')).length,
        unique_paths_modified: new Set(calls.map(call => call.projectRelativeCwd || call.sourceFile).filter(Boolean)).size,
        largest_event_path_count: Math.max(...calls.map(call => call.tags.length), 0),
      },
    top_paths: groupedCalls(calls, call => call.projectRelativeCwd || call.sourceFile || 'path').map(group => ({
      path_label: group.label,
      modification_events: group.calls.length,
      largest_record_id: group.largest.id,
      largest_call_tokens: group.largest.totalTokens,
    })),
  }),
    readProductivity: fallbackPayload('read-productivity', {
      summary: {
        read_events: calls.length,
        read_events_modified_later: modifiedLaterCount(calls),
        read_events_modified_later_pct: calls.length ? modifiedLaterCount(calls) / calls.length : 0,
      },
      by_reader: groupedCalls(calls, call => call.projectRelativeCwd || 'project').map(group => {
        const modifiedLater = modifiedLaterCount(group.calls);
      return {
        reader: group.label,
        read_events: group.calls.length,
        read_events_modified_later: modifiedLater,
        read_events_modified_later_pct: group.calls.length ? modifiedLater / group.calls.length : 0,
        largest_record_id: group.largest.id,
        largest_call_tokens: group.largest.totalTokens,
      };
    }),
  }),
    concentration: fallbackPayload('concentration', {
      summary: {
        usage_rows: calls.length,
        top_thread_share: topThreadRows[0]?.share ?? 0,
      },
      dimensions: [
        {
          dimension: 'thread',
          label: 'Thread',
          group_count: topThreadRows.length,
          top_1_share: topThreadRows[0]?.share ?? 0,
          top_rows: topThreadRows,
        },
      ],
    }),
    guidedSummary: fallbackPayload('guided-summary', {
      summary: {
        usage_rows: calls.length,
        total_tokens: totalTokens,
        cache_ratio: inputTokens ? cachedInput / inputTokens : 0,
      },
      drivers: model.findings.map(finding => ({
        title: finding.title,
        label: finding.severity,
        share: finding.share / 100,
        action: finding.summary,
      })),
    }),
    usageDrain: fallbackPayload('usage-drain', {
      summary: {
        usage_rows: calls.length,
        estimated_cost_usd: calls.reduce((sum, call) => sum + call.cost, 0),
        usage_credits: calls.reduce((sum, call) => sum + call.credits, 0),
      },
    thread_cost_curves: {
      threads: groupedCalls(calls, call => call.thread).map(group => ({
        thread: group.label,
        call_count: group.calls.length,
        estimated_cost_usd: group.calls.reduce((sum, call) => sum + call.cost, 0),
        largest_record_id: group.largest.id,
        largest_call_tokens: group.largest.totalTokens,
      })),
    },
  }),
  };
}

function fallbackPayload(section: string, payload: Record<string, unknown>): DiagnosticSnapshotPayload {
  return {
    schema: `react-fallback-${section}`,
    section,
    status: 'fallback',
    refreshed: false,
    raw_context_included: false,
    snapshot: null,
    ...payload,
  };
}

function groupedCalls(calls: CallRow[], keyFor: (call: CallRow) => string) {
  const groups = new Map<string, CallRow[]>();
  for (const call of calls) {
    const key = keyFor(call) || 'unknown';
    groups.set(key, [...(groups.get(key) ?? []), call]);
  }
  return [...groups.entries()]
    .map(([label, groupCalls]) => ({
      label,
      calls: groupCalls,
      totalTokens: groupCalls.reduce((sum, call) => sum + call.totalTokens, 0),
      largest: [...groupCalls].sort((left, right) => right.totalTokens - left.totalTokens)[0],
    }))
    .sort((left, right) => right.totalTokens - left.totalTokens || left.label.localeCompare(right.label));
}

function tagRows(calls: CallRow[], tagsFor: (call: CallRow) => string[]) {
  const counts = new Map<string, { calls: number; tokens: number; largest: CallRow | null }>();
  for (const call of calls) {
    for (const tag of tagsFor(call)) {
      const entry = counts.get(tag) ?? { calls: 0, tokens: 0, largest: null };
      const largest = !entry.largest || call.totalTokens > entry.largest.totalTokens ? call : entry.largest;
      counts.set(tag, { calls: entry.calls + 1, tokens: entry.tokens + call.totalTokens, largest });
    }
  }
  return [...counts.entries()]
    .map(([tag, entry]) => ({
      function: tag,
      calls: entry.calls,
      original_token_sum: entry.tokens,
      largest_record_id: entry.largest?.id,
      largest_call_tokens: entry.largest?.totalTokens,
    }))
    .sort((left, right) => right.original_token_sum - left.original_token_sum);
}

function modifiedLaterCount(calls: CallRow[]): number {
  return calls.filter(call => call.tags.includes('file-heavy') || call.recommendation).length;
}
