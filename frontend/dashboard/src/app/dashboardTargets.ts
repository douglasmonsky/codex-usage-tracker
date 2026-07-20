import { isDashboardViewId, type DashboardViewId } from '../routes/dashboardSearch';
import { routeDefinition } from './routeCatalog';

type DashboardPrivacyMode = 'normal' | 'redacted' | 'strict';
type DashboardHistory = 'active' | 'all';

export type DashboardTarget = {
  schema: 'codex-usage-tracker-dashboard-target-v1';
  view: DashboardViewId;
  record_id?: string;
  thread_key?: string;
  diagnostic_fact?: string;
  limit_evidence?: string;
  filters: Record<string, string | number | boolean>;
  history: DashboardHistory;
  privacy_mode: DashboardPrivacyMode;
  relative_url: string;
  absolute_url: string | null;
  fallback_instruction: string | null;
};

export type DashboardTargetInput = {
  view: string;
  record_id?: unknown;
  thread_key?: unknown;
  diagnostic_fact?: unknown;
  limit_evidence?: unknown;
  filters?: Record<string, unknown>;
  history?: unknown;
  privacy_mode?: unknown;
  service_origin?: string | null;
};

const fallbackInstruction = 'codex-usage-tracker serve-dashboard --open';
const canonicalParams = new Set(['history', 'record', 'thread_key', 'diagnostic_fact', 'limit_hypothesis']);
const recordId = /^(?:[0-9a-f]{64}|record-[0-9]{1,10})$/;
const sessionThreadKey = /^session:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const diagnosticFact = /^(?:activity|command_family|compaction|function|loop|mcp_server|mcp_tool|outcome|skill|tool):[a-z0-9_.:-]{1,80}$/;
const limitEvidence = new Set(['stable', 'decreased']);
const reportIds = new Set([
  'fast-mode-proxy', 'cost-curves', 'usage-remaining',
  'allowance-change', 'weekly-credits', 'usage-drain-model',
]);
const enumFilters: Record<string, ReadonlySet<string>> = {
  explore: new Set(['calls', 'tools', 'files']),
  detail: new Set(['first']),
  source: new Set(['all', 'project', 'session', 'git', 'source-file', 'missing']),
  sort: new Set(['time', 'duration', 'gap', 'attention', 'thread', 'initiator', 'model', 'effort', 'total', 'cached', 'uncached', 'output', 'reasoning', 'cost', 'usage', 'cache', 'context']),
  direction: new Set(['asc', 'desc']), density: new Set(['dense', 'roomy']),
  return: new Set(['overview', 'investigator', 'compression-lab', 'calls', 'threads', 'usage-drain', 'cache-context', 'diagnostics', 'reports', 'settings']),
  mode: new Set(['summary', 'full']), expand: new Set(['first', 'all']),
  risk: new Set(['all', 'Low', 'Medium', 'High']),
  thread_call_sort: new Set(['newest', 'duration', 'gap', 'initiator', 'model', 'effort', 'tokens', 'cached', 'uncached', 'output', 'reasoning', 'cost', 'cache']),
  usage_plan: new Set(['Weekly', 'weekly', 'five_hour']),
  usage_effort: new Set(['low', 'medium', 'high']),
  limit_window: new Set(['weekly', 'five_hour']),
  diagnostic_source: new Set(['facts', 'tools', 'compactions']),
};
const integerFilters: Record<string, readonly [number, number]> = {
  finding: [1, 10_000], page: [1, 10_000], thread_call_page: [1, 10_000], usage_sample: [1, 10_000],
};

export function buildDashboardTarget(input: DashboardTargetInput): DashboardTarget {
  if (!isDashboardViewId(input.view)) throw new Error(`Unknown dashboard view: ${input.view}`);
  const privacyMode = normalizePrivacyMode(input.privacy_mode);
  const history = normalizeHistory(input.history);
  const handoffParams = new Set(routeDefinition(input.view).handoffParams);
  const filters = normalizeFilters(input.filters ?? {}, handoffParams);
  const query = new Map<string, string>([['view', input.view]]);
  const target: DashboardTarget = {
    schema: 'codex-usage-tracker-dashboard-target-v1',
    view: input.view,
    filters,
    history,
    privacy_mode: privacyMode,
    relative_url: '',
    absolute_url: null,
    fallback_instruction: fallbackInstruction,
  };

  addSelector(target, query, handoffParams, input.view, 'record_id', 'record', input.record_id, 'call', privacyMode);
  addSelector(target, query, handoffParams, input.view, 'thread_key', 'thread_key', input.thread_key, 'threads', privacyMode);
  addSelector(target, query, handoffParams, input.view, 'diagnostic_fact', 'diagnostic_fact', input.diagnostic_fact, 'diagnostics', privacyMode);
  addSelector(target, query, handoffParams, input.view, 'limit_evidence', 'limit_hypothesis', input.limit_evidence, 'usage-drain', privacyMode);
  Object.entries(filters).forEach(([key, value]) => query.set(key, queryValue(value)));
  if (history !== 'active') query.set('history', history);

  const params = new URLSearchParams([...query.entries()].sort(([left], [right]) => left.localeCompare(right)));
  target.relative_url = `/react-dashboard.html?${params.toString()}`;
  const origin = normalizeLoopbackOrigin(input.service_origin);
  if (origin) {
    target.absolute_url = `${origin}${target.relative_url}`;
    target.fallback_instruction = null;
  }
  return target;
}

