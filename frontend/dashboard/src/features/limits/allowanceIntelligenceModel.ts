import type {
  AllowanceEvidenceRow,
  AllowanceStatusPayload,
  AllowanceStatusWindow,
} from '../../api/types';

type ReadoutKind = 'observed' | 'estimated' | 'unavailable';

type MetricReadout = {
  label: string;
  value: string;
  detail: string;
  grade: string;
  kind: ReadoutKind;
};

export type AllowanceReadout = {
  primary: MetricReadout;
  weekly: MetricReadout;
  fiveHour: MetricReadout;
  reset: MetricReadout;
  capacity: MetricReadout;
  forecast: MetricReadout;
  pace: MetricReadout;
};

export function buildAllowanceReadout(status: AllowanceStatusPayload | undefined): AllowanceReadout {
  const weekly = windowReadout('Weekly observed', status?.weekly);
  const fiveHour = windowReadout('5-hour observed', status?.five_hour);
  const estimation = status?.estimation;
  const estimate = estimation?.weekly_estimate;
  const hasEstimate = estimate?.used_percent !== null && estimate?.used_percent !== undefined;
  const primary: MetricReadout = hasEstimate
    ? {
        label: 'Weekly reconstructed use',
        value: percent(estimate.used_percent),
        detail: `${weekly.value} observed at ${timeLabel(status?.weekly?.observed_at)}; ${number(estimate.post_observation_credits)} priced credits added since that anchor.`,
        grade: 'Estimated',
        kind: 'estimated',
      }
    : {
        ...weekly,
        label: 'Weekly observed use',
      };
  const capacity = estimation?.capacity;
  const capacityReadout: MetricReadout = capacity?.credits_per_percent !== null
    && capacity?.credits_per_percent !== undefined
    ? {
        label: 'Personal calibration',
        value: `${number(capacity.credits_per_percent)} credits / 1%`,
        detail: `Personal historical calibration from ${capacity.completed_cycle_count} completed cycles; ${percent(capacity.price_coverage * 100)} priced interval coverage.`,
        grade: titleCase(capacity.status),
        kind: 'estimated',
      }
    : unavailable('Personal calibration', 'More complete cycles with priced usage are required.', 'Descriptive');
  const forecast = estimation?.forecast;
  const forecastReadout: MetricReadout = forecast?.used_percent !== null
    && forecast?.used_percent !== undefined
    && forecast.quantiles
    ? {
        label: 'Validated weekly estimate',
        value: percent(forecast.used_percent),
        detail: `${number(forecast.quantiles.p10)}–${percent(forecast.quantiles.p90)} time-ordered holdout interval · ${forecast.sample_size ?? 0} holdout samples.`,
        grade: 'Validated',
        kind: 'estimated',
      }
    : unavailable(
        'Validated weekly estimate',
        'Forecast withheld until the personal model passes time-ordered validation.',
        'Observed only',
      );
  const pace = estimation?.pace_scenarios;
  const paceReadout: MetricReadout = pace?.status === 'conditional'
    && pace.if_current_pace_continues !== null
    ? {
        label: 'Conditional pace',
        value: `${number(pace.if_current_pace_continues)}% / hour`,
        detail: `${number(pace.low)}–${number(pace.high)}% / hour if recent local pace continues · ${pace.sample_count} samples.`,
        grade: 'Conditional',
        kind: 'estimated',
      }
    : unavailable('Conditional pace', 'Not enough comparable recent pace windows.', 'Observed only');
  return {
    primary,
    weekly,
    fiveHour,
    reset: resetReadout(status?.weekly),
    capacity: capacityReadout,
    forecast: forecastReadout,
    pace: paceReadout,
  };
}

export function sortAllowanceEvidenceRows(rows: AllowanceEvidenceRow[]): AllowanceEvidenceRow[] {
  return [...rows].sort((left, right) => (
    Date.parse(right.end_observed_at) - Date.parse(left.end_observed_at)
  ));
}

function windowReadout(label: string, window: AllowanceStatusWindow | null | undefined): MetricReadout {
  if (!window || window.used_percent === null) {
    return unavailable(label, 'No local observation is available for this window.', 'No data');
  }
  return {
    label,
    value: percent(window.used_percent),
    detail: `${titleCase(window.freshness)} · observed ${timeLabel(window.observed_at)}`,
    grade: titleCase(window.freshness),
    kind: 'observed',
  };
}

function resetReadout(window: AllowanceStatusWindow | null | undefined): MetricReadout {
  if (!window || window.reset_countdown_seconds === null) {
    return unavailable('Weekly reset', 'No reset timestamp is available.', 'Unknown');
  }
  return {
    label: 'Weekly reset',
    value: duration(window.reset_countdown_seconds),
    detail: window.reset_at ? `Expected ${timeLabel(new Date(window.reset_at * 1_000).toISOString())}` : 'Countdown from latest observation',
    grade: titleCase(window.freshness),
    kind: 'observed',
  };
}

function unavailable(label: string, detail: string, grade: string): MetricReadout {
  return { label, value: 'Unavailable', detail, grade, kind: 'unavailable' };
}

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? 'Unavailable' : `${number(value)}%`;
}

function number(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

function duration(seconds: number): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  return days > 0 ? `${days}d ${hours}h` : `${hours}h`;
}

function timeLabel(value: string | undefined): string {
  if (!value) return 'an unknown time';
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(timestamp);
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase());
}
