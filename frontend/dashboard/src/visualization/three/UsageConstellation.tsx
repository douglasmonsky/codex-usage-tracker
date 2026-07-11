import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { LoaderCircle, RotateCcw } from 'lucide-react';

import { IconButton, SegmentedControl, StatusBadge } from '../../design';
import styles from './UsageConstellation.module.css';
import { UsageConstellationTable } from './UsageConstellationTable';
import type { UsageConstellationModel } from './types';

const LazyUsageConstellationCanvas = lazy(() => import('./UsageConstellationCanvas'));
type DisplayMode = 'space' | 'table';

type UsageConstellationProps = {
  model: UsageConstellationModel;
  onOpenCall: (recordId: string) => void;
};

export function UsageConstellation({ model, onOpenCall }: UsageConstellationProps) {
  const sectionRef = useRef<HTMLElement>(null);
  const [mode, setMode] = useState<DisplayMode>(import.meta.env.MODE === 'test' ? 'table' : 'space');
  const [shouldLoadCanvas, setShouldLoadCanvas] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [resetSignal, setResetSignal] = useState(0);

  useEffect(() => {
    if (mode !== 'space' || shouldLoadCanvas) return;
    const section = sectionRef.current;
    if (!section || typeof IntersectionObserver === 'undefined') {
      setShouldLoadCanvas(true);
      return;
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setShouldLoadCanvas(true);
        observer.disconnect();
      }
    }, { rootMargin: '420px 0px' });
    observer.observe(section);
    return () => observer.disconnect();
  }, [mode, shouldLoadCanvas]);

  const showTableFallback = useCallback(() => {
    setUnavailable(true);
    setMode('table');
  }, []);

  const options = [
    { value: 'space' as const, label: 'Constellation', disabled: unavailable },
    { value: 'table' as const, label: 'Evidence table' },
  ];

  return (
    <section ref={sectionRef} className={styles.section} aria-labelledby="usage-constellation-title" data-testid="usage-constellation">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Spatial evidence</p>
          <h2 id="usage-constellation-title">Usage constellation</h2>
          <p className={styles.question}>Where do high-volume, low-cache calls cluster over time?</p>
        </div>
        <div className={styles.controls}>
          <StatusBadge tone={model.sampled ? 'context' : 'positive'}>
            {model.sampled ? `${model.points.length.toLocaleString()} representative calls` : 'All loaded calls'}
          </StatusBadge>
          <div className={styles.viewControls}>
            <SegmentedControl label="Usage constellation display" options={options} value={mode} onValueChange={setMode} />
            {mode === 'space' ? (
              <IconButton aria-label="Reset constellation view" title="Reset view" onClick={() => setResetSignal(value => value + 1)}>
                <RotateCcw />
              </IconButton>
            ) : null}
          </div>
        </div>
      </header>

      <div className={styles.legend} aria-label="Model color legend">
        {model.legend.map(item => (
          <span key={item.label}><i style={{ backgroundColor: item.color }} />{item.label}<small>{item.count.toLocaleString()}</small></span>
        ))}
      </div>

      {model.points.length < 3 ? (
        <div className={styles.emptyState} role="status">At least three loaded calls are needed to map the constellation.</div>
      ) : mode === 'table' ? (
        <UsageConstellationTable model={model} onOpenCall={onOpenCall} />
      ) : (
        <div className={styles.stage} role="img" aria-label={model.accessibleSummary}>
          {shouldLoadCanvas ? (
            <Suspense fallback={<ConstellationLoading />}>
              <LazyUsageConstellationCanvas
                model={model}
                onOpenCall={onOpenCall}
                onUnavailable={showTableFallback}
                resetSignal={resetSignal}
              />
            </Suspense>
          ) : <ConstellationLoading />}
          <div className={styles.axes} aria-hidden="true">
            <span>Earlier to recent</span>
            <span>Height: token volume</span>
            <span>Depth: cache reuse</span>
          </div>
        </div>
      )}

      <p className={styles.summary}>{unavailable ? '3D rendering is unavailable, so the synchronized evidence table is shown. ' : ''}{model.accessibleSummary}</p>
    </section>
  );
}

function ConstellationLoading() {
  return <div className={styles.loading} role="status"><LoaderCircle aria-hidden="true" /> Loading constellation...</div>;
}
