import { ArrowRight } from 'lucide-react';
import { useState } from 'react';

import type { DashboardModel, Finding } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { formatNumber } from '../shared/format';
import { callColumns } from '../shared/tables';

export function InvestigatorPage({ model }: { model: DashboardModel }) {
  const [selectedRank, setSelectedRank] = useState(model.findings[0]?.rank ?? 0);
  const [evidenceStatus, setEvidenceStatus] = useState('Select a finding to inspect aggregate evidence.');
  const selected = model.findings.find(finding => finding.rank === selectedRank) ?? model.findings[0];

  function selectFinding(finding: Finding) {
    setSelectedRank(finding.rank);
    setEvidenceStatus(`Selected ${finding.title}`);
  }

  function inspectCalls(finding: Finding) {
    setEvidenceStatus(`Evidence table focused on ${finding.title}`);
  }

  return (
    <div className="workbench-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Investigator Workbench</h1>
          <p>Ranked findings, evidence, and aggregate-only drilldowns.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label="Stored Snapshot" tone="blue" />
          <StatusBadge label="Live API" tone="green" />
        </div>
      </div>
      <Panel title="What Is Driving Usage?" subtitle="Ranked by estimated credit impact">
        <div className="finding-list">
          {model.findings.map(finding => (
            <FindingCard
              key={finding.rank}
              finding={finding}
              active={finding.rank === selected?.rank}
              onSelect={() => selectFinding(finding)}
            />
          ))}
        </div>
      </Panel>
      <div className="stacked-panels">
        <Panel title="Usage Drain Over Time" subtitle="Observed credits vs baseline">
          <LineChart series={model.actualVsPredictedSeries} yLabel="Credits" height={230} />
        </Panel>
        <Panel title="Projected Weekly Credits" subtitle="Plan trend with confidence intervals">
          <LineChart series={model.weeklyCreditSeries} yLabel="Credits" height={230} />
        </Panel>
        <Panel title="Cache Ratio Over Time" subtitle="Cache behavior around usage windows">
          <LineChart series={model.cacheSeries} yLabel="Cache Hit %" height={220} valueFormatter={value => `${value}%`} />
        </Panel>
        <Panel title="Evidence Table" subtitle={evidenceStatus || `${formatNumber(model.calls.length)} preview calls`}>
          <DataTable columns={callColumns.slice(0, 8)} data={model.calls} compact />
        </Panel>
      </div>
      {selected ? <SelectedFinding finding={selected} onInspectCalls={() => inspectCalls(selected)} /> : null}
    </div>
  );
}

function FindingCard({ finding, active, onSelect }: { finding: Finding; active: boolean; onSelect: () => void }) {
  return (
    <article className={active ? 'finding-card active' : 'finding-card'}>
      <div className="finding-rank">{finding.rank}</div>
      <div className="finding-body">
        <h3>{finding.title}</h3>
        <p>{finding.summary}</p>
        <div className="finding-stats">
          <strong>{formatNumber(finding.credits)}</strong>
          <span>{finding.share.toFixed(1)}% total</span>
        </div>
      </div>
      <StatusBadge label={finding.severity} tone={finding.severity === 'High' ? 'red' : 'orange'} />
      <button className="inline-button" type="button" onClick={onSelect}>
        Inspect <ArrowRight size={14} />
      </button>
    </article>
  );
}

function SelectedFinding({ finding, onInspectCalls }: { finding: Finding; onInspectCalls: () => void }) {
  return (
    <aside className="side-panel">
      <Panel title="Selected Finding" subtitle={finding.title}>
        <div className="detail-stat-grid">
          <span>
            <strong>{formatNumber(finding.credits)}</strong>
            Est. Credits
          </span>
          <span>
            <strong>{finding.share.toFixed(1)}%</strong>
            Share
          </span>
          <span>
            <strong>2.4x</strong>
            vs baseline
          </span>
        </div>
        <h3>Why This Matters</h3>
        <p>{finding.summary} The signal is visible in aggregate timing, token, cache, and cost measures.</p>
        <div className="evidence-list">
          <span>Duration <strong>6h 42m</strong></span>
          <span>Calls <strong>326</strong></span>
          <span>Cache hit rate <strong>22%</strong></span>
          <span>Models used <strong>4</strong></span>
        </div>
        <button className="primary-button stretch" type="button" onClick={onInspectCalls}>
          Inspect Calls <ArrowRight size={16} />
        </button>
      </Panel>
    </aside>
  );
}
