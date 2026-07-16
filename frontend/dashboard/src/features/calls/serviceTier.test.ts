import { describe, expect, it } from 'vitest';

import { usageRowToCall } from '../../api/client';
import { serviceTierDetail, serviceTierLabel } from './serviceTier';

describe('service tier labels', () => {
  it('shows protocol-confirmed Standard separately from the throughput proxy', () => {
    const call = usageRowToCall({
      service_tier: 'standard',
      fast: 0,
      service_tier_source: 'otel_response_completed',
      service_tier_confidence: 'protocol',
      duration_seconds: 1,
      total_tokens: 9000,
    });

    expect(serviceTierLabel(call)).toBe('Standard');
    expect(serviceTierDetail(call)).toBe('confirmed Standard · protocol');
    expect(call.fastProxyCandidate).toBe(true);
  });

  it('describes unknown tiers with the historical throughput proxy', () => {
    const candidate = usageRowToCall({ duration_seconds: 1, total_tokens: 9000 });
    const normal = usageRowToCall({ duration_seconds: 10, total_tokens: 100 });

    expect(serviceTierLabel(candidate)).toBe('Unknown');
    expect(serviceTierDetail(candidate)).toBe('tier unknown · Fast proxy candidate');
    expect(serviceTierDetail(normal)).toBe('tier unknown · normal throughput proxy');
  });
});
