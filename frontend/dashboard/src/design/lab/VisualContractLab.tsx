import {
  Activity,
  AlertTriangle,
  Clock3,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  LoaderCircle,
  MoreHorizontal,
  RefreshCw,
  Search,
  Table2,
  TimerReset,
} from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { Button, IconButton, ProgressBar, StatusBadge, Surface } from '../index';
import { DataScopePopover } from './DataScopePopover';
import { ExploreScenario } from './ExploreScenario';
import { InvestigateScenario } from './InvestigateScenario';
import { LimitsScenario } from './LimitsScenario';
import { OverviewScenario } from './OverviewScenario';
import { CallScenario } from './ScenarioFrame';
import stateStyles from './ContractStates.module.css';
import feedbackStyles from './VisualContractFeedback.module.css';
import styles from './VisualContractLab.module.css';
import { labCalls, type LabCall, type LabDataState, type LabView } from './visualContractData';

const navigation = [
  { id: 'overview' as const, label: 'Overview', icon: Gauge, meta: '3' },
  { id: 'explore' as const, label: 'Explore', icon: Table2, meta: '5k' },
  { id: 'investigate' as const, label: 'Investigate', icon: FlaskConical, meta: '3' },
  { id: 'limits' as const, label: 'Limits', icon: TimerReset, meta: '1' },
];

const labDataStates: LabDataState[] = ['ready', 'loading', 'empty', 'stale', 'partial', 'error'];
const labViews: LabView[] = ['overview', 'explore', 'investigate', 'limits', 'call'];

function replaceLabSearch(key: string, value: string | null) {
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(key, value);
  else url.searchParams.delete(key);
  window.history.replaceState(null, '', url);
}

function initialView(): LabView {
  const requested = new URLSearchParams(window.location.search).get('view') as LabView | null;
  return requested && labViews.includes(requested) ? requested : 'overview';
}

function initialDataState(): LabDataState {
  const requested = new URLSearchParams(window.location.search).get('state') as LabDataState | null;
  return requested && labDataStates.includes(requested) ? requested : 'ready';
}

type ContractStatePanelProps = {
  state: Exclude<LabDataState, 'ready'>;
  onOpenScope: () => void;
  onRetry: () => void;
};

function ContractStatePanel({ onOpenScope, onRetry, state }: ContractStatePanelProps) {
  if (state === 'stale' || state === 'partial') {
    return (
      <Surface className={stateStyles.stateBanner} data-tone={state === 'partial' ? 'caution' : 'neutral'}>
        {state === 'stale' ? <Clock3 /> : <AlertTriangle />}
        <div>
          <strong>{state === 'stale' ? 'Showing current cached evidence while source updates load' : 'Partial evidence is available'}</strong>
          <span>
            {state === 'stale'
              ? '7 of 8 files checked / 28,419 records / 4.2s elapsed'
              : '7 of 8 source files indexed. Conclusions are automatically downgraded.'}
          </span>
        </div>
        <StatusBadge tone={state === 'partial' ? 'caution' : 'neutral'}>{state}</StatusBadge>
      </Surface>
    );
  }

  const content = {
    loading: {
      icon: LoaderCircle,
      title: 'Building the local evidence index',
      detail: 'Reading 8 source files / 18,420 of 42,318 records processed.',
    },
    empty: {
      icon: Database,
      title: 'No calls match this data scope',
      detail: 'The index is current. Adjust history, filters, or row scope to bring evidence into view.',
    },
    error: {
      icon: AlertTriangle,
      title: 'The latest source delta could not be read',
      detail: 'Cached evidence is unchanged. Retry the source read or review source health in Settings.',
    },
  }[state];
  const Icon = content.icon;

  return (
    <Surface className={stateStyles.statePanel} data-tone={state}>
      <Icon aria-hidden="true" />
      <div>
        <StatusBadge tone={state === 'error' ? 'risk' : 'neutral'}>{state}</StatusBadge>
        <h1>{content.title}</h1>
        <p>{content.detail}</p>
      </div>
      {state === 'loading' ? <ProgressBar label="Index build progress" value={44} /> : null}
      <div className={stateStyles.stateActions}>
        {state !== 'loading' ? <Button variant="primary" onClick={onRetry}>Retry</Button> : null}
        <Button onClick={onOpenScope}>{state === 'empty' ? 'Adjust scope' : 'View data scope'}</Button>
      </div>
    </Surface>
  );
}

