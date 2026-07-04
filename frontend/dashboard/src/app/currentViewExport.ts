import { callInvestigatorCallForCurrentUrl } from '../features/call-investigator/callInvestigatorState';
import { cacheContextCallsForCurrentUrl } from '../features/cache-context/CacheContextPage';
import { callsForCurrentUrl } from '../features/calls/CallsPage';
import { diagnosticsCallsForCurrentUrl } from '../features/diagnostics/DiagnosticsPage';
import { investigatorCallsForCurrentUrl } from '../features/investigator/InvestigatorPage';
import { overviewCallsForQuery } from '../features/overview/OverviewPage';
import { reportCallsForCurrentUrl } from '../features/reports/ReportsPage';
import { rowsToCsv, csvDateStamp, type CsvColumn } from '../features/shared/exportCsv';
import { callCsvColumns } from '../features/shared/tables';
import { threadCallsForCurrentUrl } from '../features/threads/ThreadsPage';
import { usageDrainCallsForCurrentUrl } from '../features/usage-drain/UsageDrainPage';
import type { ContextRuntime, DashboardModel } from '../api/types';
import type { ViewId } from './navigation';
import { rowLimitNoCap } from './rowLimit';
import type { HistoryScope } from './shellUrl';

export type RuntimeExportState = {
  contextRuntime: ContextRuntime;
  historyScope: HistoryScope;
  loadLimit: number;
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

export function currentViewCsvExport(
  activeView: ViewId,
  model: DashboardModel,
  runtime: RuntimeExportState,
  globalQuery = '',
  activePreset = '',
): CsvExportSpec {
  const stamp = csvDateStamp();
    switch (activeView) {
      case 'threads':
      return csvExport(`codex-thread-filtered-calls-${stamp}.csv`, threadCallsForCurrentUrl(model, globalQuery), callCsvColumns, 'call rows');
    case 'cache-context':
      return csvExport(`codex-${activeView}-calls-${stamp}.csv`, cacheContextCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    case 'usage-drain':
      return csvExport(`codex-usage-drain-calls-${stamp}.csv`, usageDrainCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    case 'diagnostics':
      return csvExport(`codex-diagnostics-calls-${stamp}.csv`, diagnosticsCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    case 'reports':
      return csvExport(`codex-reports-evidence-${stamp}.csv`, reportCallsForCurrentUrl(model), callCsvColumns, 'call rows');
    case 'settings':
      return csvExport(`codex-dashboard-settings-${stamp}.csv`, settingsExportRows(model, runtime), settingsCsvColumns, 'settings rows');
    case 'calls':
      return csvExport(`codex-calls-${stamp}.csv`, callsForCurrentUrl(model.calls, globalQuery, activePreset), callCsvColumns, 'call rows');
    case 'overview':
      return csvExport(`codex-overview-calls-${stamp}.csv`, overviewCallsForQuery(model.calls, globalQuery), callCsvColumns, 'call rows');
    case 'investigator':
      return csvExport(`codex-investigator-calls-${stamp}.csv`, investigatorCallsForCurrentUrl(model), callCsvColumns, 'call rows');
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
    { field: 'row_request', value: runtime.loadLimit === rowLimitNoCap ? 'no cap' : String(runtime.loadLimit) },
    { field: 'loaded_rows', value: String(runtime.loadedRowCount) },
    { field: 'total_available_rows', value: String(runtime.totalAvailableRows) },
    { field: 'auto_refresh', value: runtime.autoRefreshEnabled ? 'enabled' : 'paused' },
    { field: 'refresh_state', value: runtime.refreshState },
    { field: 'visible_calls', value: String(model.calls.length) },
    { field: 'visible_threads', value: String(model.threads.length) },
  ];
}
