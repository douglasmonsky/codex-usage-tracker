import type { ConversationalReadiness } from './types';

export async function loadConversationalReadiness(
  signal?: AbortSignal,
): Promise<ConversationalReadiness> {
  const response = await fetch('/api/readiness', { cache: 'no-store', signal });
  const payload = await response.json() as ConversationalReadiness & { error?: string };
  if (!response.ok) throw new Error(payload.error || `MCP readiness request failed (${response.status})`);
  return payload;
}
