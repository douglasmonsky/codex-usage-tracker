import { BarChart3, Download, Table2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';

import { useShellI18n } from '../../app/i18nContext';
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
import { localizeVisualizationSpec } from './localizeVisualizationSpec';

export type VisualizationView = 'chart' | 'table';

type VisualizationProps = {
  defaultView?: VisualizationView;
  height?: number;
  onSelectionChange?: (key: string) => void;
  spec: VisualizationSpecV1;
};

export function Visualization({ defaultView = 'chart', height = 360, onSelectionChange, spec }: VisualizationProps) {
  const i18n = useShellI18n();
  const localizedSpec = useMemo(
    () => localizeVisualizationSpec(spec, i18n.translateText),
    [i18n.translateText, spec],
  );
  const chartElementRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<EChartsVisualizationRenderer | null>(null);
  const [view, setView] = useState<VisualizationView>(defaultView);
  const [rendererState, setRendererState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const issues = useMemo(() => validateVisualizationSpec(localizedSpec), [localizedSpec]);
  const rows = useMemo(() => tableRowsForVisualization(localizedSpec), [localizedSpec]);
  const canRenderData = issues.length === 0 && shouldRenderVisualizationData(localizedSpec) && rows.length > 0;
  const selectedLabel = selectedVisualizationLabel(localizedSpec, selectedKey);
  const ariaDescription = visualizationAriaDescription(localizedSpec, i18n.translateText);

  useEffect(() => {
    setSelectedKey(current => (current && rows.some(row => row.key === current) ? current : rows[0]?.key ?? null));
  }, [rows]);

  useEffect(() => {
    rendererRef.current?.select(selectedKey);
  }, [selectedKey]);

  useEffect(() => {
    const element = chartElementRef.current;
    if (view !== 'chart' || !canRenderData || !element) return;
    if (element.clientWidth <= 0 || element.clientHeight <= 0) {
      setRendererState('idle');
      return;
    }
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    const abortController = new AbortController();
    setRendererState('loading');

    void import('../renderer/echartsRenderer')
      .then(({ createEChartsVisualizationRenderer }) => {
        if (cancelled) return;
        return createEChartsVisualizationRenderer(
          element,
          localizedSpec,
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
  }, [canRenderData, localizedSpec, view]);

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
    anchor.download = `codex-${localizedSpec.id}.svg`;
    anchor.click();
  }

  const titleId = `${localizedSpec.id}-title`;
  const descriptionId = `${localizedSpec.id}-description`;

  return (
    <section
      className={styles.root}
      aria-labelledby={titleId}
      data-visualization-id={localizedSpec.id}
      data-visualization-state={localizedSpec.state.kind}
    >
      <header className={styles.header}>
        <div>
          <h3 id={titleId}>{localizedSpec.title}</h3>
          {localizedSpec.description ? <p>{localizedSpec.description}</p> : null}
        </div>
        <div className={styles.toolbar}>
          <div className={styles.segmented} role="group" aria-label={i18n.translateText('Visualization view')}>
            <button type="button" aria-label={i18n.translateText('Chart view')} title={i18n.translateText('Chart view')} aria-pressed={view === 'chart'} onClick={() => setView('chart')}>
              <BarChart3 size={16} />
            </button>
            <button type="button" aria-label={i18n.translateText('Table view')} title={i18n.translateText('Table view')} aria-pressed={view === 'table'} onClick={() => setView('table')}>
              <Table2 size={16} />
            </button>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            aria-label={i18n.translateText('Export visualization as SVG')}
            title={i18n.translateText('Export SVG')}
            disabled={view !== 'chart' || rendererState !== 'ready'}
            onClick={exportSvg}
          >
            <Download size={16} />
          </button>
        </div>
      </header>

      <div className={styles.meta}>
        <span>{localizedSpec.scope.label}</span>
        <span>{i18n.translateText(`${localizedSpec.scope.rowCount.toLocaleString()} evidence rows`)}</span>
        <span>{i18n.translateText(`Updated ${formatFreshness(localizedSpec.freshness.generatedAt)}`)}</span>
      </div>

      {issues.length ? (
        <div className={styles.state} data-state="error" role="alert">
          <strong>{i18n.translateText('Visualization contract error')}</strong>
          <span>{i18n.translateText(issues[0].path)}：{i18n.translateText(issues[0].message)}</span>
        </div>
      ) : null}

      {!issues.length && !shouldRenderVisualizationData(localizedSpec) ? <VisualizationState spec={localizedSpec} /> : null}
      {!issues.length && (localizedSpec.state.kind === 'partial' || localizedSpec.state.kind === 'stale') ? <VisualizationState spec={localizedSpec} /> : null}

      {canRenderData && view === 'chart' ? (
        <div
          className={styles.chartRegion}
          style={{ minHeight: height }}
          role="region"
          tabIndex={0}
          aria-describedby={descriptionId}
          aria-label={i18n.translateText(`${localizedSpec.title} chart`)}
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
          {rendererState === 'loading' ? <div className={styles.chartStatus}>{i18n.translateText('Loading renderer...')}</div> : null}
          {rendererState === 'error' ? <div className={styles.chartStatus}>{i18n.translateText('Chart unavailable. Use the synchronized table view.')}</div> : null}
        </div>
      ) : null}

      {canRenderData && view === 'table' ? (
        <VisualizationTable spec={localizedSpec} selectedKey={selectedKey} onSelectionChange={selectKey} />
      ) : null}

      <footer className={styles.summary} id={descriptionId}>
        <strong>{localizedSpec.accessibility.summary}</strong>
        {selectedLabel ? <span aria-live="polite">{i18n.translateText('Selected')} {selectedLabel}</span> : null}
        <span className={styles.screenReaderOnly}>{ariaDescription}</span>
        {localizedSpec.caveats?.length ? <span>{localizedSpec.caveats[0]}</span> : null}
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
