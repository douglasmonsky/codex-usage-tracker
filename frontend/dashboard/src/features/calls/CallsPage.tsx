import { Columns3, Download, Filter, RefreshCw } from 'lucide-react';

import type { DashboardModel } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { money } from '../shared/format';
import { callColumns } from '../shared/tables';

export function CallsPage({ model }: { model: DashboardModel }) {
  return (
    <div className="page-grid">
      <div className="page-title-row">
        <div>
          <h1>Calls</h1>
          <p>High-density analyst view for model calls, cost, cache hits, and duration.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button">
            <Columns3 size={16} /> Columns
          </button>
          <button className="toolbar-button" type="button">
            <Download size={16} /> Export
          </button>
          <button className="primary-button" type="button">
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
      </div>
      <div className="dashboard-grid three">
        <Panel title="Usage Over Time" subtitle="Tokens">
          <LineChart series={model.tokenSeries} yLabel="Tokens" height={220} />
        </Panel>
        <Panel title="Cost by Model" subtitle="Estimated USD">
          <BarChart data={model.modelCosts} valueLabel={money} />
        </Panel>
        <Panel title="Cache Hit Rate Over Time" subtitle="Daily">
          <LineChart series={model.cacheSeries} yLabel="Cache %" height={220} valueFormatter={value => `${value}%`} />
        </Panel>
      </div>
      <div className="filter-row">
        <label className="search-box">
          <span className="sr-only">Search calls</span>
          <input placeholder="Search calls, threads, models..." />
        </label>
        <button className="toolbar-button" type="button">
          <Filter size={16} /> More Filters
        </button>
        <div className="density-toggle" aria-label="Density">
          <button type="button" className="active">Dense</button>
          <button type="button">Roomy</button>
        </div>
      </div>
      <Panel title="Model Calls" subtitle="Aggregate rows only; raw context stays gated.">
        <DataTable columns={callColumns} data={model.calls} />
      </Panel>
    </div>
  );
}
