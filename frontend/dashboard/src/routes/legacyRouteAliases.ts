import {
  isEvidenceConsoleRouteId,
  type EvidenceConsoleRouteId,
} from '../app/evidenceConsoleRoutes';

export const legacyDirectRouteIds = [
  'investigator',
  'compression-lab',
  'diagnostics',
  'cache-context',
  'reports',
] as const;

export type LegacyDirectRouteId = (typeof legacyDirectRouteIds)[number];

export const legacyCompatibilityRouteIds = [
  'overview',
  'calls',
  'threads',
  'call',
  'usage-drain',
  ...legacyDirectRouteIds,
] as const;

export const legacyRouteAliases = {
  overview: { view: 'home', params: {} },
  calls: { view: 'explore', params: { mode: 'calls' } },
  threads: { view: 'explore', params: { mode: 'threads' } },
  call: { view: 'evidence', params: { kind: 'call' } },
  'usage-drain': { view: 'limits', params: {} },
  settings: { view: 'settings', params: {} },
  investigator: null,
  'compression-lab': null,
  diagnostics: null,
  'cache-context': null,
  reports: null,
} as const;

export type LegacyRouteId = keyof typeof legacyRouteAliases;
export type NormalizedDashboardRoute = {
  view: EvidenceConsoleRouteId | LegacyDirectRouteId;
  params: Record<string, string>;
};

const legacyDirectRouteIdSet = new Set<string>(legacyDirectRouteIds);

export function isLegacyDirectRouteId(value: unknown): value is LegacyDirectRouteId {
  return typeof value === 'string' && legacyDirectRouteIdSet.has(value);
}

export function normalizeDashboardRouteInput(value: unknown): NormalizedDashboardRoute | null {
  const candidate = typeof value === 'string' ? value.trim() : '';
  if (!candidate) return null;
  if (isEvidenceConsoleRouteId(candidate)) return { view: candidate, params: {} };
  if (candidate === 'insights') return { view: 'home', params: {} };
  if (isLegacyDirectRouteId(candidate)) return { view: candidate, params: {} };
  if (!(candidate in legacyRouteAliases)) return null;
  const alias = legacyRouteAliases[candidate as LegacyRouteId];
  if (!alias) return null;
  return { view: alias.view, params: { ...alias.params } };
}
