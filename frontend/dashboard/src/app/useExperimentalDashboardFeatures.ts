import { useEffect, useState } from 'react';

export const experimentalDashboardFeaturesStorageKey = 'codex-usage-dashboard-show-experimental-v1';

function storage(): Storage | undefined {
  try {
    return typeof globalThis.localStorage === 'undefined' ? undefined : globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function readPreference(): boolean {
  try {
    const stored = JSON.parse(storage()?.getItem(experimentalDashboardFeaturesStorageKey) ?? 'false') as unknown;
    return typeof stored === 'boolean' ? stored : false;
  } catch {
    return false;
  }
}

function safelyWrite(showExperimental: boolean): void {
  try {
    storage()?.setItem(experimentalDashboardFeaturesStorageKey, JSON.stringify(showExperimental));
  } catch {
    // Restricted storage must not prevent in-session preference changes.
  }
}

export function useExperimentalDashboardFeatures() {
  const [showExperimental, setShowExperimental] = useState(readPreference);

  useEffect(() => safelyWrite(showExperimental), [showExperimental]);

  return { showExperimental, setShowExperimental };
}
