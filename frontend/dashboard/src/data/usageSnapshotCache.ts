import type { DashboardBootPayload } from '../api/types';
import type { DataScope } from './dataScope';

export type UsageSnapshotIdentity = {
  sourceKey: string;
  sourceRevision: string;
  scope: DataScope;
};

export type UsageSnapshotStore = {
  read(identity: UsageSnapshotIdentity): Promise<DashboardBootPayload | null>;
  write(identity: UsageSnapshotIdentity, payload: DashboardBootPayload): Promise<void>;
};

type UsageSnapshotRecord = UsageSnapshotIdentity & {
  cacheKey: string;
  payload: DashboardBootPayload;
  storedAt: number;
};

const databaseName = 'codexUsageDashboard';
const databaseVersion = 1;
const storeName = 'usageSnapshots';
const maxRecords = 6;
const maxAgeMs = 7 * 24 * 60 * 60 * 1_000;

export const persistentUsageSnapshotStore: UsageSnapshotStore = {
  async read(identity) {
    if (!identity.sourceRevision) return null;
    try {
      const database = await openDatabase();
      if (!database) return null;
      const record = await requestResult<UsageSnapshotRecord | undefined>(
        database.transaction(storeName, 'readonly').objectStore(storeName).get(cacheKey(identity)),
      );
      if (!record || record.sourceRevision !== identity.sourceRevision || Date.now() - record.storedAt > maxAgeMs) {
        return null;
      }
      return record.payload;
    } catch {
      return null;
    }
  },
  async write(identity, payload) {
    if (!identity.sourceRevision) return;
    try {
      const database = await openDatabase();
      if (!database) return;
      const transaction = database.transaction(storeName, 'readwrite');
      transaction.objectStore(storeName).put({
        ...identity,
        cacheKey: cacheKey(identity),
        payload,
        storedAt: Date.now(),
      } satisfies UsageSnapshotRecord);
      await transactionComplete(transaction);
      await pruneSnapshots(database);
    } catch {
      // IndexedDB can be unavailable in private or embedded browser contexts.
    }
  },
};

function cacheKey(identity: UsageSnapshotIdentity): string {
  const { historyScope, loadWindow, limit, since } = identity.scope;
  return JSON.stringify([identity.sourceKey, historyScope, loadWindow, limit, since]);
}

function openDatabase(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === 'undefined') return Promise.resolve(null);
  return new Promise(resolve => {
    const request = indexedDB.open(databaseName, databaseVersion);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(storeName)) {
        request.result.createObjectStore(storeName, { keyPath: 'cacheKey' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
    request.onblocked = () => resolve(null);
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'));
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error('IndexedDB transaction failed'));
    transaction.onabort = () => reject(transaction.error ?? new Error('IndexedDB transaction aborted'));
  });
}

async function pruneSnapshots(database: IDBDatabase): Promise<void> {
  const readTransaction = database.transaction(storeName, 'readonly');
  const records = await requestResult<UsageSnapshotRecord[]>(readTransaction.objectStore(storeName).getAll());
  const staleRecords = records
    .sort((left, right) => right.storedAt - left.storedAt)
    .slice(maxRecords);
  if (!staleRecords.length) return;
  const deleteTransaction = database.transaction(storeName, 'readwrite');
  const objectStore = deleteTransaction.objectStore(storeName);
  staleRecords.forEach(record => objectStore.delete(record.cacheKey));
  await transactionComplete(deleteTransaction);
}
