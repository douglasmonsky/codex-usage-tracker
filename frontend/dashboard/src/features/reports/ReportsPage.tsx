import { Download, RefreshCw } from 'lucide-react';
import { useState } from 'react';

import type { DashboardModel, ReportSummary } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp } from '../shared/exportCsv';
import { weeklyColumns } from '../shared/tables';

export function ReportsPage({ model }: { model: DashboardModel }) {
  const [activeTitle, setActiveTitle] = useState(model.reports[0]?.title ?? '');
  const [refreshStatus, setRefreshStatus] = useState('Stored report snapshot loaded just now');
  const [exportStatus, setExportStatus] = useState('');
  const active = model.reports.find(report => report.title === activeTitle) ?? model.reports[0];

  function refreshReport() {
    setExportStatus('');
    setRefreshStatus(`Report snapshot refreshed ${new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date())}`);
  }

  function exportReportPack() {
    downloadJson(`codex-report-pack-${csvDateStamp()}.json`, {
      schema: 'codex-usage-tracker-react-report-pack-v1',
      activeReport: active?.title ?? null,
      reports: model.reports,
      weeklyWindows: model.weeklyWindows,
      threadSummaries: model.threads.map(thread => ({
        name: thread.name,
        turns: thread.turns,
        totalTokens: thread.totalTokens,
        cost: thread.cost,
        cachePct: thread.cachePct,
        coldResumeRisk: thread.coldResumeRisk,
      })),
    });
    setExportStatus(`Exported ${model.reports.length} report snapshots`);
  }

  return (
    <div className="reports-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Reports</h1>
          <p>Research-style report snapshots generated from local aggregate data.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button" onClick={exportReportPack}>
            <Download size={16} /> Export Pack
          </button>
          <button className="primary-button" type="button" onClick={refreshReport}>
            <RefreshCw size={16} /> Refresh Report
          </button>
        </div>
      </div>
      <Panel title="Report Library" subtitle={exportStatus || refreshStatus}>
        <div className="report-list">
          {model.reports.map(report => (
            <ReportCard key={report.title} report={report} active={report.title === active?.title} onSelect={() => setActiveTitle(report.title)} />
          ))}
        </div>
      </Panel>
      <div className="stacked-panels">
        <Panel title={active?.title ?? 'Weekly Credits'} subtitle="Projected credits with interval table">
          <LineChart series={model.weeklyCreditSeries} yLabel="Credits" />
        </Panel>
        <Panel title="Cost Curves" subtitle="Cumulative estimated cost by thread">
          <BarChart data={model.threads.map(thread => ({ label: thread.name, value: thread.cost }))} valueLabel={value => `$${value.toFixed(2)}`} />
        </Panel>
        <Panel title="Usage Drain Model" subtitle="Actual vs predicted local estimate">
          <LineChart series={model.actualVsPredictedSeries} yLabel="Credits" />
        </Panel>
        <Panel title="Confidence Intervals" subtitle="Weekly window evidence">
          <DataTable columns={weeklyColumns} data={model.weeklyWindows} compact />
        </Panel>
      </div>
    </div>
  );
}

function ReportCard({ report, active, onSelect }: { report: ReportSummary; active: boolean; onSelect: () => void }) {
  const tone = report.status === 'Ready' ? 'green' : report.status === 'Planned' ? 'orange' : 'red';

  return (
    <button className={active ? 'report-card active' : 'report-card'} type="button" onClick={onSelect}>
      <div>
        <strong>{report.title}</strong>
        <p>{report.description}</p>
      </div>
      <span>{report.owner}</span>
      <StatusBadge label={report.status} tone={tone} />
    </button>
  );
}

function downloadJson(filename: string, payload: unknown): void {
  const serialized = JSON.stringify(payload, null, 2);
  const blob = new Blob([serialized], { type: 'application/json;charset=utf-8' });
  const objectUrl =
    typeof URL.createObjectURL === 'function'
      ? URL.createObjectURL(blob)
      : `data:application/json;charset=utf-8,${encodeURIComponent(serialized)}`;
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  if (objectUrl.startsWith('blob:') && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(objectUrl);
  }
}
