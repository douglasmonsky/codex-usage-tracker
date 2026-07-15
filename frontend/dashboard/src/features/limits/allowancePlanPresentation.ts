const PLAN_COLORS: Record<string, string> = {
  pro: '#3b82f6',
  prolite: '#d97706',
  plus: '#16866b',
  team: '#7656a8',
  business: '#0f8b8d',
  enterprise: '#c0448f',
  mixed: '#8a5a44',
  unknown: '#6b7280',
};

const PLAN_MEDIAN_COLORS: Record<string, string> = {
  pro: '#1d4ed8',
  prolite: '#9a4d00',
  plus: '#0f5f4c',
  team: '#513879',
  business: '#086467',
  enterprise: '#8c2f68',
  mixed: '#623e2f',
  unknown: '#454b55',
};

const FALLBACK_COLORS = ['#3568b8', '#b45f8f', '#577590', '#a66f00', '#5f7f45'];

export function normalizeAllowancePlanType(value: string | null | undefined): string {
  const normalized = (value ?? '').trim().toLowerCase().replaceAll('-', '_').replaceAll(' ', '_');
  if (!normalized) return 'unknown';
  if (normalized === 'pro_lite') return 'prolite';
  return normalized;
}

export function allowancePlanLabel(value: string): string {
  const planType = normalizeAllowancePlanType(value);
  const known: Record<string, string> = {
    pro: 'Pro',
    prolite: 'Pro Lite',
    plus: 'Plus',
    team: 'Team',
    business: 'Business',
    enterprise: 'Enterprise',
    mixed: 'Mixed plan',
    unknown: 'Unknown plan',
  };
  return known[planType] ?? planType.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}

export function allowancePlanColor(value: string): string {
  const planType = normalizeAllowancePlanType(value);
  const known = PLAN_COLORS[planType];
  if (known) return known;
  const hash = [...planType].reduce((total, character) => total + character.charCodeAt(0), 0);
  return FALLBACK_COLORS[hash % FALLBACK_COLORS.length];
}

export function allowancePlanMedianColor(value: string): string {
  const planType = normalizeAllowancePlanType(value);
  return PLAN_MEDIAN_COLORS[planType] ?? darkenHex(allowancePlanColor(planType), 0.28);
}

export function allowancePlanFieldKey(value: string): string {
  return normalizeAllowancePlanType(value).replace(/[^a-z0-9]+/g, '_');
}

function darkenHex(color: string, amount: number): string {
  const channels = color.slice(1).match(/.{2}/g);
  if (!channels || channels.length !== 3) return color;
  const factor = 1 - amount;
  return `#${channels
    .map(channel => Math.round(Number.parseInt(channel, 16) * factor).toString(16).padStart(2, '0'))
    .join('')}`;
}