export function VisualContractLab() {
  const [view, setView] = useState<LabView>(initialView);
  const [selectedCall, setSelectedCall] = useState<LabCall>(labCalls[1]);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [dataState, setDataState] = useState<LabDataState>(initialDataState);
  const [history, setHistory] = useState<'active' | 'all'>('active');
  const [rowLimit, setRowLimit] = useState<number | null>(5000);
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!refreshing) return undefined;
    const timer = window.setTimeout(() => {
      setRefreshing(false);
      setDataState((current) => {
        if (current !== 'stale') return current;
        replaceLabSearch('state', null);
        return 'ready';
      });
      setAnnouncement('Index refresh complete: 42,318 records current');
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [refreshing]);

  useEffect(() => {
    if (!announcement) return undefined;
    const timer = window.setTimeout(() => setAnnouncement(null), 2400);
    return () => window.clearTimeout(timer);
  }, [announcement]);

  useEffect(() => {
    if (!scopeOpen) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setScopeOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [scopeOpen]);

  const activeLabel = useMemo(
    () => navigation.find((item) => item.id === view)?.label ?? (view === 'call' ? 'Call Investigator' : 'Dashboard'),
    [view],
  );

  const navigate = (nextView: LabView) => {
    setView(nextView);
    replaceLabSearch('view', nextView === 'overview' ? null : nextView);
    setAnnouncement(`${nextView === 'call' ? 'Call Investigator' : nextView} opened`);
    window.scrollTo({ top: 0 });
  };

  const selectCall = (call: LabCall) => {
    setSelectedCall(call);
    setAnnouncement(`${call.thread} selected`);
  };

  const applyScope = (rows: number | null, nextHistory: 'active' | 'all') => {
    setRowLimit(rows);
    setHistory(nextHistory);
    setScopeOpen(false);
    setAnnouncement(`${rows === null ? 'All rows' : `${rows.toLocaleString()} rows`} / ${nextHistory} history applied`);
  };

  const startRefresh = () => {
    setRefreshing(true);
    setDataState('stale');
    replaceLabSearch('state', 'stale');
    setAnnouncement('Checking source files for new records');
  };

  const cancelRefresh = () => {
    setRefreshing(false);
    setDataState('partial');
    replaceLabSearch('state', 'partial');
    setAnnouncement('Refresh cancelled; current evidence marked partial');
  };

  const previewState = (state: LabDataState) => {
    setDataState(state);
    replaceLabSearch('state', state === 'ready' ? null : state);
    setAnnouncement(`${state} data state previewed`);
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    if (!search.trim()) return;
    navigate('explore');
    setAnnouncement(`Searching loaded evidence for “${search.trim()}”`);
  };

  const blocksScenario = dataState === 'loading' || dataState === 'empty' || dataState === 'error';

  return (
    <div className={styles.root}>
      <div className={styles.trustStrip}>Unofficial project. Not made by, affiliated with, endorsed by, sponsored by, or supported by OpenAI.</div>
      <div className={styles.shell}>
        <aside className={styles.rail}>
          <div className={styles.brand}>
            <span className={styles.brandMark}><Activity /></span>
            <span className={styles.brandCopy}><strong>Codex Usage</strong><span>Local evidence workspace</span></span>
          </div>
          <nav className={styles.nav} aria-label="Visual contract navigation">
            {navigation.map((item) => {
              const Icon = item.icon;
              return (
                <button className={styles.navButton} data-active={item.id === view} key={item.id} type="button" onClick={() => navigate(item.id)}>
                  <Icon /><span>{item.label}</span><span className={styles.navMeta}>{item.meta}</span>
                </button>
              );
            })}
            <button className={styles.navButton} type="button" onClick={() => setAnnouncement('Reports use the selected-report narrative template')}>
              <FileText /><span>Reports</span><span className={styles.navMeta}>6</span>
            </button>
          </nav>
          <div className={styles.railFooter}>
            <div className={styles.railHealth}><i className={styles.healthDot} />Index current</div>
            <span>Local only / synthetic lab data</span>
          </div>
        </aside>

        <main className={styles.workspace}>
          <header className={styles.commandBar}>
            <form className={styles.search} role="search" onSubmit={submitSearch}>
              <Search />
              <input aria-label="Search dashboard" placeholder={`Search ${activeLabel.toLowerCase()} evidence`} value={search} onChange={(event) => setSearch(event.target.value)} />
            </form>
            <div className={styles.commandActions}>
              <button
                aria-expanded={scopeOpen}
                aria-label={`Data scope: ${rowLimit === null ? 'All rows' : `${rowLimit.toLocaleString()} loaded`}, ${history} history`}
                className={styles.scopeButton}
                title="Data scope"
                type="button"
                onClick={() => setScopeOpen((open) => !open)}
              >
                <Database />
                <span className={styles.scopeCopy}><strong>{rowLimit === null ? 'All rows' : `${rowLimit.toLocaleString()} loaded`}</strong><span>42,318 indexed / {history}</span></span>
              </button>
              <StatusBadge className={styles.desktopAction} tone="positive">Live</StatusBadge>
              <IconButton className={refreshing ? feedbackStyles.refreshing : undefined} aria-label="Refresh data" disabled={refreshing} onClick={startRefresh}><RefreshCw /></IconButton>
            </div>
          </header>

          {scopeOpen ? (
            <DataScopePopover
              currentHistory={history}
              currentRows={rowLimit}
              dataState={dataState}
              refreshing={refreshing}
              onApply={applyScope}
              onCancelRefresh={cancelRefresh}
              onClose={() => setScopeOpen(false)}
              onPreviewStateChange={previewState}
              onRefresh={startRefresh}
            />
          ) : null}

          <div className={styles.content}>
            {dataState !== 'ready' ? (
              <ContractStatePanel
                state={dataState}
                onOpenScope={() => setScopeOpen(true)}
                onRetry={startRefresh}
              />
            ) : null}
            {!blocksScenario && view === 'overview' ? <OverviewScenario onAnnounce={setAnnouncement} onNavigate={navigate} onSelectCall={(call) => { selectCall(call); navigate('call'); }} /> : null}
            {!blocksScenario && view === 'explore' ? <ExploreScenario onAnnounce={setAnnouncement} onNavigate={navigate} onSelectCall={selectCall} selectedCall={selectedCall} /> : null}
            {!blocksScenario && view === 'investigate' ? <InvestigateScenario onAnnounce={setAnnouncement} onNavigate={navigate} /> : null}
            {!blocksScenario && view === 'limits' ? <LimitsScenario onAnnounce={setAnnouncement} onNavigate={navigate} /> : null}
            {!blocksScenario && view === 'call' ? <CallScenario call={selectedCall} onAnnounce={setAnnouncement} onNavigate={navigate} /> : null}
          </div>
        </main>
      </div>

      <nav className={styles.mobileNav} aria-label="Mobile visual contract navigation">
        {navigation.map((item) => {
          const Icon = item.icon;
          return <button data-active={item.id === view} key={item.id} type="button" onClick={() => navigate(item.id)}><Icon /><span>{item.label}</span></button>;
        })}
        <button type="button" aria-expanded={scopeOpen} onClick={() => setScopeOpen(true)}><MoreHorizontal /><span>More</span></button>
      </nav>

      {announcement ? <div className={feedbackStyles.announcement} role="status" aria-live="polite">{announcement}</div> : null}
    </div>
  );
}
