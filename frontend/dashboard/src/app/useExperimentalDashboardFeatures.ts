import { useEffect, useState } from 'react';

export const compatibilityAndLabsStorageKey = 'codex-usage-dashboard-show-compatibility-labs-v1';
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
    const target = storage();
    const raw = target?.getItem(compatibilityAndLabsStorageKey)
      ?? target?.getItem(experimentalDashboardFeaturesStorageKey)
      ?? 'false';
    const stored = JSON.parse(raw) as unknown;
    return typeof stored === 'boolean' ? stored : false;
  } catch {
    return false;
  }
}

function safelyWrite(showExperimental: boolean): void {
  try {
    storage()?.setItem(compatibilityAndLabsStorageKey, JSON.stringify(showExperimental));
  } catch {
    // Restricted storage must not prevent in-session preference changes.
  }
}

export function useExperimentalDashboardFeatures() {
  const [showExperimental, setShowExperimental] = useState(readPreference);

  useEffect(() => safelyWrite(showExperimental), [showExperimental]);

  return {
    showCompatibilityAndLabs: showExperimental,
    setShowCompatibilityAndLabs: setShowExperimental,
    // Shell aliases remain until the compatibility cleanup task renames its callers.
    showExperimental,
    setShowExperimental,
  };
}
