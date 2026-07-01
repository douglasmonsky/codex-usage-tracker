import { RefreshCw } from 'lucide-react';

import type { DashboardModel, ReportSummary } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { weeklyColumns } from '../shared/tables';

export function ReportsPage({ model }: { model: DashboardModel }) {
  const active = model.reports[0];

  return (
    <div className="reports-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Reports</h1>
          <p>Research-style report snapshots generated from local aggregate data.</p>
        </div>
        <button className="primary-button" type="button">
          <RefreshCw size={16} /> Refresh Report
        </button>
      </div>
      <Panel title="Report Library" subtitle="Snapshots and planned report payloads">
        <div className="report-list">
          {model.reports.map(report => (
            <ReportCard key={report.title} report={report} active={report.title === active?.title} />
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

function ReportCard({ report, active }: { report: ReportSummary; active: boolean }) {
  const tone = report.status === 'Ready' ? 'green' : report.status === 'Planned' ? 'orange' : 'red';

  return (
    <article className={active ? 'report-card active' : 'report-card'}>
      <div>
        <strong>{report.title}</strong>
        <p>{report.description}</p>
      </div>
      <span>{report.owner}</span>
      <StatusBadge label={report.status} tone={tone} />
    </article>
  );
}
