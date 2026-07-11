import { Filter, X } from 'lucide-react';
import type { RefObject } from 'react';
import {
  sourceCoverageLabel,
  type CallsDateRange,
  type CallsSortKey,
  type ConfidenceFilter,
  type SortDirection,
  type SourceCoverage,
  type SourceFilter,
  type TimeFilter,
} from './callFilterSummary';
import styles from './CallsPage.module.css';

export type CallsFilterBarProps = {
  searchInputRef: RefObject<HTMLInputElement | null>;
  localQuery: string;
  modelFilter: string;
  effortFilter: string;
  confidenceFilter: ConfidenceFilter;
  sourceFilter: SourceFilter;
  timeFilter: TimeFilter;
  dateStart: string;
  dateEnd: string;
  sortKey: CallsSortKey;
  sortDirection: SortDirection;
  modelOptions: string[];
  effortOptions: string[];
  sourceCoverage: SourceCoverage;
  dateRangeStatus: CallsDateRange;
  onLocalQueryChange(value: string): void;
  onModelFilterChange(value: string): void;
  onEffortFilterChange(value: string): void;
  onConfidenceFilterChange(value: ConfidenceFilter): void;
  onSourceFilterChange(value: SourceFilter): void;
  onTimeFilterChange(value: TimeFilter): void;
  onDateStartChange(value: string): void;
  onDateEndChange(value: string): void;
  onSortKeyChange(value: string): void;
  onSortDirectionChange(value: string): void;
  onClear(): void;
};

export function CallsFilterBar({
  searchInputRef,
  localQuery,
  modelFilter,
  effortFilter,
  confidenceFilter,
  sourceFilter,
  timeFilter,
  dateStart,
  dateEnd,
  sortKey,
  sortDirection,
  modelOptions,
  effortOptions,
  sourceCoverage,
  dateRangeStatus,
  onLocalQueryChange,
  onModelFilterChange,
  onEffortFilterChange,
  onConfidenceFilterChange,
  onSourceFilterChange,
  onTimeFilterChange,
  onDateStartChange,
  onDateEndChange,
  onSortKeyChange,
  onSortDirectionChange,
  onClear,
}: CallsFilterBarProps) {
  return (
    <section className={styles.queryBar} aria-label="Call filters">
      <label className="search-box">
        <span className="sr-only">Search calls</span>
        <input
          ref={searchInputRef}
          value={localQuery}
          onChange={event => onLocalQueryChange(event.target.value)}
          placeholder="Search calls, cwd, projects, models..."
        />
      </label>
      <label className="filter-field">
        <span>Model</span>
        <select value={modelFilter} onChange={event => onModelFilterChange(event.target.value)}>
          <option value="all">All models</option>
          {modelOptions.map(option => <option value={option} key={option}>{option}</option>)}
        </select>
      </label>
      <label className="filter-field">
        <span>Effort</span>
        <select value={effortFilter} onChange={event => onEffortFilterChange(event.target.value)}>
          <option value="all">All effort</option>
          {effortOptions.map(option => <option value={option} key={option}>{option}</option>)}
        </select>
      </label>
      <label className="filter-field">
        <span>Confidence</span>
        <select
          aria-label="Confidence filter"
          value={confidenceFilter}
          onChange={event => onConfidenceFilterChange(event.target.value as ConfidenceFilter)}
        >
          <option value="all">All confidence</option>
          <option value="cost-exact">Exact cost</option>
          <option value="cost-estimated">Estimated cost</option>
          <option value="cost-unpriced">Unpriced cost</option>
          <option value="credit-exact">Exact credit rate</option>
          <option value="credit-estimated">Estimated credit mapping</option>
          <option value="credit-override">User credit override</option>
          <option value="credit-missing">Missing credit rate</option>
        </select>
      </label>
      <label className="filter-field">
        <span>Time</span>
        <select
          aria-label="Time filter"
          value={timeFilter}
          onChange={event => onTimeFilterChange(event.target.value as TimeFilter)}
        >
          <option value="all">All time</option>
          <option value="today">Today</option>
          <option value="this-week">This week</option>
          <option value="last-7-days">Last 7 days</option>
          <option value="this-month">This month</option>
          <option value="custom">Custom range</option>
        </select>
        {dateRangeStatus.active || dateRangeStatus.invalid ? (
          <span
            className="filter-status"
            data-state={dateRangeStatus.invalid ? 'error' : 'active'}
            aria-live="polite"
          >
            {dateRangeStatus.label}
          </span>
        ) : null}
      </label>
      <details className={styles.advancedFilters}>
        <summary><Filter size={16} />More filters</summary>
        <div className={styles.advancedFilterGrid}>
          <label className="filter-field">
            <span>Source</span>
            <select
              aria-label="Source filter"
              value={sourceFilter}
              onChange={event => onSourceFilterChange(event.target.value as SourceFilter)}
            >
              <option value="all">All sources</option>
              <option value="project">Project / cwd</option>
              <option value="session">Session-linked</option>
              <option value="git">Git metadata</option>
              <option value="source-file">Source file</option>
              <option value="missing">Missing source</option>
            </select>
            <span
              className="filter-status"
              data-state={sourceFilter === 'all' ? 'active' : 'filtered'}
              aria-live="polite"
            >
              {sourceCoverageLabel(sourceCoverage, sourceFilter)}
            </span>
          </label>
          <label className="filter-field">
            <span>Start</span>
            <input
              aria-label="Start date"
              type="date"
              value={dateStart}
              onChange={event => onDateStartChange(event.target.value)}
            />
          </label>
          <label className="filter-field">
            <span>End</span>
            <input
              aria-label="End date"
              type="date"
              value={dateEnd}
              onChange={event => onDateEndChange(event.target.value)}
            />
          </label>
          <label className="filter-field">
            <span>Sort</span>
            <select aria-label="Sort calls" value={sortKey} onChange={event => onSortKeyChange(event.target.value)}>
              <option value="time">Newest calls</option>
              <option value="duration">Longest duration</option>
              <option value="gap">Longest gap</option>
              <option value="attention">Needs attention</option>
              <option value="thread">Thread name</option>
              <option value="initiator">Initiated</option>
              <option value="model">Model</option>
              <option value="effort">Reasoning</option>
              <option value="total">Most tokens</option>
              <option value="cached">Cached</option>
              <option value="uncached">Uncached</option>
              <option value="output">Output</option>
              <option value="reasoning">Reasoning output</option>
              <option value="cost">Highest estimated cost</option>
              <option value="usage">Highest Codex credits</option>
              <option value="cache">Lowest cache ratio</option>
              <option value="context">Highest context use</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Direction</span>
            <select
              aria-label="Sort direction"
              value={sortDirection}
              onChange={event => onSortDirectionChange(event.target.value)}
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
        </div>
      </details>
      <button className="toolbar-button" type="button" onClick={onClear}>
        <X size={16} />
        Clear filters
      </button>
    </section>
  );
}
