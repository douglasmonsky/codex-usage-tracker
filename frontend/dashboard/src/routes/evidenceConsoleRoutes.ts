import {
  FileSearch,
  Home,
  Search,
  Settings,
  TimerReset,
  type LucideIcon,
} from 'lucide-react';

export const evidenceConsoleRouteIds = [
  'home',
  'explore',
  'limits',
  'evidence',
  'settings',
] as const;

export type EvidenceConsoleRouteId = (typeof evidenceConsoleRouteIds)[number];

export const exploreModes = ['calls', 'threads'] as const;
export type ExploreMode = (typeof exploreModes)[number];

type EvidenceConsoleRoutePlacement = 'primary' | 'contextual' | 'utility';

export type EvidenceConsoleRouteDefinition = {
  id: EvidenceConsoleRouteId;
  label: string;
  description: string;
  icon: LucideIcon;
  placement: EvidenceConsoleRoutePlacement;
  capabilities: { refresh: boolean; export: boolean; copyLink: boolean };
  safeParams: readonly string[];
  handoffParams: readonly string[];
};

const capabilities = (refresh: boolean) => ({ refresh, export: true, copyLink: true });

export const evidenceConsoleRoutes = [
  {
    id: 'home',
    label: 'Home',
    description: 'Readiness and recent findings',
    icon: Home,
    placement: 'primary',
    capabilities: capabilities(true),
    safeParams: [],
    handoffParams: [],
  },
  {
    id: 'explore',
    label: 'Explore',
    description: 'Calls and threads evidence',
    icon: Search,
    placement: 'primary',
    capabilities: capabilities(true),
    safeParams: [
      'mode', 'explore', 'detail', 'call_q', 'source', 'sort', 'direction', 'density', 'page',
      'thread', 'thread_key', 'expand', 'threads', 'thread_q', 'risk', 'thread_call_sort',
      'thread_call_page', 'calls_sort', 'calls_direction', 'calls_page', 'threads_sort',
      'threads_direction', 'threads_page',
    ],
    handoffParams: [
      'mode', 'explore', 'detail', 'source', 'sort', 'direction', 'density', 'page',
      'thread_key', 'expand', 'risk', 'thread_call_sort', 'thread_call_page',
      'calls_sort', 'calls_direction', 'calls_page', 'threads_sort', 'threads_direction',
      'threads_page',
    ],
  },
  {
    id: 'limits',
    label: 'Limits',
    description: 'Allowance status and evidence',
    icon: TimerReset,
    placement: 'primary',
    capabilities: capabilities(true),
    safeParams: [
      'usage_plan', 'usage_effort', 'usage_subagents', 'usage_sample', 'usage_confidence',
      'limit_window', 'limit_hypothesis', 'operation', 'window', 'range', 'analysis_id',
    ],
    handoffParams: [
      'usage_plan', 'usage_effort', 'usage_subagents', 'usage_sample', 'usage_confidence',
      'limit_window', 'limit_hypothesis', 'operation', 'window', 'range', 'analysis_id',
    ],
  },
  {
    id: 'evidence',
    label: 'Evidence',
    description: 'Contextual supporting records',
    icon: FileSearch,
    placement: 'contextual',
    capabilities: capabilities(false),
    safeParams: [
      'kind', 'record', 'record_id', 'thread_key', 'analysis_id', 'finding_id', 'evidence_id',
      'return', 'return_mode', 'mode', 'max_entries', 'max_chars', 'include_tool_output',
      'include_compaction_history',
    ],
    handoffParams: [
      'kind', 'record', 'thread_key', 'analysis_id', 'finding_id', 'evidence_id', 'return',
      'return_mode', 'mode',
    ],
  },
  {
    id: 'settings',
    label: 'Settings',
    description: 'Local configuration',
    icon: Settings,
    placement: 'utility',
    capabilities: capabilities(true),
    safeParams: [],
    handoffParams: [],
  },
] as const satisfies readonly EvidenceConsoleRouteDefinition[];

export const evidenceConsolePrimaryRoutes = evidenceConsoleRoutes.filter(
  route => route.placement === 'primary',
);

export const evidenceConsoleSettingsRoute = evidenceConsoleRoutes[4];

const evidenceConsoleRouteIdSet = new Set<string>(evidenceConsoleRouteIds);

export function isEvidenceConsoleRouteId(value: unknown): value is EvidenceConsoleRouteId {
  return typeof value === 'string' && evidenceConsoleRouteIdSet.has(value);
}
