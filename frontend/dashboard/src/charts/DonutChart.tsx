import type { DonutDatum } from '../api/types';

export function DonutChart({ data, centerLabel }: { data: DonutDatum[]; centerLabel: string }) {
  const total = data.reduce((sum, item) => sum + item.value, 0) || 1;
  let offset = 25;

  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 160 160" className="donut" role="img" aria-label={`${centerLabel} composition`}>
        <circle cx="80" cy="80" r="52" fill="none" stroke="#e5eaf3" strokeWidth="28" />
        {data.map(item => {
          const dash = (item.value / total) * 326.73;
          const segment = (
            <circle
              key={item.label}
              cx="80"
              cy="80"
              r="52"
              fill="none"
              stroke={item.color}
              strokeDasharray={`${dash} 326.73`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
              strokeWidth="28"
              transform="rotate(-90 80 80)"
            />
          );
          offset += dash;
          return segment;
        })}
        <text x="80" y="76" textAnchor="middle" className="donut-value">
          {centerLabel}
        </text>
        <text x="80" y="96" textAnchor="middle" className="donut-label">
          total
        </text>
      </svg>
      <div className="donut-legend">
        {data.map(item => (
          <span key={item.label}>
            <i style={{ backgroundColor: item.color }} />
            {item.label} {Math.round((item.value / total) * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}
