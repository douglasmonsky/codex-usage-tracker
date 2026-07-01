import type { CSSProperties } from 'react';

import type { DashboardModel } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { MetricCard } from '../../components/MetricCard';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { threadColumns } from '../shared/tables';

export function CacheContextPage({ model }: { model: DashboardModel }) {
  return (
    <div className="cache-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Cache And Context Lab</h1>
          <p>Cache behavior, cold resumes, context pressure, and optimization recommendations.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label="Snapshot current" tone="green" />
          <StatusBadge label="Context safe" tone="blue" />
        </div>
      </div>
      <div className="metric-grid span-all">
        {model.cards.slice(2, 5).map(card => (
          <MetricCard key={card.label} card={card} />
        ))}
      </div>
      <Panel title="Cache Hit Rate & Context Window Over Time" subtitle="Cache reuse and context pressure">
        <LineChart series={[...model.cacheSeries, model.usageRemainingSeries[0]].filter(Boolean)} yLabel="Percent" valueFormatter={value => `${value}%`} />
      </Panel>
      <Panel title="Cache Reuse Heatmap" subtitle="Threads by weekly window">
        <div className="heatmap" role="table" aria-label="Cache reuse heatmap">
          <div className="heatmap-head">
            <span>Thread</span>
            {['May 26', 'Jun 02', 'Jun 09', 'Jun 16', 'Jun 23', 'Jun 30'].map(label => (
              <span key={label}>{label}</span>
            ))}
          </div>
          {model.cacheHeatmap.map(row => (
            <div className="heatmap-row" key={row.thread}>
              <strong>{row.thread}</strong>
              {row.values.map((value, index) => (
                <span key={`${row.thread}-${index}`} style={{ '--intensity': value / 100 } as CSSProperties}>
                  {value}%
                </span>
              ))}
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Threads Overview" subtitle="Cold resume and cache efficiency signals" className="span-all">
        <DataTable columns={threadColumns} data={model.threads} compact />
      </Panel>
      <aside className="side-panel">
        <Panel title="Selected Thread Diagnosis" subtitle="thread-8c1e">
          <div className="evidence-list">
            <span>Resume gap <strong>5 days 14 hours</strong></span>
            <span>Total turns <strong>142</strong></span>
            <span>Input tokens <strong>1.84M</strong></span>
            <span>Cache hit rate <strong>22.1%</strong></span>
          </div>
          <h3>Suggested Actions</h3>
          <ul className="compact-list">
            <li>Summarize before the next work session.</li>
            <li>Split completed topics into fresh threads.</li>
            <li>Use structured handoffs for long-running work.</li>
          </ul>
        </Panel>
      </aside>
    </div>
  );
}
