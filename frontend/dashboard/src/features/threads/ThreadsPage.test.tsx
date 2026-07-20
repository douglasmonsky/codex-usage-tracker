import { describe, expect, it } from 'vitest';

import { buildThreads } from '../../api/client';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import {
  buildThreadsDepartureUrl,
  callsForThreadRow,
  canonicalThreadSelector,
  nextThreadSelection,
  resolveSelectedThread,
} from './ThreadsPage';
import {
  threadRowIdentity,
  threadSelectorFromIdentity,
} from './threadsUrlState';

describe('ThreadsPage canonical thread routing', () => {
  it('propagates the API thread key into aggregate thread rows', () => {
    const call = {
      ...fixtureModel.calls[0],
      thread: 'Private project label',
      threadKey: 'session:019e374d-c19f-7da3-a44f-8de043a7a64e',
    };

    expect(buildThreads([call])[0]?.threadKey).toBe(call.threadKey);
  });

  it('keeps same-label canonical threads and their offline evidence distinct', () => {
    const first = {
      ...fixtureModel.calls[0],
      id: 'record-101',
      thread: 'Shared label',
      threadKey: 'session:019e374d-c19f-7da3-a44f-8de043a7a64e',
    };
    const second = {
      ...fixtureModel.calls[1],
      id: 'record-102',
      thread: 'Shared label',
      threadKey: 'session:029e374d-c19f-7da3-a44f-8de043a7a64e',
    };
    const threads = buildThreads([first, second]);

    expect(threads).toHaveLength(2);
    expect(new Set(threads.map(thread => thread.threadKey))).toEqual(new Set([first.threadKey, second.threadKey]));
    expect(threads.every(thread => thread.name === 'Shared label')).toBe(true);
    expect(callsForThreadRow([first, second], threads[0]).map(call => call.id)).toEqual([
      threads[0].threadKey === first.threadKey ? first.id : second.id,
    ]);
    const firstSelector = canonicalThreadSelector(threads[0]);
    const secondSelector = canonicalThreadSelector(threads[1]);
    expect(nextThreadSelection(threads[0], secondSelector)).toEqual(secondSelector);
    expect(nextThreadSelection(threads[0], firstSelector)).toBeNull();
    expect(threadSelectorFromIdentity(threadRowIdentity(threads[1]))).toEqual(secondSelector);
  });

  it('resolves canonical keys before legacy display names', () => {
    const threads = fixtureModel.threads.map((thread, index) => ({
      ...thread,
      name: index === 0 ? 'session:019e374d-c19f-7da3-a44f-8de043a7a64e' : thread.name,
      threadKey: index === 1 ? 'session:019e374d-c19f-7da3-a44f-8de043a7a64e' : `session:00000000-0000-0000-0000-00000000000${index}`,
    }));

    expect(resolveSelectedThread(threads, {
      kind: 'key',
      value: 'session:019e374d-c19f-7da3-a44f-8de043a7a64e',
    }))
      .toBe(threads[1]);
    expect(resolveSelectedThread(threads, {
      kind: 'name',
      value: 'session:019e374d-c19f-7da3-a44f-8de043a7a64e',
    })).toBe(threads[0]);
    expect(resolveSelectedThread(threads, { kind: 'name', value: threads[2].name })).toBe(threads[2]);

    const canonical = canonicalThreadSelector(threads[1]);
    const renamedThreads = threads.map(thread => thread === threads[1]
      ? { ...thread, name: 'Updated private label' }
      : thread);
    expect(resolveSelectedThread(renamedThreads, canonical)?.name).toBe('Updated private label');
  });

  it('clears both thread selectors when leaving the Threads workspace', () => {
    const url = buildThreadsDepartureUrl(
      'tools',
      'http://localhost/react-dashboard.html?view=threads&thread=Private%20project&thread_key=session%3A019e374d-c19f-7da3-a44f-8de043a7a64e',
    );

    expect(url.searchParams.has('thread')).toBe(false);
    expect(url.searchParams.has('thread_key')).toBe(false);
  });
});
