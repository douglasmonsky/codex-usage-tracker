import { useEffect, useMemo, useRef, useState } from 'react';
import type { DashboardModel } from '../../api/types';
import { useEvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { uniqueSorted } from '../shared/filtering';
import {
  summarizeSourceCoverage,
  type CallsSortKey,
  type ConfidenceFilter,
  type SortDirection,
  type SourceFilter,
  type TimeFilter,
} from './callFilterSummary';
import { callsDateRange } from './callsFilterSort';
import {
  buildCallsViewLink,
  cleanCallsDateInput as cleanDateInput,
  coerceCallsSortKey,
  defaultCallsSortDirection,
  readCallsSearchParam,
  readCallsSortKeyParam,
  readConfidenceFilterParam,
  readDateInputParam,
  readDensityParam,
  readInitialSelectedCallId,
  readPageVisibleRowsParam,
  readSortDirectionParam,
  readSourceFilterParam,
  readTimeFilterParam,
  type Density,
} from './callsUrlState';
import {
  readCallsDetailPanelPreference,
  rememberCallsDetailPanelPreference,
} from './callsDetailPanelPreference';

export const callsTablePageSize = 250;

export function useCallsExplorerControls(model: DashboardModel, globalQuery: string) {
  const densityParam = readCallsSearchParam('density');
  const [localQuery, setLocalQuery] = useState(() => readCallsSearchParam('call_q'));
  const [modelFilter, setModelFilter] = useState(() => readCallsSearchParam('model') || 'all');
  const [effortFilter, setEffortFilter] = useState(() => readCallsSearchParam('effort') || 'all');
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>(() => readConfidenceFilterParam());
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>(() => readSourceFilterParam());
  const [timeFilter, setTimeFilter] = useState<TimeFilter>(() => readTimeFilterParam());
  const [dateStart, setDateStart] = useState(() => readDateInputParam('from'));
  const [dateEnd, setDateEnd] = useState(() => readDateInputParam('to'));
  const [sortKey, setSortKey] = useState<CallsSortKey>(() => readCallsSortKeyParam());
  const [sortDirection, setSortDirection] = useState<SortDirection>(
    () => readSortDirectionParam(readCallsSortKeyParam()),
  );
  const gridPreferences = useEvidenceGridPreferences('codexUsageCallsEvidenceGrid', {
    density: readDensityParam() === 'dense' ? 'compact' : 'comfortable',
    columnVisibility: {},
  }, densityParam === 'roomy' ? 'comfortable' : densityParam === 'dense' ? 'compact' : undefined);
  const density: Density = gridPreferences.density === 'compact' ? 'dense' : 'roomy';
  const initialSelectedCallId = useMemo(() => readInitialSelectedCallId(), []);
  const [selectedCallId, setSelectedCallId] = useState<string | null>(initialSelectedCallId);
  const [visibleCallRows, setVisibleCallRows] = useState(() => readPageVisibleRowsParam(callsTablePageSize));
  const [exportStatus, setExportStatus] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [detailsExpanded, setDetailsExpanded] = useState(
    () => readCallsDetailPanelPreference(Boolean(initialSelectedCallId)),
  );
  const searchInputRef = useRef<HTMLInputElement>(null);
  const previousGlobalQueryRef = useRef(globalQuery);
  const modelOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.model)), [model.calls]);
  const effortOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.effort)), [model.calls]);
  const sourceCoverage = useMemo(() => summarizeSourceCoverage(model.calls), [model.calls]);
  const dateRangeStatus = useMemo(
    () => callsDateRange(timeFilter, dateStart, dateEnd, new Date()),
    [dateEnd, dateStart, timeFilter],
  );

  useEffect(() => {
    if (previousGlobalQueryRef.current === globalQuery) return;
    previousGlobalQueryRef.current = globalQuery;
    setVisibleCallRows(callsTablePageSize);
  }, [globalQuery]);

  function resetCallTablePage() {
    setVisibleCallRows(callsTablePageSize);
  }

  function updateLocalQuery(value: string) {
    setLocalQuery(value);
    resetCallTablePage();
  }

  function updateModelFilter(value: string) {
    setModelFilter(value);
    resetCallTablePage();
  }

  function updateEffortFilter(value: string) {
    setEffortFilter(value);
    resetCallTablePage();
  }

  function updateConfidenceFilter(value: ConfidenceFilter) {
    setConfidenceFilter(value);
    resetCallTablePage();
  }

  function updateSourceFilter(value: SourceFilter) {
    setSourceFilter(value);
    resetCallTablePage();
  }

  function updateTimeFilter(value: TimeFilter) {
    setTimeFilter(value);
    resetCallTablePage();
  }

  function updateDateStart(value: string) {
    setDateStart(cleanDateInput(value));
    setTimeFilter('custom');
    resetCallTablePage();
  }

  function updateDateEnd(value: string) {
    setDateEnd(cleanDateInput(value));
    setTimeFilter('custom');
    resetCallTablePage();
  }

  function updateSortKey(value: string) {
    const nextSort = coerceCallsSortKey(value);
    setSortKey(nextSort);
    setSortDirection(defaultCallsSortDirection(nextSort));
    resetCallTablePage();
  }

  function updateSortDirection(value: string) {
    setSortDirection(value === 'asc' ? 'asc' : 'desc');
    resetCallTablePage();
  }

  function clearCallFilters() {
    setLocalQuery('');
    setModelFilter('all');
    setEffortFilter('all');
    setConfidenceFilter('all');
    setSourceFilter('all');
    setTimeFilter('all');
    setDateStart('');
    setDateEnd('');
    setSortKey('time');
    setSortDirection(defaultCallsSortDirection('time'));
    gridPreferences.setDensity('compact');
    gridPreferences.setColumnVisibility({});
    setSelectedCallId(null);
    setVisibleCallRows(callsTablePageSize);
    window.history.replaceState(null, '', buildCallsViewLink({
      localQuery: '',
      modelFilter: 'all',
      effortFilter: 'all',
      confidenceFilter: 'all',
      sourceFilter: 'all',
      timeFilter: 'all',
      dateStart: '',
      dateEnd: '',
      sortKey: 'time',
      sortDirection: defaultCallsSortDirection('time'),
      density: 'dense',
      selectedRecordId: '',
      visibleRowCount: callsTablePageSize,
      pageSize: callsTablePageSize,
    }));
    setFilterStatus('Calls filters cleared');
  }

  function toggleCallDetails() {
    setDetailsExpanded(expanded => {
      const nextExpanded = !expanded;
      rememberCallsDetailPanelPreference(nextExpanded);
      return nextExpanded;
    });
  }

  return {
    localQuery,
    modelFilter,
    effortFilter,
    confidenceFilter,
    sourceFilter,
    timeFilter,
    dateStart,
    dateEnd,
    sortKey,
    setSortKey,
    sortDirection,
    setSortDirection,
    gridPreferences,
    density,
    initialSelectedCallId,
    selectedCallId,
    setSelectedCallId,
    visibleCallRows,
    setVisibleCallRows,
    exportStatus,
    setExportStatus,
    filterStatus,
    detailsExpanded,
    searchInputRef,
    modelOptions,
    effortOptions,
    sourceCoverage,
    dateRangeStatus,
    resetCallTablePage,
    updateLocalQuery,
    updateModelFilter,
    updateEffortFilter,
    updateConfidenceFilter,
    updateSourceFilter,
    updateTimeFilter,
    updateDateStart,
    updateDateEnd,
    updateSortKey,
    updateSortDirection,
    clearCallFilters,
    toggleCallDetails,
  };
}
