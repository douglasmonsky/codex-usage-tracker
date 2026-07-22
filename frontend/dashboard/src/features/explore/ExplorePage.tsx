import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

import { CallsPage, type CallsPageProps } from '../calls/CallsPage';
import { ThreadsPage } from '../threads/ThreadsPage';
import {
  buildExploreModeUrl,
  normalizeExploreUrl,
  readExploreMode,
  type ExploreMode,
} from './exploreState';
import styles from './ExplorePage.module.css';

export type ExplorePageProps = CallsPageProps & {
  globalFilters?: ReactNode;
  threadsModel?: CallsPageProps['model'];
};

const modeOptions: ReadonlyArray<{ mode: ExploreMode; label: string }> = [
  { mode: 'calls', label: 'Calls' },
  { mode: 'threads', label: 'Threads' },
];

export function ExplorePage(props: ExplorePageProps) {
  const { globalFilters, threadsModel, ...callsProps } = props;
  const [mode, setMode] = useState<ExploreMode>(() => readExploreMode());
  const pendingFocus = useRef<ExploreMode | null>(null);
  const callsTab = useRef<HTMLButtonElement>(null);
  const threadsTab = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const normalized = normalizeExploreUrl();
    if (normalized.toString() !== window.location.href) {
      window.history.replaceState(null, '', normalized);
    }
    const syncMode = () => setMode(readExploreMode());
    window.addEventListener('popstate', syncMode);
    return () => window.removeEventListener('popstate', syncMode);
  }, []);

  useEffect(() => {
    if (!pendingFocus.current) return;
    const target = pendingFocus.current === 'calls' ? callsTab.current : threadsTab.current;
    pendingFocus.current = null;
    target?.focus();
  }, [mode]);

  function selectMode(nextMode: ExploreMode, focus = false) {
    if (nextMode === mode) return;
    pendingFocus.current = focus ? nextMode : null;
    const url = buildExploreModeUrl(nextMode);
    window.history.pushState(null, '', url);
    setMode(nextMode);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentMode: ExploreMode) {
    let nextMode: ExploreMode | null = null;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextMode = currentMode === 'calls' ? 'threads' : 'calls';
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextMode = currentMode === 'calls' ? 'threads' : 'calls';
    } else if (event.key === 'Home') {
      nextMode = 'calls';
    } else if (event.key === 'End') {
      nextMode = 'threads';
    }
    if (!nextMode) return;
    event.preventDefault();
    selectMode(nextMode, true);
  }

  return (
    <div className={styles.page}>
      <section className={styles.modeBar} aria-label="Explore evidence browser">
        <div>
          <p className={styles.eyebrow}>Evidence browser</p>
          <strong>Explore calls and threads</strong>
        </div>
        <div className={styles.tabs} role="tablist" aria-label="Explore mode">
          {modeOptions.map(option => (
            <button
              aria-controls={`explore-${option.mode}-panel`}
              aria-selected={mode === option.mode}
              className={mode === option.mode ? styles.activeTab : undefined}
              id={`explore-${option.mode}-tab`}
              key={option.mode}
              onClick={() => selectMode(option.mode)}
              onKeyDown={event => handleTabKeyDown(event, option.mode)}
              ref={option.mode === 'calls' ? callsTab : threadsTab}
              role="tab"
              tabIndex={mode === option.mode ? 0 : -1}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>
      <div
        aria-labelledby={`explore-${mode}-tab`}
        className={styles.panel}
        id={`explore-${mode}-panel`}
        role="tabpanel"
      >
        {mode === 'calls' ? (
          <CallsPage {...callsProps} />
        ) : (
          <ThreadsPage
            model={threadsModel ?? props.model}
            globalQuery={props.globalQuery}
            onOpenInvestigator={props.onOpenInvestigator}
            onCopyCallLink={props.onCopyCallLink}
            globalFilters={globalFilters}
            contextRuntime={props.contextRuntime}
            includeArchived={props.includeArchived}
            sourceKey={props.sourceKey}
            sourceRevision={props.sourceRevision}
            focusedEndpointsEnabled={props.focusedEndpointsEnabled}
          />
        )}
      </div>
    </div>
  );
}
