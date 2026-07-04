import type { BarDatum } from '../api/types';

type BarChartProps = {
  data: BarDatum[];
  valueLabel?: (value: number) => string;
};

export function BarChart({ data, valueLabel = value => String(value) }: BarChartProps) {
  const max = Math.max(...data.map(item => item.value), 1);
  return (
    <div className="bar-list">
      {data.map(item => (
        <div className="bar-row" key={item.label}>
          <span>{item.label}</span>
          <div className="bar-track" aria-hidden="true">
            <i
              style={{
                width: `${(item.value / max) * 100}%`,
                backgroundColor: item.color ?? '#2563eb',
              }}
            />
          </div>
          <strong>{valueLabel(item.value)}</strong>
        </div>
      ))}
    </div>
  );
}
