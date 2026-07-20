import { callInvestigatorCallForCurrentUrl } from '../features/call-investigator/callInvestigatorState';
import { rowsToCsv, csvDateStamp, type CsvColumn } from '../features/shared/exportCsv';
import { callCsvColumns } from '../features/shared/tables';
import type { ContextRuntime, DashboardModel } from '../api/types';
import { loadWindowLabel, type LoadWindow } from '../data/dataScope';
import type { ViewId } from './navigation';
import { routeDefinition } from './routeCatalog';
import { rowLimitNoCap } from './rowLimit';
import type { HistoryScope } from './shellUrl';

export type RuntimeExportState = {
  contextRuntime: ContextRuntime;
  historyScope: HistoryScope;
  loadWindow: LoadWindow;
  loadLimit: number;
  scopeSince: string | null;
  loadedRowCount: number;
  totalAvailableRows: number;
  canUseLiveApi: boolean;
  autoRefreshEnabled: boolean;
  refreshState: string;
};

export type CsvExportSpec = {
  filename: string;
  csv: string;
  rowCount: number;
  label: string;
};

export async function currentViewCsvExport(
  activeView: ViewId,
  model: DashboardModel,
  runtime: RuntimeExportState,
  globalQuery = '',
  activePreset = '',
): Promise<CsvExportSpec> {
  if (!routeDefinition(activeView).capabilities.export) {
    throw new Error(`CSV export is not available for ${routeDefinition(activeView).label}.`);
  }
  const stamp = csvDateStamp();
    switch (activeView) {
      case 'threads': {
      const { threadCallsForCurrentUrl } = await import('../features/threads/ThreadsPage');
      return csvExport(`codex-thread-filtered-calls-${stamp}.csv`, threadCallsForCurrentUrl(model, globalQuery), callCsvColumns, 'call rows');
      }
    case 'cache-context': {
      const { cacheContextCallsForCurrentUrl } = await import('../features/cache-context/CacheContextPage');
      return csvExport(`codex-${activeView}-calls-${stamp}.csv`, cacheContextCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    }
    case 'usage-drain': {
      const { usageDrainCallsForCurrentUrl } = await import('../features/usage-drain/UsageDrainPage');
      return csvExport(`codex-usage-drain-calls-${stamp}.csv`, usageDrainCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    }
    case 'diagnostics': {
      const { diagnosticsCallsForCurrentUrl } = await import('../features/diagnostics/DiagnosticsPage');
      return csvExport(`codex-diagnostics-calls-${stamp}.csv`, diagnosticsCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    }
    case 'reports': {
      const { reportCallsForCurrentUrl } = await import('../features/reports/ReportsPage');
      return csvExport(`codex-reports-evidence-${stamp}.csv`, reportCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    }
    case 'settings':
      return csvExport(`codex-dashboard-settings-${stamp}.csv`, settingsExportRows(model, runtime), settingsCsvColumns, 'settings rows');
    case 'calls': {
      const { callsForCurrentUrl } = await import('../features/calls/CallsPage');
      return csvExport(`codex-calls-${stamp}.csv`, callsForCurrentUrl(model.calls, globalQuery, activePreset), callCsvColumns, 'call rows');
    }
    case 'overview': {
      const { overviewCallsForQuery } = await import('../features/overview/OverviewPage');
      return csvExport(`codex-overview-calls-${stamp}.csv`, overviewCallsForQuery(model.calls, globalQuery), callCsvColumns, 'call rows');
    }
    case 'investigator': {
      const { investigatorCallsForCurrentUrl } = await import('../features/investigator/InvestigatorPage');
      return csvExport(`codex-investigator-calls-${stamp}.csv`, investigatorCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    }
    case 'compression-lab':
      return csvExport(`codex-compression-lab-scope-${stamp}.csv`, model.calls, callCsvColumns, 'call rows');
    case 'call':
      return csvExport(`codex-call-calls-${stamp}.csv`, callInvestigatorCallForCurrentUrl(model), callCsvColumns, 'call rows');
  }
}

function csvExport<T>(filename: string, rows: T[], columns: Array<CsvColumn<T>>, label: string): CsvExportSpec {
  return {
    filename,
    csv: rowsToCsv(rows, columns),
    rowCount: rows.length,
    label,
  };
}

type SettingsExportRow = { field: string; value: string };

const settingsCsvColumns: Array<CsvColumn<SettingsExportRow>> = [
  { header: 'Field', value: row => row.field },
  { header: 'Value', value: row => row.value },
];

export function settingsExportRows(model: DashboardModel, runtime: RuntimeExportState): SettingsExportRow[] {
  return [
    { field: 'live_api', value: runtime.canUseLiveApi ? 'available' : 'static snapshot' },
    { field: 'context_api', value: runtime.contextRuntime.contextApiEnabled ? 'enabled' : 'gated' },
    { field: 'history_scope', value: runtime.historyScope },
    { field: 'data_window', value: loadWindowLabel(runtime.loadWindow, runtime.loadLimit) },
    { field: 'scope_since', value: runtime.scopeSince ?? 'none' },
    { field: 'row_request', value: runtime.loadLimit === rowLimitNoCap ? 'no cap' : String(runtime.loadLimit) },
    { field: 'loaded_rows', value: String(runtime.loadedRowCount) },
    { field: 'total_available_rows', value: String(runtime.totalAvailableRows) },
    { field: 'auto_refresh', value: runtime.autoRefreshEnabled ? 'enabled' : 'paused' },
    { field: 'refresh_state', value: runtime.refreshState },
    { field: 'visible_calls', value: String(model.calls.length) },
    { field: 'visible_threads', value: String(model.threads.length) },
  ];
}
