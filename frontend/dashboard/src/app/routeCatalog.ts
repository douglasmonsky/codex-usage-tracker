import {
  BarChart3,
  BookOpen,
  BrainCircuit,
  Database,
  FlaskConical,
  Home,
  Search,
  Table2,
  TimerReset,
  Workflow,
  type LucideIcon,
} from 'lucide-react';

import type { DashboardViewId } from '../routes/dashboardSearch';
import {
  evidenceConsolePrimaryRoutes,
  evidenceConsoleRoutes,
} from './evidenceConsoleRoutes';

type RouteMaturity = 'stable' | 'experimental';
type RoutePlacement = 'primary' | 'contextual' | 'utility' | 'hidden';
type RouteLifecycle = 'active' | 'transitioning' | 'deprecated';
export type DashboardExposurePhase = 'foundation' | 'simplified';

export type DashboardRouteDefinition = {
  id: DashboardViewId;
  label: string;
  description: string;
  icon: LucideIcon;
  maturity: RouteMaturity;
  placement: RoutePlacement;
  lifecycle: RouteLifecycle;
  navigationGroup: 'primary' | 'experimental' | null;
  experimentalNavigationEligible: boolean;
  capabilities: { refresh: boolean; export: boolean; copyLink: boolean };
  safeParams: readonly string[];
  handoffParams: readonly string[];
  replacementMcpOperation?: string;
};

const capabilities = (refresh: boolean) => ({ refresh, export: true, copyLink: true });

const legacyRouteCatalog = [
  {
    id: 'overview', label: 'Overview', description: 'High-level telemetry', icon: Home,
    maturity: 'stable', placement: 'hidden', lifecycle: 'transitioning', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(true), safeParams: [], handoffParams: [],
  },
  {
    id: 'investigator', label: 'Investigate', description: 'Root-cause evidence', icon: FlaskConical,
    maturity: 'experimental', placement: 'hidden', lifecycle: 'deprecated', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(false), safeParams: ['finding'], handoffParams: ['finding'],
    replacementMcpOperation: 'usage_analyze + usage_evidence',
  },
  {
    id: 'compression-lab', label: 'Compression Lab', description: 'Context savings', icon: BrainCircuit,
    maturity: 'experimental', placement: 'hidden', lifecycle: 'deprecated', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(false), safeParams: [], handoffParams: [],
    replacementMcpOperation: 'usage_analyze(goal="token_waste")',
  },
  {
    id: 'calls', label: 'Calls', description: 'Model-call table', icon: Table2,
    maturity: 'stable', placement: 'hidden', lifecycle: 'transitioning', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(true),
    safeParams: ['explore', 'detail', 'call_q', 'source', 'sort', 'direction', 'density', 'page'],
    handoffParams: ['explore', 'detail', 'source', 'sort', 'direction', 'density', 'page'],
  },
  {
    id: 'call', label: 'Call Investigator', description: 'Selected call evidence', icon: Search,
    maturity: 'stable', placement: 'hidden', lifecycle: 'transitioning', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(false),
    safeParams: ['record', 'return', 'mode', 'max_entries', 'max_chars', 'include_tool_output', 'include_compaction_history'],
    handoffParams: ['record', 'return', 'mode'],
  },
  {
    id: 'threads', label: 'Threads', description: 'Thread efficiency', icon: Workflow,
    maturity: 'stable', placement: 'hidden', lifecycle: 'transitioning', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(true),
    safeParams: ['thread', 'thread_key', 'expand', 'threads', 'thread_q', 'risk', 'thread_call_sort', 'thread_call_page'],
    handoffParams: ['thread_key', 'expand', 'risk', 'thread_call_sort', 'thread_call_page'],
  },
  {
    id: 'usage-drain', label: 'Legacy Limits', description: 'Allowance intelligence', icon: TimerReset,
    maturity: 'stable', placement: 'hidden', lifecycle: 'transitioning', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(true),
    safeParams: ['usage_plan', 'usage_effort', 'usage_subagents', 'usage_sample', 'usage_confidence', 'limit_window', 'limit_hypothesis'],
    handoffParams: ['usage_plan', 'usage_effort', 'usage_subagents', 'usage_sample', 'usage_confidence', 'limit_window', 'limit_hypothesis'],
  },
  {
    id: 'cache-context', label: 'Cache And Context', description: 'Cache and cold resumes', icon: Database,
    maturity: 'experimental', placement: 'hidden', lifecycle: 'deprecated', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(true), safeParams: ['cache_thread'], handoffParams: [],
    replacementMcpOperation: 'usage_analyze(goal="cache_failure")',
  },
  {
    id: 'diagnostics', label: 'Diagnostics Notebook', description: 'Technical report', icon: BookOpen,
    maturity: 'experimental', placement: 'hidden', lifecycle: 'deprecated', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(false),
    safeParams: ['diagnostic_source', 'diagnostic_fact'],
    handoffParams: ['diagnostic_source', 'diagnostic_fact'],
    replacementMcpOperation: 'usage_query + usage_evidence',
  },
  {
    id: 'reports', label: 'Reports', description: 'Generated analyses', icon: BarChart3,
    maturity: 'experimental', placement: 'hidden', lifecycle: 'deprecated', navigationGroup: null,
    experimentalNavigationEligible: false, capabilities: capabilities(true), safeParams: ['report'], handoffParams: ['report'],
    replacementMcpOperation: 'usage_analyze or usage_query',
  },
] as const satisfies readonly DashboardRouteDefinition[];

const targetRouteCatalog: DashboardRouteDefinition[] = evidenceConsoleRoutes.map(route => ({
  ...route,
  maturity: 'stable',
  lifecycle: 'active',
  navigationGroup: route.placement === 'primary' ? 'primary' : null,
  experimentalNavigationEligible: false,
}));

export const routeCatalog: readonly DashboardRouteDefinition[] = [
  ...targetRouteCatalog,
  ...legacyRouteCatalog,
];

export type CompatibilityLabRoute = Pick<
  DashboardRouteDefinition,
  'id' | 'label' | 'maturity' | 'lifecycle'
> & { replacementMcpOperation: string };

export const compatibilityLabRoutes: readonly CompatibilityLabRoute[] = legacyRouteCatalog.flatMap(route => (
  'replacementMcpOperation' in route && route.replacementMcpOperation
    ? [{
        id: route.id,
        label: route.label,
        maturity: route.maturity,
        lifecycle: route.lifecycle,
        replacementMcpOperation: route.replacementMcpOperation,
      }]
    : []
));

const foundationRouteIds: readonly DashboardViewId[] = [
  'overview', 'investigator', 'compression-lab', 'calls', 'threads',
  'usage-drain', 'cache-context', 'diagnostics', 'reports', 'settings',
];

export function routeDefinition(view: DashboardViewId): DashboardRouteDefinition {
  const definition = routeCatalog.find(route => route.id === view);
  if (!definition) throw new Error(`Unknown dashboard route: ${view}`);
  return definition;
}

export function navigationForPhase(phase: DashboardExposurePhase): DashboardRouteDefinition[] {
  if (phase === 'foundation') return foundationRouteIds.map(routeDefinition);
  return evidenceConsolePrimaryRoutes.map(route => routeDefinition(route.id));
}
