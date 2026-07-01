import { max } from 'd3-array';
import { scaleLinear, scalePoint } from 'd3-scale';
import { line } from 'd3-shape';

import type { Series } from '../api/types';

type LineChartProps = {
  series: Series[];
  yLabel: string;
  valueFormatter?: (value: number) => string;
  height?: number;
};

export function LineChart({ series, yLabel, valueFormatter = defaultFormatter, height = 280 }: LineChartProps) {
  const labels = series[0]?.points.map(point => point.label) ?? [];
  const width = Math.max(760, labels.length * 112);
  const margin = { top: 24, right: 24, bottom: 54, left: 72 };
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

  return (
    <div className="chart-scroll" role="img" aria-label={`${yLabel} line chart`}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
        {ticks.map(tick => (
          <g key={tick}>
            <line x1={margin.left} y1={y(tick)} x2={margin.left + innerWidth} y2={y(tick)} className="grid-line" />
            <text x={margin.left - 10} y={y(tick) + 4} textAnchor="end" className="axis-text">
              {valueFormatter(tick)}
            </text>
          </g>
        ))}
        <line
          x1={margin.left}
          y1={margin.top + innerHeight}
          x2={margin.left + innerWidth}
          y2={margin.top + innerHeight}
          className="axis-line"
        />
        <line x1={margin.left} y1={margin.top} x2={margin.left} y2={margin.top + innerHeight} className="axis-line" />
        <text
          x={18}
          y={margin.top + innerHeight / 2}
          className="axis-label"
          transform={`rotate(-90 18 ${margin.top + innerHeight / 2})`}
        >
          {yLabel}
        </text>
        {labels.map((label, index) => {
          const xValue = x(label) ?? margin.left;
          const show = labels.length <= 9 || index % Math.ceil(labels.length / 8) === 0;
          return show ? (
            <text key={label} x={xValue} y={height - 18} textAnchor="middle" className="axis-text">
              {label}
            </text>
          ) : null;
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
