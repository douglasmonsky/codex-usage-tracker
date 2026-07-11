import { BarChart3, Download, Table2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';

import {
  tableRowsForVisualization,
  validateVisualizationSpec,
  visualizationAriaDescription,
  type VisualizationSpecV1,
} from '../spec';
import type { EChartsVisualizationRenderer } from '../renderer/echartsRenderer';
import { VisualizationState, shouldRenderVisualizationData } from './VisualizationState';
import { selectedVisualizationLabel, VisualizationTable } from './VisualizationTable';
import styles from './Visualization.module.css';

export type VisualizationView = 'chart' | 'table';

type VisualizationProps = {
  defaultView?: VisualizationView;
  height?: number;
  onSelectionChange?: (key: string) => void;
  spec: VisualizationSpecV1;
};

export function Visualization({ defaultView = 'chart', height = 360, onSelectionChange, spec }: VisualizationProps) {
  const chartElementRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<EChartsVisualizationRenderer | null>(null);
  const [view, setView] = useState<VisualizationView>(defaultView);
  const [rendererState, setRendererState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const issues = useMemo(() => validateVisualizationSpec(spec), [spec]);
  const rows = useMemo(() => tableRowsForVisualization(spec), [spec]);
  const canRenderData = issues.length === 0 && shouldRenderVisualizationData(spec) && rows.length > 0;
  const selectedLabel = selectedVisualizationLabel(spec, selectedKey);

  useEffect(() => {
    setSelectedKey(current => (current && rows.some(row => row.key === current) ? current : rows[0]?.key ?? null));
  }, [rows]);

  useEffect(() => {
    rendererRef.current?.select(selectedKey);
  }, [selectedKey]);

  useEffect(() => {
    const element = chartElementRef.current;
    if (view !== 'chart' || !canRenderData || !element) return;
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    const abortController = new AbortController();
    setRendererState('loading');

    void import('../renderer/echartsRenderer')
      .then(({ createEChartsVisualizationRenderer }) => {
        if (cancelled) return;
        return createEChartsVisualizationRenderer(
          element,
          spec,
          selectKey,
          { animate: !prefersReducedMotion(), signal: abortController.signal },
        );
      })
      .then(renderer => {
        if (!renderer) return;
        if (cancelled) {
          renderer.dispose();
          return;
        }
        rendererRef.current = renderer;
        renderer.select(selectedKey);
        observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => renderer.resize());
        observer?.observe(element);
        setRendererState('ready');
      })
      .catch(() => {
        if (!cancelled) setRendererState('error');
      });

    return () => {
      cancelled = true;
      abortController.abort();
      observer?.disconnect();
      rendererRef.current?.dispose();
      rendererRef.current = null;
    };
  }, [canRenderData, spec, view]);

  function selectKey(key: string) {
    setSelectedKey(key);
    onSelectionChange?.(key);
  }

  function handleChartKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!rows.length) return;
    const currentIndex = Math.max(0, rows.findIndex(row => row.key === selectedKey));
    const direction = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0;
    if (!direction && event.key !== 'Home' && event.key !== 'End') return;
    event.preventDefault();
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : Math.max(0, Math.min(rows.length - 1, currentIndex + direction));
    selectKey(rows[nextIndex].key);
  }

  function exportSvg() {
    const dataUrl = rendererRef.current?.exportSvgDataUrl();
    if (!dataUrl) return;
    const anchor = document.createElement('a');
    anchor.href = dataUrl;
    anchor.download = `codex-${spec.id}.svg`;
    anchor.click();
  }

  const titleId = `${spec.id}-title`;
  const descriptionId = `${spec.id}-description`;

  return (
    <section
      className={styles.root}
      aria-labelledby={titleId}
      data-visualization-id={spec.id}
      data-visualization-state={spec.state.kind}
    >
      <header className={styles.header}>
        <div>
          <h3 id={titleId}>{spec.title}</h3>
          {spec.description ? <p>{spec.description}</p> : null}
        </div>
        <div className={styles.toolbar}>
          <div className={styles.segmented} role="group" aria-label="Visualization view">
            <button type="button" aria-label="Chart view" title="Chart view" aria-pressed={view === 'chart'} onClick={() => setView('chart')}>
              <BarChart3 size={16} />
            </button>
            <button type="button" aria-label="Table view" title="Table view" aria-pressed={view === 'table'} onClick={() => setView('table')}>
              <Table2 size={16} />
            </button>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            aria-label="Export visualization as SVG"
            title="Export SVG"
            disabled={view !== 'chart' || rendererState !== 'ready'}
            onClick={exportSvg}
          >
            <Download size={16} />
          </button>
        </div>
      </header>

      <div className={styles.meta}>
        <span>{spec.scope.label}</span>
        <span>{spec.scope.rowCount.toLocaleString()} evidence rows</span>
        <span>Updated {formatFreshness(spec.freshness.generatedAt)}</span>
      </div>

      {issues.length ? (
        <div className={styles.state} data-state="error" role="alert">
          <strong>Visualization contract error</strong>
          <span>{issues[0].path}: {issues[0].message}</span>
        </div>
      ) : null}

      {!issues.length && !shouldRenderVisualizationData(spec) ? <VisualizationState spec={spec} /> : null}
      {!issues.length && (spec.state.kind === 'partial' || spec.state.kind === 'stale') ? <VisualizationState spec={spec} /> : null}

      {canRenderData && view === 'chart' ? (
        <div
          className={styles.chartRegion}
          style={{ minHeight: height }}
          role="region"
          tabIndex={0}
          aria-describedby={descriptionId}
          aria-label={`${spec.title} chart`}
          aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown Home End"
          onKeyDown={handleChartKeyDown}
        >
          <div
            ref={chartElementRef}
            className={styles.chart}
            style={{ height }}
            data-testid="visualization-chart"
            aria-hidden="true"
          />
          {rendererState === 'loading' ? <div className={styles.chartStatus}>Loading renderer...</div> : null}
          {rendererState === 'error' ? <div className={styles.chartStatus}>Chart unavailable. Use the synchronized table view.</div> : null}
        </div>
      ) : null}

      {canRenderData && view === 'table' ? (
        <VisualizationTable spec={spec} selectedKey={selectedKey} onSelectionChange={selectKey} />
      ) : null}

      <footer className={styles.summary} id={descriptionId}>
        <strong>{spec.accessibility.summary}</strong>
        {selectedLabel ? <span aria-live="polite">Selected {selectedLabel}</span> : null}
        <span className={styles.screenReaderOnly}>{visualizationAriaDescription(spec)}</span>
        {spec.caveats?.length ? <span>{spec.caveats[0]}</span> : null}
      </footer>
    </section>
  );
}

function prefersReducedMotion() {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function formatFreshness(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
