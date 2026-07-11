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

function readPreferences(
  storageKey: string,
  defaults: EvidenceGridPreferenceDefaults,
  initialDensity?: EvidenceGridDensity,
): EvidenceGridPreferenceDefaults {
  const storage = getLocalStorage();
  if (!storage) {
    return { ...defaults, density: initialDensity ?? defaults.density };
  }

  try {
    const stored = JSON.parse(storage.getItem(storageKey) ?? '{}') as StoredEvidenceGridPreferences;
    const storedDensity = stored.density === 'compact' || stored.density === 'comfortable'
      ? stored.density
      : defaults.density;
    const density = initialDensity ?? storedDensity;
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
  initialDensity?: EvidenceGridDensity,
): EvidenceGridPreferences {
  const [preferences, setPreferences] = useState(() => readPreferences(storageKey, defaults, initialDensity));

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
