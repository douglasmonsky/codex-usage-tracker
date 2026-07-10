import { Columns3, Download } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button, IconButton, SegmentedControl } from '../index';
import { EvidenceTable } from './EvidenceTable';
import { CallInspector, ScenarioFrame } from './ScenarioFrame';
import evidenceStyles from './Evidence.module.css';
import styles from './Scenarios.module.css';
import { labCalls, type LabCall, type LabScenarioProps } from './visualContractData';

type ExploreScenarioProps = LabScenarioProps & {
  selectedCall: LabCall;
  onSelectCall: (call: LabCall) => void;
};

export function ExploreScenario({ onAnnounce, onNavigate, onSelectCall, selectedCall }: ExploreScenarioProps) {
  const [mode, setMode] = useState<'calls' | 'threads'>('calls');
  const [query, setQuery] = useState('');
  const [model, setModel] = useState('all');
  const rows = useMemo(
    () => labCalls.filter((call) => {
      const matchesQuery = `${call.thread} ${call.id}`.toLowerCase().includes(query.toLowerCase());
      return matchesQuery && (model === 'all' || call.model === model);
    }),
    [model, query],
  );

  return (
    <ScenarioFrame
      eyebrow="Evidence explorer"
      title={mode === 'calls' ? 'Calls' : 'Threads'}
      description="A table-first workspace with stable selection, frozen identity, and immediate investigation."
      actions={
        <>
          <IconButton aria-label="Choose columns" onClick={() => onAnnounce('Column chooser opened')}><Columns3 /></IconButton>
          <Button onClick={() => onAnnounce(`${mode} export prepared`)}><Download />Export</Button>
        </>
      }
    >
      <div className={styles.toolbar}>
        <SegmentedControl
          label="Explore entity"
          options={[{ label: 'Calls', value: 'calls' }, { label: 'Threads', value: 'threads' }]}
          value={mode}
          onValueChange={setMode}
        />
        <div className={styles.toolbarGrow}>
          <input
            className={styles.filterInput}
            placeholder={`Search ${mode}`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <select className={styles.filterSelect} aria-label="Model" value={model} onChange={(event) => setModel(event.target.value)}>
          <option value="all">All models</option>
          <option value="gpt-5.6">gpt-5.6</option>
          <option value="gpt-5.5">gpt-5.5</option>
          <option value="gpt-5.6-mini">gpt-5.6-mini</option>
        </select>
      </div>

      <div className={evidenceStyles.splitWorkspace}>
        <EvidenceTable calls={rows} selectedId={selectedCall.id} onSelect={onSelectCall} />
        <CallInspector
          call={selectedCall}
          onCopy={() => onAnnounce('Call link copied')}
          onOpen={() => onNavigate('call')}
        />
      </div>
    </ScenarioFrame>
  );
}
