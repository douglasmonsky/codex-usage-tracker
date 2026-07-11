import type { UsageConstellationModel } from './types';
import styles from './UsageConstellation.module.css';

type UsageConstellationTableProps = {
  model: UsageConstellationModel;
  onOpenCall: (recordId: string) => void;
};

export function UsageConstellationTable({ model, onOpenCall }: UsageConstellationTableProps) {
  return (
    <div className={styles.tableFrame} role="region" aria-label="Usage constellation evidence" tabIndex={0}>
      <table>
        <thead>
          <tr>
            <th scope="col">Call</th>
            <th scope="col">Time</th>
            <th scope="col">Model</th>
            <th scope="col">Tokens</th>
            <th scope="col">Cache reuse</th>
            <th scope="col">Thread</th>
          </tr>
        </thead>
        <tbody>
          {model.points.map(point => (
            <tr key={point.id}>
              <th scope="row">
                <button type="button" onClick={() => onOpenCall(point.recordId)}>
                  Open call
                </button>
              </th>
              <td>{formatTimestamp(point.timestamp)}</td>
              <td><span className={styles.tableSwatch} style={{ backgroundColor: point.color }} />{point.model}</td>
              <td>{point.totalTokens.toLocaleString()}</td>
              <td>{Math.round(point.cachedPercent)}%</td>
              <td>{point.thread}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatTimestamp(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value || 'Unknown';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(timestamp);
}
