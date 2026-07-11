import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import type { VisibilityState } from '@tanstack/react-table';

export type EvidenceGridDensity = 'comfortable' | 'compact';

export type EvidenceGridPreferenceDefaults = {
  density: EvidenceGridDensity;
  columnVisibility: VisibilityState;
};

type StoredEvidenceGridPreferences = Partial<EvidenceGridPreferenceDefaults>;

export type EvidenceGridPreferences = {
  density: EvidenceGridDensity;
  setDensity: Dispatch<SetStateAction<EvidenceGridDensity>>;
  columnVisibility: VisibilityState;
  setColumnVisibility: Dispatch<SetStateAction<VisibilityState>>;
  restoreDefaults: () => void;
};

function getLocalStorage(): Storage | undefined {
  try {
    return typeof globalThis.localStorage === 'undefined' ? undefined : globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function readPreferences(storageKey: string, defaults: EvidenceGridPreferenceDefaults): EvidenceGridPreferenceDefaults {
  const storage = getLocalStorage();
  if (!storage) {
    return defaults;
  }

  try {
    const stored = JSON.parse(storage.getItem(storageKey) ?? '{}') as StoredEvidenceGridPreferences;
    const density = stored.density === 'compact' || stored.density === 'comfortable'
      ? stored.density
      : defaults.density;
    const columnVisibility = stored.columnVisibility && typeof stored.columnVisibility === 'object'
      ? Object.fromEntries(
          Object.entries(stored.columnVisibility).filter((entry): entry is [string, boolean] => typeof entry[1] === 'boolean'),
        )
      : defaults.columnVisibility;
    return { density, columnVisibility };
  } catch {
    return defaults;
  }
}

export function useEvidenceGridPreferences(
  storageKey: string,
  defaults: EvidenceGridPreferenceDefaults,
): EvidenceGridPreferences {
  const [preferences, setPreferences] = useState(() => readPreferences(storageKey, defaults));

  useEffect(() => {
    getLocalStorage()?.setItem(storageKey, JSON.stringify(preferences));
  }, [preferences, storageKey]);

  const setDensity = useCallback<Dispatch<SetStateAction<EvidenceGridDensity>>>(nextDensity => {
    setPreferences(current => ({
      ...current,
      density: typeof nextDensity === 'function' ? nextDensity(current.density) : nextDensity,
    }));
  }, []);

  const setColumnVisibility = useCallback<Dispatch<SetStateAction<VisibilityState>>>(nextVisibility => {
    setPreferences(current => ({
      ...current,
      columnVisibility: typeof nextVisibility === 'function'
        ? nextVisibility(current.columnVisibility)
        : nextVisibility,
    }));
  }, []);

  const restoreDefaults = useCallback(() => {
    setPreferences({
      density: defaults.density,
      columnVisibility: { ...defaults.columnVisibility },
    });
  }, [defaults.columnVisibility, defaults.density]);

  return {
    density: preferences.density,
    setDensity,
    columnVisibility: preferences.columnVisibility,
    setColumnVisibility,
    restoreDefaults,
  };
}
