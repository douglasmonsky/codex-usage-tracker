export function DrillMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <span className="drilldown-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <em>{detail}</em>
    </span>
  );
}

export function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
