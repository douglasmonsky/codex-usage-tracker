import type { DashboardModel, DiagnosticSection } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';

export function DiagnosticsPage({ model }: { model: DashboardModel }) {
  return (
    <div className="diagnostics-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Diagnostics Notebook</h1>
          <p>Technical report of system behavior and usage patterns.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label="Data as of Jun 01" tone="blue" />
          <StatusBadge label="Local Only" tone="green" />
        </div>
      </div>
      <Panel title="Executive Findings" subtitle="Top observations from aggregate telemetry" className="span-all">
        <div className="executive-grid">
          {model.diagnostics.slice(0, 3).map((section, index) => (
            <article className={`executive-card tone-${index + 1}`} key={section.title}>
              <span>{index + 1}</span>
              <strong>{section.title}</strong>
              <p>{section.finding}</p>
            </article>
          ))}
        </div>
      </Panel>
      <div className="diagnostic-sections">
        {model.diagnostics.map(section => (
          <DiagnosticRow key={section.title} section={section} />
        ))}
      </div>
      <aside className="side-panel">
        <Panel title="Notebook Index" subtitle="Jump to section">
          <div className="index-list">
            {model.diagnostics.map((section, index) => (
              <span key={section.title}>
                <i>{index + 1}</i>
                {section.title}
                <StatusBadge label={section.status} tone={section.status === 'Ready' ? 'green' : 'orange'} />
              </span>
            ))}
          </div>
        </Panel>
      </aside>
    </div>
  );
}

function DiagnosticRow({ section }: { section: DiagnosticSection }) {
  return (
    <Panel title={section.title} subtitle={section.metric}>
      <div className="diagnostic-row">
        <LineChart series={section.series} yLabel={section.title} height={180} />
        <div>
          <h3>Finding</h3>
          <p>{section.finding}</p>
          <StatusBadge label={`${section.confidence} confidence`} tone={section.confidence === 'High' ? 'green' : 'orange'} />
        </div>
        <div className="mini-evidence">
          <span>Evidence</span>
          <strong>{section.metric}</strong>
          <small>{section.status}</small>
        </div>
      </div>
    </Panel>
  );
}
