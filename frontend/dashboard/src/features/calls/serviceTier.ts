import type { CallRow } from '../../api/types';

export function serviceTierLabel(call: CallRow): 'Fast' | 'Standard' | 'Unknown' {
  if (call.fast === true) return 'Fast';
  if (call.fast === false) return 'Standard';
  return 'Unknown';
}

export function serviceTierDetail(call: CallRow): string {
  if (call.fast !== null) {
    return `confirmed ${serviceTierLabel(call)} · ${call.serviceTierConfidence || 'exact'}`;
  }
  return call.fastProxyCandidate
    ? 'tier unknown · Fast proxy candidate'
    : 'tier unknown · normal throughput proxy';
}
