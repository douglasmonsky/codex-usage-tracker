type EvidenceKind = 'call' | 'thread' | 'finding' | 'allowance';

export type EvidenceRouteState =
  | {
      status: 'ready';
      kind: 'call' | 'thread';
      selectorId: string;
      analysisId: null;
    }
  | {
      status: 'ready';
      kind: 'finding' | 'allowance';
      selectorId: string;
      analysisId: string;
    }
  | {
      status: 'invalid';
      message: string;
    };

const SAFE_SELECTOR = /^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}$/;
const EVIDENCE_PARAMS = [
  'kind',
  'record',
  'record_id',
  'thread_key',
  'analysis',
  'analysis_id',
  'finding',
  'finding_id',
  'evidence',
  'evidence_id',
  'return',
  'return_mode',
] as const;

function selector(params: URLSearchParams, canonical: string, compatibility?: string): string | null {
  return params.get(canonical) ?? (compatibility ? params.get(compatibility) : null);
}

function isSafeSelector(value: string | null): value is string {
  return value !== null && SAFE_SELECTOR.test(value);
}

export function readEvidenceRouteState(input: string | URL): EvidenceRouteState {
  const url = input instanceof URL ? input : new URL(input);
  const kind = url.searchParams.get('kind');

  if (kind === 'call') {
    const selectorId = selector(url.searchParams, 'record', 'record_id');
    return isSafeSelector(selectorId)
      ? { status: 'ready', kind, selectorId, analysisId: null }
      : { status: 'invalid', message: 'This call evidence link is incomplete or malformed.' };
  }
  if (kind === 'thread') {
    const selectorId = url.searchParams.get('thread_key');
    return isSafeSelector(selectorId)
      ? { status: 'ready', kind, selectorId, analysisId: null }
      : { status: 'invalid', message: 'This thread evidence link is incomplete or malformed.' };
  }
  if (kind === 'finding') {
    const selectorId = selector(url.searchParams, 'finding', 'finding_id');
    const analysisId = selector(url.searchParams, 'analysis', 'analysis_id');
    return isSafeSelector(selectorId) && isSafeSelector(analysisId)
      ? { status: 'ready', kind, selectorId, analysisId }
      : { status: 'invalid', message: 'This finding evidence link is incomplete or malformed.' };
  }
  if (kind === 'allowance') {
    const selectorId = selector(url.searchParams, 'evidence', 'evidence_id');
    const analysisId = selector(url.searchParams, 'analysis', 'analysis_id');
    return isSafeSelector(selectorId) && isSafeSelector(analysisId)
      ? { status: 'ready', kind, selectorId, analysisId }
      : { status: 'invalid', message: 'This allowance evidence link is incomplete or malformed.' };
  }
  return { status: 'invalid', message: 'This evidence link uses an unsupported evidence kind.' };
}

export function normalizeEvidenceUrl(input: string | URL): URL {
  const url = input instanceof URL ? new URL(input) : new URL(input);
  if (url.searchParams.get('view') === 'call') {
    url.searchParams.set('view', 'evidence');
    if (!url.searchParams.has('kind')) url.searchParams.set('kind', 'call');
  }
  const aliases = [
    ['record', 'record_id'],
    ['analysis', 'analysis_id'],
    ['finding', 'finding_id'],
    ['evidence', 'evidence_id'],
  ] as const;
  for (const [canonical, compatibility] of aliases) {
    if (!url.searchParams.has(canonical) && url.searchParams.has(compatibility)) {
      url.searchParams.set(canonical, url.searchParams.get(compatibility) ?? '');
    }
    url.searchParams.delete(compatibility);
  }
  return url;
}

function defaultReturn(kind: EvidenceKind): { view: string; mode?: string } {
  if (kind === 'call') return { view: 'explore', mode: 'calls' };
  if (kind === 'thread') return { view: 'explore', mode: 'threads' };
  if (kind === 'allowance') return { view: 'limits' };
  return { view: 'home' };
}

export function buildEvidenceReturnUrl(input: string | URL): URL {
  const url = normalizeEvidenceUrl(input);
  const state = readEvidenceRouteState(url);
  const requestedKind = url.searchParams.get('kind');
  const fallbackKind = state.status === 'ready'
    ? state.kind
    : isEvidenceKind(requestedKind) ? requestedKind : null;
  const fallback = fallbackKind ? defaultReturn(fallbackKind) : { view: 'home' };
  const requestedView = url.searchParams.get('return');
  const view = requestedView && requestedView !== 'evidence' ? requestedView : fallback.view;
  const mode = view === 'explore' ? url.searchParams.get('return_mode') ?? fallback.mode : undefined;

  for (const parameter of EVIDENCE_PARAMS) url.searchParams.delete(parameter);
  url.searchParams.set('view', view);
  if (mode) url.searchParams.set('mode', mode);
  else url.searchParams.delete('mode');
  if (state.status === 'ready' && state.kind === 'thread' && view === 'explore') {
    url.searchParams.set('thread_key', state.selectorId);
  }
  if (state.status === 'ready' && state.kind === 'allowance' && view === 'limits') {
    url.searchParams.set('analysis_id', state.analysisId);
  }
  return url;
}

function isEvidenceKind(value: string | null): value is EvidenceKind {
  return value === 'call' || value === 'thread' || value === 'finding' || value === 'allowance';
}
