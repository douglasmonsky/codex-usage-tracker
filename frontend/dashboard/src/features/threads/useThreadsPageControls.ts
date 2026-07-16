import type { SortingState } from '@tanstack/react-table';
import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import {
  buildThreadsViewLink,
  defaultThreadCallSortDirection,
  normalizeThreadCallSort,
  readInitialSelectedThreadParam,
  readThreadCallSortDirectionParam,
  readThreadCallSortParam,
  readThreadPageVisibleRowsParam,
  readThreadRiskParam,
  readThreadSearchParam,
  readThreadSortingParam,
  threadsTablePageSize,
  type ThreadCallSortDirection,
  type ThreadCallSortKey,
} from './threadsUrlState';
import { normalizeThreadRiskFilter, type ThreadRiskFilter } from './threadFilterSummary';
import type { ThreadEvidenceViewMode } from './ThreadsExplorerView';

export interface ThreadsPageControls {
  localQuery: string;
  riskFilter: ThreadRiskFilter;
  selectedThreadName: string | null;
  threadSorting: SortingState;
  visibleThreadRows: number;
  threadCallSort: ThreadCallSortKey;
  threadCallSortDirection: ThreadCallSortDirection;
  exportStatus: string;
  filterStatus: string;
  viewMode: ThreadEvidenceViewMode;
  setSelectedThreadName: Dispatch<SetStateAction<string | null>>;
  setVisibleThreadRows: Dispatch<SetStateAction<number>>;
  setExportStatus: Dispatch<SetStateAction<string>>;
  setViewMode: Dispatch<SetStateAction<ThreadEvidenceViewMode>>;
  updateLocalQuery: (value: string) => void;
  updateRiskFilter: (value: string) => void;
  updateThreadSorting: (updater: SortingState | ((old: SortingState) => SortingState)) => void;
  clearThreadFilters: () => void;
  toggleThread: (threadName: string) => void;
  updateThreadCallSort: (value: string) => void;
  updateThreadCallSortDirection: (value: string) => void;
}

export function useThreadsPageControls(globalQuery: string): ThreadsPageControls {
  const [localQuery, setLocalQuery] = useState(() => readThreadSearchParam('thread_q'));
  const [riskFilter, setRiskFilter] = useState<ThreadRiskFilter>(() => readThreadRiskParam());
  const [selectedThreadName, setSelectedThreadName] = useState<string | null>(() => readInitialSelectedThreadParam());
  const [threadSorting, setThreadSorting] = useState<SortingState>(() => readThreadSortingParam());
  const [visibleThreadRows, setVisibleThreadRows] = useState(() => readThreadPageVisibleRowsParam(threadsTablePageSize));
  const initialThreadCallSort = readThreadCallSortParam();
  const [threadCallSort, setThreadCallSort] = useState<ThreadCallSortKey>(() => initialThreadCallSort);
  const [threadCallSortDirection, setThreadCallSortDirection] = useState<ThreadCallSortDirection>(() =>
    readThreadCallSortDirectionParam(initialThreadCallSort),
  );
  const [exportStatus, setExportStatus] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [viewMode, setViewMode] = useState<ThreadEvidenceViewMode>('table');
  const previousGlobalQueryRef = useRef(globalQuery);

  useEffect(() => {
    if (previousGlobalQueryRef.current === globalQuery) return;
    previousGlobalQueryRef.current = globalQuery;
    setVisibleThreadRows(threadsTablePageSize);
  }, [globalQuery]);

  function resetThreadTablePage() {
    setVisibleThreadRows(threadsTablePageSize);
  }

  function updateLocalQuery(value: string) {
    setLocalQuery(value);
    resetThreadTablePage();
  }

  function updateRiskFilter(value: string) {
    setRiskFilter(normalizeThreadRiskFilter(value));
    resetThreadTablePage();
  }

  function updateThreadSorting(updater: SortingState | ((old: SortingState) => SortingState)) {
    setThreadSorting(current => (typeof updater === 'function' ? updater(current) : updater));
    resetThreadTablePage();
  }

  function clearThreadFilters() {
    setLocalQuery('');
    setRiskFilter('all');
    setSelectedThreadName(null);
    setVisibleThreadRows(threadsTablePageSize);
    setThreadCallSort('newest');
    setThreadCallSortDirection(defaultThreadCallSortDirection('newest'));
    window.history.replaceState(null, '', buildThreadsViewLink({
      localQuery: '',
      riskFilter: 'all',
      selectedThreadName: null,
      sorting: threadSorting,
      visibleRowCount: threadsTablePageSize,
      threadCallSort: 'newest',
      threadCallSortDirection: defaultThreadCallSortDirection('newest'),
    }));
    setFilterStatus('Thread filters cleared');
  }

  function toggleThread(threadName: string) {
    setSelectedThreadName(current => current === threadName ? null : threadName);
  }

  function updateThreadCallSort(value: string) {
    const nextSort = normalizeThreadCallSort(value);
    setThreadCallSort(nextSort);
    setThreadCallSortDirection(defaultThreadCallSortDirection(nextSort));
  }

  function updateThreadCallSortDirection(value: string) {
    setThreadCallSortDirection(value === 'asc' ? 'asc' : 'desc');
  }

  return {
    localQuery, riskFilter, selectedThreadName, threadSorting, visibleThreadRows,
    threadCallSort, threadCallSortDirection, exportStatus, filterStatus, viewMode,
    setSelectedThreadName, setVisibleThreadRows, setExportStatus, setViewMode,
    updateLocalQuery, updateRiskFilter, updateThreadSorting, clearThreadFilters,
    toggleThread, updateThreadCallSort, updateThreadCallSortDirection,
  };
}
