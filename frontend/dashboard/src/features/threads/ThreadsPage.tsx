import { Columns3, Filter } from 'lucide-react';

import type { DashboardModel } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { DonutChart } from '../../charts/DonutChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { money } from '../shared/format';
import { threadColumns } from '../shared/tables';

export function ThreadsPage({ model }: { model: DashboardModel }) {
  const selected = model.threads[0];

  return (
    <div className="thread-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Thread Efficiency</h1>
          <p>Threads as units of work, with cost concentration and handoff signals.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button">
            <Filter size={16} /> Filters
          </button>
          <button className="toolbar-button" type="button">
            <Columns3 size={16} /> Columns
          </button>
        </div>
      </div>
      <Panel title="Cost vs Turns" subtitle="Sorted by estimated cost">
        <BarChart
          data={model.threads.map(thread => ({
            label: thread.name,
            value: thread.cost,
            color: thread.cachePct < 20 ? '#ef4444' : thread.cachePct < 45 ? '#f59e0b' : '#16a34a',
          }))}
          valueLabel={money}
        />
      </Panel>
      <Panel title="Thread Leaderboard" subtitle="Cache efficiency, cold resume risk, and productivity">
        <DataTable columns={threadColumns} data={model.threads} compact />
      </Panel>
      {selected ? (
        <aside className="side-panel">
          <Panel title="Selected Thread" subtitle={selected.name}>
            <div className="detail-stat-grid vertical">
              <span>
                <strong>{selected.turns}</strong>
                Turns visible
              </span>
              <span>
                <strong>{money(selected.cost)}</strong>
                Estimated cost
              </span>
              <span>
                <strong>{selected.cachePct.toFixed(0)}%</strong>
                Cache hit rate
              </span>
            </div>
            <DonutChart
              centerLabel="Model Mix"
              data={[
                { label: 'codex-1', value: 68, color: '#2563eb' },
                { label: 'o4-mini', value: 21, color: '#059669' },
                { label: 'Other', value: 11, color: '#94a3b8' },
              ]}
            />
          </Panel>
        </aside>
      ) : null}
    </div>
  );
}
