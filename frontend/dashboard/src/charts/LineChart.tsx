import { max } from 'd3-array';
import { scaleLinear, scalePoint } from 'd3-scale';
import { line } from 'd3-shape';
import { useLayoutEffect, useRef, useState } from 'react';

import type { Series } from '../api/types';
import { useShellI18n } from '../app/i18nContext';

type LineChartProps = {
  series: Series[];
  yLabel: string;
  valueFormatter?: (value: number) => string;
  height?: number;
};

const dateLabelWidth = 38;

export function LineChart({ series, yLabel, valueFormatter = defaultFormatter, height = 280 }: LineChartProps) {
  const i18n = useShellI18n();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [viewportWidth, setViewportWidth] = useState(0);
  const labels = series[0]?.points.map(point => point.label) ?? [];
  const minWidth = labels.length <= 1 ? 360 : labels.length <= 4 ? 520 : 760;
  const width = Math.max(minWidth, labels.length * dateLabelWidth, viewportWidth);
  const margin = { top: 24, right: 56, bottom: 54, left: 72 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const allValues = series.flatMap(item =>
    item.points.flatMap(point => [point.value, point.low, point.high].filter(isNumber)),
  );
  const maxValue = max(allValues) ?? 1;
  const y = scaleLinear()
    .domain([0, maxValue * 1.12])
    .nice(4)
    .range([margin.top + innerHeight, margin.top]);
  const x = scalePoint<string>()
    .domain(labels)
    .range([margin.left, margin.left + innerWidth])
    .padding(0.35);
  const pathFor = line<{ label: string; value: number }>()
    .x(point => x(point.label) ?? margin.left)
    .y(point => y(point.value));
  const ticks = y.ticks(4);
  const hasScrollableHistory = labels.length > 1 && (viewportWidth <= 0 || width > viewportWidth + 1);

  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) {
      return;
    }
    const measure = () => {
      const nextWidth = Math.round(scroller.clientWidth);
      if (nextWidth > 0) {
        setViewportWidth(currentWidth => (currentWidth === nextWidth ? currentWidth : nextWidth));
      }
    };
    measure();
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    resizeObserver?.observe(scroller);
    return () => resizeObserver?.disconnect();
  }, []);

  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) {
      return;
    }
    const scrollToRecent = () => {
      scroller.scrollLeft = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
    };
    scrollToRecent();
    const frame = window.requestAnimationFrame(scrollToRecent);
    const timeouts = [80, 250, 600].map(delay => window.setTimeout(scrollToRecent, delay));
    const resizeObserver =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            scrollToRecent();
          });
    resizeObserver?.observe(scroller);
    if (scroller.firstElementChild) {
      resizeObserver?.observe(scroller.firstElementChild);
    }
    return () => {
      window.cancelAnimationFrame(frame);
      timeouts.forEach(timeout => window.clearTimeout(timeout));
      resizeObserver?.disconnect();
    };
  }, [labels.length, width]);

  return (
    <div className="line-chart-frame" role="img" aria-label={i18n.translateText(`${yLabel} line chart`)}>
      {hasScrollableHistory ? <div className="chart-scroll-cue">{i18n.translateText('Recent dates shown. Scroll left for earlier dates.')}</div> : null}
      <div className="chart-scroll-shell">
        <div
          className="chart-scroll"
          ref={scrollRef}
          role="region"
          tabIndex={hasScrollableHistory ? 0 : undefined}
          aria-label={i18n.translateText(`${yLabel} history. Recent dates are shown first; scroll left for earlier dates.`)}
        >
          <svg className="chart" viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
            {ticks.map(tick => (
              <g key={tick}>
                <line x1={margin.left} y1={y(tick)} x2={margin.left + innerWidth} y2={y(tick)} className="grid-line" />
              </g>
            ))}
            <line
              x1={margin.left}
              y1={margin.top + innerHeight}
              x2={margin.left + innerWidth}
              y2={margin.top + innerHeight}
              className="axis-line"
            />
            {labels.map(label => {
              const xValue = x(label) ?? margin.left;
              return (
                <text key={label} x={xValue} y={height - 18} textAnchor="middle" className="axis-text">
                  {label}
                </text>
              );
            })}
            {series.map(item => (
              <g key={item.id}>
                {item.points.map(point =>
                  isNumber(point.low) && isNumber(point.high) ? (
                    <line
                      key={`${item.id}-${point.label}-ci`}
                      x1={x(point.label)}
                      x2={x(point.label)}
                      y1={y(point.low)}
                      y2={y(point.high)}
                      className="confidence-line"
                    />
                  ) : null,
                )}
                <path
                  d={pathFor(item.points) ?? undefined}
                  fill="none"
                  stroke={item.color}
                  strokeDasharray={item.dashed ? '7 7' : undefined}
                  strokeWidth={3}
                />
                {item.points.map(point => (
                  <circle
                    key={`${item.id}-${point.label}`}
                    cx={x(point.label)}
                    cy={y(point.value)}
                    r={4}
                    fill={item.color}
                    stroke="#ffffff"
                    strokeWidth={2}
                  />
                ))}
              </g>
            ))}
          </svg>
        </div>
        <svg
          className="chart-axis-overlay"
          viewBox={`0 0 ${margin.left} ${height}`}
          width={margin.left}
          height={height}
          aria-hidden="true"
        >
          <rect className="chart-axis-bg" width={margin.left} height={height} />
          {ticks.map(tick => (
            <text key={tick} x={margin.left - 10} y={y(tick) + 4} textAnchor="end" className="axis-text">
              {valueFormatter(tick)}
            </text>
          ))}
          <line
            x1={margin.left - 0.5}
            y1={margin.top}
            x2={margin.left - 0.5}
            y2={margin.top + innerHeight}
            className="axis-line"
          />
          <text
            x={18}
            y={margin.top + innerHeight / 2}
            className="axis-label"
            transform={`rotate(-90 18 ${margin.top + innerHeight / 2})`}
          >
            {yLabel}
          </text>
        </svg>
      </div>
      <div className="chart-legend">
        {series.map(item => (
          <span key={item.id}>
            <i style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function defaultFormatter(value: number): string {
  return new Intl.NumberFormat('en-US', {
    notation: value >= 10_000 ? 'compact' : 'standard',
    maximumFractionDigits: 1,
  }).format(value);
}
