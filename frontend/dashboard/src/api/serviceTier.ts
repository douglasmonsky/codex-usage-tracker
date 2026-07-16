export type UsageServiceTierFields = {
  standard_usage_credits?: number | null;
  usage_credit_multiplier?: number | null;
  usage_credit_multiplier_source?: string | null;
  service_tier?: string | null;
  fast?: number | boolean | null;
  service_tier_source?: string | null;
  service_tier_confidence?: string | null;
};

export type CallServiceTierFields = {
  credits: number;
  serviceTier: string;
  fast: boolean | null;
  serviceTierSource: string;
  serviceTierConfidence: string;
  fastProxyCandidate: boolean;
  standardUsageCredits: number;
  usageCreditMultiplier: number;
  usageCreditMultiplierSource: string;
};

export function usageServiceTierFields(
  row: UsageServiceTierFields & { usage_credits?: number },
  durationSeconds: number,
  totalTokens: number,
): CallServiceTierFields {
  const rawFast = row.fast;
  const fast = rawFast === true || rawFast === 1
    ? true
    : rawFast === false || rawFast === 0
      ? false
      : null;
  return {
    credits: Number(row.usage_credits ?? 0),
    serviceTier: String(row.service_tier ?? ''),
    fast,
    serviceTierSource: String(row.service_tier_source ?? ''),
    serviceTierConfidence: String(row.service_tier_confidence ?? ''),
    fastProxyCandidate: durationSeconds > 0 && totalTokens / Math.max(durationSeconds, 1) > 4_000,
    standardUsageCredits: Number(row.standard_usage_credits ?? row.usage_credits ?? 0),
    usageCreditMultiplier: Number(row.usage_credit_multiplier ?? 1),
    usageCreditMultiplierSource: String(row.usage_credit_multiplier_source ?? ''),
  };
}
