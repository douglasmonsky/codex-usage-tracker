import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  experimentalDashboardFeaturesStorageKey,
  useExperimentalDashboardFeatures,
} from './useExperimentalDashboardFeatures';

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('useExperimentalDashboardFeatures', () => {
  it('defaults experimental dashboard features off', () => {
    const { result } = renderHook(() => useExperimentalDashboardFeatures());
    expect(result.current.showExperimental).toBe(false);
  });

  it('updates immediately and stores a JSON boolean', async () => {
    const { result } = renderHook(() => useExperimentalDashboardFeatures());

    act(() => result.current.setShowExperimental(true));

    expect(result.current.showExperimental).toBe(true);
    await waitFor(() => expect(localStorage.getItem(experimentalDashboardFeaturesStorageKey)).toBe('true'));
  });

  it('restores the preference after remounting', async () => {
    const first = renderHook(() => useExperimentalDashboardFeatures());
    act(() => first.result.current.setShowExperimental(true));
    await waitFor(() => expect(localStorage.getItem(experimentalDashboardFeaturesStorageKey)).toBe('true'));
    first.unmount();

    const second = renderHook(() => useExperimentalDashboardFeatures());
    expect(second.result.current.showExperimental).toBe(true);
  });

  it.each(['{broken', 'null', '"true"', '1'])('treats malformed stored value %s as off', stored => {
    localStorage.setItem(experimentalDashboardFeaturesStorageKey, stored);
    const { result } = renderHook(() => useExperimentalDashboardFeatures());
    expect(result.current.showExperimental).toBe(false);
  });

  it('preserves in-session state when storage access is restricted', () => {
    vi.stubGlobal('localStorage', restrictedStorage());
    const { result } = renderHook(() => useExperimentalDashboardFeatures());

    act(() => result.current.setShowExperimental(true));

    expect(result.current.showExperimental).toBe(true);
  });
});

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null,
    removeItem: key => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}

function restrictedStorage(): Storage {
  const denied = () => { throw new DOMException('Storage denied', 'SecurityError'); };
  return {
    get length() { return denied(); },
    clear: denied,
    getItem: denied,
    key: denied,
    removeItem: denied,
    setItem: denied,
  };
}
