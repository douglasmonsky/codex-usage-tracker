import { afterEach, beforeEach, vi } from 'vitest';
import { clearDiagnosticApiCache } from '../api/diagnostics';
import { clearContextEvidenceCache } from '../features/shared/contextEvidenceCache';

export { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
export { describe, expect, it, vi } from 'vitest';
export { App } from '../App';
export { rowsToCsv } from '../features/shared/exportCsv';

export function installAppTestHooks() {
  beforeEach(() => {
    window.history.replaceState(null, '', '/');
    window.sessionStorage.clear();
    delete window.__CODEX_USAGE_BOOT__;
clearDiagnosticApiCache();
clearContextEvidenceCache();
vi.restoreAllMocks();
});

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
}
