const callsDetailPanelStorageKey = 'codexUsageDetailPanel';

export function readCallsDetailPanelPreference(defaultExpanded = false): boolean {
  try {
    const storedValue = window.sessionStorage?.getItem(callsDetailPanelStorageKey);
    return storedValue ? storedValue === 'expanded' : defaultExpanded;
  } catch {
    return defaultExpanded;
  }
}

export function rememberCallsDetailPanelPreference(expanded: boolean): void {
  try {
    window.sessionStorage?.setItem(callsDetailPanelStorageKey, expanded ? 'expanded' : 'collapsed');
  } catch {
    // Session storage is optional; the visible toggle still works without persistence.
  }
}
