import { AlertTriangle, Clock3, Database, LoaderCircle } from 'lucide-react';

import { stateDescription } from '../spec';
import type { VisualizationSpecV1 } from '../spec';
import styles from './Visualization.module.css';

export function VisualizationState({ spec }: { spec: VisualizationSpecV1 }) {
  const state = spec.state;
  const Icon = state.kind === 'loading' ? LoaderCircle : state.kind === 'stale' ? Clock3 : state.kind === 'error' ? AlertTriangle : Database;
  return (
    <div className={styles.state} data-state={state.kind} role={state.kind === 'error' ? 'alert' : 'status'}>
      <Icon aria-hidden="true" className={state.kind === 'loading' ? styles.spinning : undefined} size={20} />
      <div>
        <strong>{stateTitle(state.kind)}</strong>
        <span>{stateDescription(spec)}</span>
      </div>
    </div>
  );
}

export function shouldRenderVisualizationData(spec: VisualizationSpecV1) {
  return spec.state.kind === 'ready' || spec.state.kind === 'partial' || spec.state.kind === 'stale';
}

function stateTitle(kind: VisualizationSpecV1['state']['kind']) {
  switch (kind) {
    case 'ready':
      return 'Ready';
    case 'loading':
      return 'Loading evidence';
    case 'empty':
      return 'No matching evidence';
    case 'partial':
      return 'Partial evidence';
    case 'insufficient-data':
      return 'More evidence required';
    case 'stale':
      return 'Stored snapshot';
    case 'error':
      return 'Evidence unavailable';
  }
}
