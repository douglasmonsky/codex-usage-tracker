import type { KeyboardEvent } from 'react';

export function stopRowActionKeyDown(event: KeyboardEvent<HTMLElement>) {
  event.stopPropagation();
}
