import { Filter, X } from 'lucide-react';
import { useMemo } from 'react';
import type { DashboardModel } from '../api/types';
import { readLegacyShellFilters } from './legacyShellFilters';
import type { ViewId } from './navigation';

type ShellGlobalFiltersProps = {
  activeView: ViewId;
  locationSearch: string;
  model: DashboardModel;
  onUrlChange: (url: URL) => void;
};

const timeOptions = [
  { value: 'all', label: 'All time' },
  { value: 'today', label: 'Today' },
  { value: 'this-week', label: 'This week' },
  { value: 'last-7-days', label: 'Last 7 days' },
  { value: 'this-month', label: 'This month' },
  { value: 'custom', label: 'Custom' },
];

const confidenceOptions = [
  { value: 'all', label: 'All confidence' },
  { value: 'cost-exact', label: 'Exact cost' },
  { value: 'cost-estimated', label: 'Estimated cost' },
  { value: 'cost-unpriced', label: 'Unpriced cost' },
  { value: 'credit-exact', label: 'Exact credit' },
  { value: 'credit-estimated', label: 'Estimated credit' },
  { value: 'credit-override', label: 'Credit override' },
  { value: 'credit-missing', label: 'Missing credit' },
];

export function ShellGlobalFilters({ activeView, locationSearch, model, onUrlChange }: ShellGlobalFiltersProps) {
  const filters = readLegacyShellFilters(locationSearch);
  const modelOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.model)), [model.calls]);
  const effortOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.effort)), [model.calls]);
  const timeValue = filters.dateStart || filters.dateEnd ? 'custom' : normalizeTimeValue(filters.datePreset);
  const dateStatus = dateFilterStatus(filters, timeValue);

  if (activeView === 'calls' || activeView === 'call' || !model.calls.length) {
    return null;
  }

  function updateUrl(mutator: (url: URL) => void) {
    const url = new URL(window.location.href);
    mutator(url);
    onUrlChange(url);
  }

  function updateSelectParam(name: string, value: string) {
    updateUrl(url => {
      if (name === 'confidence') {
        url.searchParams.delete('pricing');
      }
      if (!value || value === 'all') {
        url.searchParams.delete(name);
      } else {
        url.searchParams.set(name, value);
      }
    });
  }

  function updateTimeFilter(value: string) {
    updateUrl(url => {
      if (!value || value === 'all') {
        url.searchParams.delete('date');
        url.searchParams.delete('time');
        url.searchParams.delete('from');
        url.searchParams.delete('to');
        return;
      }
      url.searchParams.set('date', value);
      url.searchParams.set('time', value);
      if (value !== 'custom') {
        url.searchParams.delete('from');
        url.searchParams.delete('to');
      }
    });
  }

  function updateDateBound(name: 'from' | 'to', value: string) {
    updateUrl(url => {
      if (value) {
        url.searchParams.set(name, value);
        url.searchParams.set('date', 'custom');
        url.searchParams.set('time', 'custom');
      } else {
        url.searchParams.delete(name);
        if (!url.searchParams.get('from') && !url.searchParams.get('to')) {
          url.searchParams.delete('date');
          url.searchParams.delete('time');
        }
      }
    });
  }

  function clearFilters() {
    updateUrl(url => {
      for (const name of ['model', 'effort', 'confidence', 'pricing', 'date', 'time', 'from', 'to']) {
        url.searchParams.delete(name);
      }
    });
  }

  return (
    <section className="global-filter-strip span-all" aria-label="Dashboard filters">
      <strong>
        <Filter size={15} />
        Filters
      </strong>
      <label>
        <span>Model</span>
        <select
          aria-label="Global model filter"
          value={filters.model || 'all'}
          onChange={event => updateSelectParam('model', event.target.value)}
        >
          <option value="all">All models</option>
          {modelOptions.map(option => (
            <option value={option} key={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Effort</span>
        <select
          aria-label="Global effort filter"
          value={filters.effort || 'all'}
          onChange={event => updateSelectParam('effort', event.target.value)}
        >
          <option value="all">All effort</option>
          {effortOptions.map(option => (
            <option value={option} key={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Confidence</span>
        <select
          aria-label="Global confidence filter"
          value={normalizeConfidenceValue(filters.confidence)}
          onChange={event => updateSelectParam('confidence', event.target.value)}
        >
          {confidenceOptions.map(option => (
            <option value={option.value} key={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Time</span>
        <select aria-label="Global time filter" value={timeValue} onChange={event => updateTimeFilter(event.target.value)}>
          {timeOptions.map(option => (
            <option value={option.value} key={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {dateStatus ? (
          <span className="filter-status" data-state={dateStatus.state} aria-live="polite">
            {dateStatus.label}
          </span>
        ) : null}
      </label>
      <label>
        <span>Start</span>
        <input
          aria-label="Global start date"
          type="date"
          value={filters.dateStart}
          onChange={event => updateDateBound('from', event.target.value)}
        />
      </label>
      <label>
        <span>End</span>
        <input
          aria-label="Global end date"
          type="date"
          value={filters.dateEnd}
          onChange={event => updateDateBound('to', event.target.value)}
        />
      </label>
      <button className="toolbar-button" type="button" disabled={!filters.active} onClick={clearFilters}>
        <X size={15} />
        Clear filters
      </button>
    </section>
  );
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.map(value => value.trim()).filter(Boolean))).sort((left, right) =>
    left.localeCompare(right),
  );
}

function normalizeTimeValue(value: string): string {
  return timeOptions.some(option => option.value === value) ? value : 'all';
}

function normalizeConfidenceValue(value: string): string {
  if (value === 'official') return 'cost-exact';
  if (value === 'estimated') return 'cost-estimated';
  if (value === 'unpriced') return 'cost-unpriced';
  return confidenceOptions.some(option => option.value === value) ? value : 'all';
}

type DateFilterStatus = {
  label: string;
  state: 'active' | 'error';
};

function dateFilterStatus(filters: ReturnType<typeof readLegacyShellFilters>, timeValue: string): DateFilterStatus | null {
  const start = parseDateInput(filters.dateStart);
  const end = parseDateInput(filters.dateEnd);
  if (start !== null && end !== null && start > end) {
    return { label: 'Invalid date range', state: 'error' };
  }
  if (timeValue === 'custom' && (filters.dateStart || filters.dateEnd)) {
    return { label: customDateLabel(filters.dateStart, filters.dateEnd), state: 'active' };
  }
  if (timeValue !== 'all') {
    const label = timeOptions.find(option => option.value === timeValue)?.label ?? timeValue;
    const range = presetDateRange(timeValue);
    return {
      label: range ? `${label}: ${localDateKey(range.start)} to ${localDateKey(addDays(range.endExclusive, -1))}` : label,
      state: 'active',
    };
  }
  return null;
}

function customDateLabel(start: string, end: string): string {
  if (start && end) return `Custom: ${start} to ${end}`;
  if (start) return `Custom: from ${start}`;
  if (end) return `Custom: through ${end}`;
  return 'Custom range';
}

function presetDateRange(preset: string): { start: Date; endExclusive: Date } | null {
  const today = localDay();
  if (preset === 'today') return { start: today, endExclusive: addDays(today, 1) };
  if (preset === 'this-week') {
    const start = weekStart(today);
    return { start, endExclusive: addDays(start, 7) };
  }
  if (preset === 'last-7-days') return { start: addDays(today, -6), endExclusive: addDays(today, 1) };
  if (preset === 'this-month') {
    return {
      start: new Date(today.getFullYear(), today.getMonth(), 1),
      endExclusive: new Date(today.getFullYear(), today.getMonth() + 1, 1),
    };
  }
  return null;
}

function localDay(value = new Date()): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function weekStart(date: Date): Date {
  const day = date.getDay();
  return addDays(date, day === 0 ? -6 : 1 - day);
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function localDateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function parseDateInput(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date.getTime();
}
