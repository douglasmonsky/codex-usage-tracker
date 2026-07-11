import { Activity, ChartNoAxesCombined, ShieldCheck } from 'lucide-react';
import { useMemo, useState } from 'react';

import { visualizationContractStates, visualizationExampleSpecs, visualizationSpecForState } from '../fixtures';
import { Visualization, type VisualizationView } from '../react';
import type { VisualizationDataState, VisualizationSpecV1 } from '../spec';
import styles from './VisualizationContractLab.module.css';

const readyState: VisualizationDataState = { kind: 'ready' };
const stateOptions = [readyState, ...visualizationContractStates];

export function VisualizationContractLab() {
  const initial = useMemo(readLabSearch, []);
  const [exampleId, setExampleId] = useState(initial.exampleId);
  const [stateKind, setStateKind] = useState<VisualizationDataState['kind']>(initial.stateKind);
  const [defaultView, setDefaultView] = useState<VisualizationView>(initial.view);
  const baseSpec = visualizationExampleSpecs.find(spec => spec.id === exampleId) ?? visualizationExampleSpecs[0];
  const state = stateOptions.find(option => option.kind === stateKind) ?? readyState;
  const spec = state.kind === 'ready' ? baseSpec : visualizationSpecForState(baseSpec, state);

  function updateSelection(next: { exampleId?: string; stateKind?: VisualizationDataState['kind']; view?: VisualizationView }) {
    const resolved = {
      exampleId: next.exampleId ?? exampleId,
      stateKind: next.stateKind ?? stateKind,
      view: next.view ?? defaultView,
    };
    setExampleId(resolved.exampleId);
    setStateKind(resolved.stateKind);
    setDefaultView(resolved.view);
    const url = new URL(window.location.href);
    url.searchParams.set('lab', 'visualization-contract');
    url.searchParams.set('example', resolved.exampleId);
    url.searchParams.set('state', resolved.stateKind);
    url.searchParams.set('mode', resolved.view);
    window.history.replaceState(null, '', url);
  }

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <ChartNoAxesCombined size={20} />
          <div>
            <strong>Visualization Contract Lab</strong>
            <span>Codex Usage Tracker redesign</span>
          </div>
        </div>
        <div className={styles.status}>
          <ShieldCheck size={16} />
          Semantic spec v1
        </div>
      </header>

      <main className={styles.workspace}>
        <aside className={styles.controls} aria-label="Visualization contract controls">
          <div className={styles.controlGroup}>
            <label htmlFor="visualization-example">Example</label>
            <select
              id="visualization-example"
              value={exampleId}
              onChange={event => updateSelection({ exampleId: event.target.value })}
            >
              {visualizationExampleSpecs.map(example => <option key={example.id} value={example.id}>{example.title}</option>)}
            </select>
          </div>
          <div className={styles.controlGroup}>
            <label htmlFor="visualization-state">Data state</label>
            <select
              id="visualization-state"
              value={stateKind}
              onChange={event => updateSelection({ stateKind: event.target.value as VisualizationDataState['kind'] })}
            >
              {stateOptions.map(option => <option key={option.kind} value={option.kind}>{stateLabel(option.kind)}</option>)}
            </select>
          </div>
          <div className={styles.controlGroup}>
            <span className={styles.groupLabel}>Initial view</span>
            <div className={styles.viewModes} role="group" aria-label="Initial visualization view">
              {(['chart', 'table'] as const).map(view => (
                <button key={view} type="button" aria-pressed={defaultView === view} onClick={() => updateSelection({ view })}>
                  {view === 'chart' ? 'Chart' : 'Table'}
                </button>
              ))}
            </div>
          </div>
          <ContractReadout spec={spec} />
        </aside>

        <section className={styles.canvas} aria-label="Visualization preview">
          <div className={styles.canvasHeading}>
            <div>
              <span>Contract preview</span>
              <strong>{spec.kind === 'flow' ? 'Flow' : spec.kind === 'heatmap' ? 'Matrix' : 'Cartesian'} renderer</strong>
            </div>
            <Activity size={18} />
          </div>
          <Visualization key={`${spec.id}-${defaultView}`} spec={spec} defaultView={defaultView} height={420} />
        </section>
      </main>
    </div>
  );
}

function ContractReadout({ spec }: { spec: VisualizationSpecV1 }) {
  const facts = [
    ['State', spec.state.kind],
    ['Rows', String(spec.scope.rowCount)],
    ['Table columns', String(spec.table.columns.length)],
    ['Annotations', String(spec.annotations?.length ?? 0)],
    ['Selection', spec.interactions?.selection ? 'Linked' : 'None'],
    ['Zoom / brush', spec.interactions?.zoom || spec.interactions?.brush ? 'Enabled' : 'None'],
  ];
  return (
    <dl className={styles.readout}>
      {facts.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function readLabSearch() {
  const search = new URLSearchParams(window.location.search);
  const requestedExample = search.get('example');
  const requestedState = search.get('state') as VisualizationDataState['kind'] | null;
  const requestedView = search.get('mode');
  return {
    exampleId: visualizationExampleSpecs.some(spec => spec.id === requestedExample) ? requestedExample as string : visualizationExampleSpecs[0].id,
    stateKind: stateOptions.some(state => state.kind === requestedState) ? requestedState as VisualizationDataState['kind'] : 'ready',
    view: requestedView === 'table' ? 'table' as const : 'chart' as const,
  };
}

function stateLabel(kind: VisualizationDataState['kind']) {
  if (kind === 'insufficient-data') return 'Insufficient data';
  return `${kind.charAt(0).toUpperCase()}${kind.slice(1)}`;
}
