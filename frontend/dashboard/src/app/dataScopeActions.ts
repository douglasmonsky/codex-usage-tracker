import type { Dispatch, SetStateAction } from 'react';

import type { RefreshOptions } from './dashboardRefresh';
import type { ViewId } from './navigation';
import {
  finiteRowLimitFallback,
  loadWindowLabel,
  storeDataScopePreference,
  type LoadWindow,
} from './rowLimit';
import { historyScopeUrl, type HistoryScope } from './shellUrl';

type DataScopeActionsInput = {
  activeView: ViewId;
  historyScope: HistoryScope;
  loadLimit: number;
  loadWindow: LoadWindow;
  nextLoadMoreLimit: number;
  pendingLoadLimit: number;
  refreshDashboard(options: RefreshOptions): Promise<void>;
  replaceShellUrl(url: URL): void;
  setHistoryScope: Dispatch<SetStateAction<HistoryScope>>;
  setLoadLimit: Dispatch<SetStateAction<number>>;
  setLoadWindow: Dispatch<SetStateAction<LoadWindow>>;
  setPendingLoadLimit: Dispatch<SetStateAction<number>>;
  setRefreshState: Dispatch<SetStateAction<string>>;
};

export function usesFocusedScopeEndpoints(view: ViewId): boolean {
  return view === 'home' || view === 'overview';
}

export function createDataScopeActions(input: DataScopeActionsInput) {
  const focused = usesFocusedScopeEndpoints(input.activeView);

  function applyLoadLimitChange() {
    if (!focused) {
      void input.refreshDashboard({
        refresh: false,
        loadLimit: input.pendingLoadLimit,
        loadWindow: 'rows',
      });
      return;
    }
    const nextLimit = finiteRowLimitFallback(
      input.pendingLoadLimit,
      input.loadLimit,
      500,
    );
    input.setLoadLimit(nextLimit);
    input.setPendingLoadLimit(nextLimit);
    input.setLoadWindow('rows');
    storeDataScopePreference(nextLimit, input.historyScope, 'rows');
    input.setRefreshState(`${loadWindowLabel('rows', nextLimit)} selected`);
  }

  function handleLoadWindowChange(nextLoadWindow: LoadWindow) {
    if (nextLoadWindow === input.loadWindow) return;
    if (!focused) {
      void input.refreshDashboard({ refresh: false, loadWindow: nextLoadWindow });
      return;
    }
    input.setLoadWindow(nextLoadWindow);
    storeDataScopePreference(input.loadLimit, input.historyScope, nextLoadWindow);
    input.setRefreshState(
      `${loadWindowLabel(nextLoadWindow, input.loadLimit)} selected`,
    );
  }

  function loadAllRows() {
    if (focused) {
      handleLoadWindowChange('all');
      return;
    }
    void input.refreshDashboard({ refresh: false, loadWindow: 'all' });
  }

  function loadMoreRows() {
    input.setPendingLoadLimit(input.nextLoadMoreLimit);
    if (!focused) {
      void input.refreshDashboard({
        refresh: false,
        loadLimit: input.nextLoadMoreLimit,
        loadWindow: input.loadWindow,
      });
      return;
    }
    input.setLoadLimit(input.nextLoadMoreLimit);
    input.setLoadWindow('rows');
    storeDataScopePreference(
      input.nextLoadMoreLimit,
      input.historyScope,
      'rows',
    );
    input.setRefreshState(
      `${loadWindowLabel('rows', input.nextLoadMoreLimit)} selected`,
    );
  }

  function handleHistoryScopeChange(value: string) {
    const nextHistoryScope: HistoryScope = value === 'all' ? 'all' : 'active';
    input.setHistoryScope(nextHistoryScope);
    input.replaceShellUrl(historyScopeUrl(nextHistoryScope));
    storeDataScopePreference(
      input.loadLimit,
      nextHistoryScope,
      input.loadWindow,
    );
    if (!focused) {
      void input.refreshDashboard({
        refresh: false,
        historyScope: nextHistoryScope,
      });
      return;
    }
    input.setRefreshState(
      `${nextHistoryScope === 'all' ? 'All history' : 'Active sessions'} selected`,
    );
  }

  return {
    applyLoadLimitChange,
    handleHistoryScopeChange,
    handleLoadWindowChange,
    loadAllRows,
    loadMoreRows,
  };
}
