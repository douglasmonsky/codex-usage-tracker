import type { OverviewEndpointBundle } from './overviewQueries';

export type OverviewEndpointCacheIdentity = {
  includeArchived: boolean;
  since: string;
  sourceRevision: string;
};

export type OverviewEndpointCache = {
  read(identity: OverviewEndpointCacheIdentity): OverviewEndpointBundle | null;
  write(identity: OverviewEndpointCacheIdentity, bundle: OverviewEndpointBundle): void;
};

type OverviewEndpointStorage = Pick<Storage, 'getItem' | 'setItem'>;

type OverviewEndpointCacheRecord = {
  identity: OverviewEndpointCacheIdentity;
  bundle: OverviewEndpointBundle;
  storedAt: number;
};

const storageKey = 'codexUsageOverviewEndpointCache';
const maxAgeMs = 7 * 24 * 60 * 60 * 1_000;
const maxStorageBytes = 2_000_000;
const maxRecords = 8;

export function createOverviewEndpointCache(
  storageProvider: () => OverviewEndpointStorage | null,
): OverviewEndpointCache {
  return {
    read(identity) {
      const storage = storageProvider();
      if (!storage) return null;
      try {
        const raw = storage.getItem(storageKey);
        if (!raw || raw.length > maxStorageBytes) return null;
        const record = parseRecords(raw).find(candidate => (
          sameIdentity(candidate.identity, identity)
          && Date.now() - candidate.storedAt <= maxAgeMs
        ));
        return record?.bundle ?? null;
      } catch {
        return null;
      }
    },
    write(identity, bundle) {
      const storage = storageProvider();
      if (!storage) return;
      try {
        const records = parseRecords(storage.getItem(storageKey) ?? '')
          .filter(record => !sameIdentity(record.identity, identity) && Date.now() - record.storedAt <= maxAgeMs);
        records.unshift({ identity, bundle, storedAt: Date.now() });
        const serialized = JSON.stringify(records.slice(0, maxRecords));
        if (serialized.length <= maxStorageBytes) storage.setItem(storageKey, serialized);
      } catch {
        // Storage can be disabled or full in private and embedded browser contexts.
      }
    },
  };
}

export const persistentOverviewEndpointCache = createOverviewEndpointCache(localStorageOrNull);

/*
 * Keep parsing tolerant of the initial single-record format so existing local
 * caches migrate without a storage-version ceremony.
 */
function parseRecords(raw: string): OverviewEndpointCacheRecord[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as OverviewEndpointCacheRecord[] | OverviewEndpointCacheRecord;
    const records = Array.isArray(parsed) ? parsed : [parsed];
    return records.filter(record => (
      Boolean(record)
      && typeof record.storedAt === 'number'
      && Boolean(record.identity)
      && Boolean(record.bundle)
    ));
  } catch {
    return [];
  }
}

function sameIdentity(
  left: OverviewEndpointCacheIdentity | undefined,
  right: OverviewEndpointCacheIdentity,
): boolean {
  return Boolean(
    left
    && left.includeArchived === right.includeArchived
    && left.since === right.since
    && left.sourceRevision === right.sourceRevision,
  );
}

function localStorageOrNull(): OverviewEndpointStorage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}
