import { useEffect, useState } from 'react';

export const settingsSections = ['data', 'estimates', 'content', 'application', 'sources'] as const;
export type SettingsSection = (typeof settingsSections)[number];
export const settingsSectionStorageKey = 'codex-usage-dashboard-settings-section';

function isSettingsSection(value: unknown): value is SettingsSection {
  return settingsSections.some(section => section === value);
}

function storage(): Storage | undefined {
  try {
    return typeof globalThis.localStorage === 'undefined' ? undefined : globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function readSettingsSection(): SettingsSection {
  try {
    const stored = JSON.parse(storage()?.getItem(settingsSectionStorageKey) ?? 'null') as unknown;
    return isSettingsSection(stored) ? stored : 'data';
  } catch {
    return 'data';
  }
}

export function useSettingsSection() {
  const [selectedSection, setSelectedSection] = useState<SettingsSection>(readSettingsSection);

  useEffect(() => {
    try {
      storage()?.setItem(settingsSectionStorageKey, JSON.stringify(selectedSection));
    } catch {
      // Restricted storage must not prevent in-session navigation.
    }
  }, [selectedSection]);

  return { selectedSection, selectSection: setSelectedSection };
}
