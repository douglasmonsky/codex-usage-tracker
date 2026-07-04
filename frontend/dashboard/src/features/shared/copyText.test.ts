import { describe, expect, it, vi } from 'vitest';

import { copyText } from './copyText';

describe('copyText', () => {
  it('uses the Clipboard API when available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    await expect(copyText('https://example.test/current-view')).resolves.toBe(true);

    expect(writeText).toHaveBeenCalledWith('https://example.test/current-view');
  });

  it('falls back to a hidden textarea when the Clipboard API is unavailable', async () => {
    let copiedText = '';
    const execCommand = vi.fn((command: string) => {
      copiedText = document.querySelector('textarea')?.value ?? '';
      return command === 'copy';
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    });

    await expect(copyText('https://example.test/fallback')).resolves.toBe(true);

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(copiedText).toBe('https://example.test/fallback');
    expect(document.querySelector('textarea')).toBeNull();
  });
});
