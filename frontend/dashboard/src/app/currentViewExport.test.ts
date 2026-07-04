import { describe, expect, it } from 'vitest';

import { fixtureModel } from '../test-fixtures/dashboardFixture';
import { currentViewCsvExport, settingsExportRows, type RuntimeExportState } from './currentViewExport';
import { rowLimitNoCap } from './rowLimit';

const runtime: RuntimeExportState = {
  contextRuntime: {
    apiToken: 'test-token',
    contextApiEnabled: true,
    fileMode: false,
  },
  historyScope: 'all',
  loadLimit: rowLimitNoCap,
  loadedRowCount: 8,
  totalAvailableRows: 25,
  canUseLiveApi: true,
  autoRefreshEnabled: true,
  refreshState: 'Loaded all history',
};

describe('current view export helpers', () => {
  it('builds settings runtime rows with explicit no-cap and live states', () => {
    expect(settingsExportRows(fixtureModel, runtime)).toEqual([
      { field: 'live_api', value: 'available' },
      { field: 'context_api', value: 'enabled' },
      { field: 'history_scope', value: 'all' },
      { field: 'row_request', value: 'no cap' },
      { field: 'loaded_rows', value: '8' },
      { field: 'total_available_rows', value: '25' },
      { field: 'auto_refresh', value: 'enabled' },
      { field: 'refresh_state', value: 'Loaded all history' },
      { field: 'visible_calls', value: String(fixtureModel.calls.length) },
      { field: 'visible_threads', value: String(fixtureModel.threads.length) },
    ]);
  });

  it('exports settings runtime state as a two-column CSV', () => {
    const exportSpec = currentViewCsvExport('settings', fixtureModel, runtime);

    expect(exportSpec.filename).toMatch(/^codex-dashboard-settings-\d{4}-\d{2}-\d{2}\.csv$/);
    expect(exportSpec.label).toBe('settings rows');
    expect(exportSpec.rowCount).toBe(10);
    expect(exportSpec.csv).toContain('Field,Value');
    expect(exportSpec.csv).toContain('row_request,no cap');
    expect(exportSpec.csv).toContain('history_scope,all');
  });

 it('keeps current-view export routing scoped active call data', () => {
    const threadsExport = currentViewCsvExport('threads', fixtureModel, runtime, 'thread-9f3a');
    const callsExport = currentViewCsvExport('calls', fixtureModel, runtime, 'thread-9f3a');

 expect(threadsExport.filename).toMatch(/^codex-thread-filtered-calls-\d{4}-\d{2}-\d{2}\.csv$/);
 expect(threadsExport.label).toBe('call rows');
 expect(threadsExport.rowCount).toBe(1);
    expect(threadsExport.csv.split('\n')[0]).toContain(
      'timestamp,thread,call_started_at,call_duration_seconds,previous_call_event_timestamp,previous_call_delta_seconds',
    );
    expect(callsExport.label).toBe('call rows');
    expect(callsExport.rowCount).toBe(1);
  });
});