export function dashboardTargetPrompt(target: DashboardTarget): string {
  const destination = target.absolute_url ?? target.relative_url;
  const fallback = target.fallback_instruction ? ` If needed, run: ${target.fallback_instruction}.` : '';
  return `Open the ${target.view} usage dashboard at ${destination}.${fallback}`;
}

function normalizeFilters(
  input: Record<string, unknown>,
  safeParams: ReadonlySet<string>,
): Record<string, string | number | boolean> {
  const normalized: Record<string, string | number | boolean> = {};
  Object.keys(input).sort().forEach(key => {
    if (!safeParams.has(key) || canonicalParams.has(key)) return;
    const value = normalizeFilterValue(key, input[key]);
    if (value !== null) normalized[key] = value;
  });
  return normalized;
}

function addSelector(
  target: DashboardTarget,
  query: Map<string, string>,
  safeParams: ReadonlySet<string>,
  view: DashboardViewId,
  targetKey: 'record_id' | 'thread_key' | 'diagnostic_fact' | 'limit_evidence',
  queryKey: string,
  value: unknown,
  requiredView: DashboardViewId,
  privacyMode: DashboardPrivacyMode,
): void {
  if (value === undefined || value === null) return;
  if (view !== requiredView || !safeParams.has(queryKey)) throw new Error(`${targetKey} is not allowed for ${view}`);
  const normalized = normalizeIdentifier(value, targetKey, privacyMode);
  if (!normalized) throw new Error(`${targetKey} must be a bounded privacy-safe identifier`);
  target[targetKey] = normalized;
  query.set(queryKey, normalized);
}

function normalizeFilterValue(key: string, value: unknown): string | number | boolean | null {
  const allowed = enumFilters[key];
  if (allowed) {
    const candidate = typeof value === 'string' ? value.trim() : '';
    return allowed.has(candidate) ? candidate : null;
  }
  const range = integerFilters[key];
  if (range) return integerInRange(value, range[0], range[1]);
  if (key === 'usage_subagents') {
    if (typeof value === 'boolean') return value;
    return integerInRange(value, 0, 100);
  }
  if (key === 'usage_confidence') {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) return null;
    return Object.is(value, -0) || Number.isInteger(value) ? Math.trunc(value) : value;
  }
  if (key === 'report') return typeof value === 'string' && reportIds.has(value) ? value : null;
  return null;
}

function integerInRange(value: unknown, minimum: number, maximum: number): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum ? value : null;
}

function normalizeIdentifier(
  value: unknown,
  targetKey: 'record_id' | 'thread_key' | 'diagnostic_fact' | 'limit_evidence',
  privacyMode: DashboardPrivacyMode,
): string | null {
  if (typeof value !== 'string') return null;
  if (targetKey === 'record_id') return recordId.test(value) ? value : null;
  if (targetKey === 'thread_key') {
    if (sessionThreadKey.test(value)) return value;
    return privacyMode === 'normal' && normalThreadKey(value) ? value : null;
  }
  if (targetKey === 'diagnostic_fact') return diagnosticFact.test(value) ? value : null;
  return limitEvidence.has(value) ? value : null;
}

function normalThreadKey(value: string): boolean {
  if (!value.startsWith('thread:')) return false;
  const label = value.slice('thread:'.length);
  return label.length > 0 && label.length <= 80 && !/[\r\n\t/\\?#{}[\]]/.test(label);
}

function queryValue(value: string | number | boolean): string {
  if (typeof value !== 'number' || Number.isInteger(value)) return String(value);
  return value.toFixed(15).replace(/0+$/, '').replace(/\.$/, '') || '0';
}

function normalizePrivacyMode(value: unknown): DashboardPrivacyMode {
  if (value === undefined) return 'normal';
  if (value === 'normal' || value === 'redacted' || value === 'strict') return value;
  throw new Error(`Unknown privacy mode: ${String(value)}`);
}

function normalizeHistory(value: unknown): DashboardHistory {
  if (value === undefined) return 'active';
  if (value === 'active' || value === 'all') return value;
  throw new Error(`Unknown dashboard history: ${String(value)}`);
}

function normalizeLoopbackOrigin(value: string | null | undefined): string | null {
  if (!value) return null;
  const origin = new URL(value);
  if (origin.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname)) {
    throw new Error('Dashboard service origin must be loopback HTTP');
  }
  if (origin.username || origin.password) throw new Error('Dashboard service origin must not include credentials');
  const port = Number(origin.port);
  if (!origin.port || !Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error('Dashboard service origin must include port 1024 through 65535');
  }
  if (origin.pathname !== '/' || origin.search || origin.hash) throw new Error('Dashboard service origin must be an origin');
  return origin.origin;
}
