export type UsageBillingFields = {
  estimated_cost_usd?: number | null;
  standard_cost_usd?: number | null;
  priority_cost_usd?: number | null;
  pricing_service_tier?: string | null;
  billing_basis?: string | null;
  cost_semantics?: string | null;
};

export type CallBillingFields = {
  cost: number;
  standardCost: number | null;
  priorityCost: number | null;
  pricingServiceTier: string;
  billingBasis: string;
  costSemantics: string;
};

export function usageBillingFields(row: UsageBillingFields): CallBillingFields {
  return {
    cost: Number(row.estimated_cost_usd ?? 0),
    standardCost: optionalNumber(row.standard_cost_usd),
    priorityCost: optionalNumber(row.priority_cost_usd),
    pricingServiceTier: String(row.pricing_service_tier ?? ''),
    billingBasis: String(row.billing_basis ?? 'unknown'),
    costSemantics: String(row.cost_semantics ?? 'api_token_estimate'),
  };
}

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}
