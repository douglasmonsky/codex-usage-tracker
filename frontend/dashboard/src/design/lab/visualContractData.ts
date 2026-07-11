export type LabView = 'overview' | 'explore' | 'investigate' | 'limits' | 'call';

export type LabDataState = 'ready' | 'loading' | 'empty' | 'stale' | 'partial' | 'error';

export type LabScenarioProps = {
  onAnnounce: (message: string) => void;
  onNavigate: (view: LabView) => void;
};

export type LabCall = {
  id: string;
  time: string;
  thread: string;
  model: string;
  tokens: number;
  cache: number;
  credits: number;
  signal: 'efficient' | 'watch' | 'risk';
};

export const labCalls: LabCall[] = [
  {
    id: 'call-1042',
    time: '14:32',
    thread: 'Allowance detector research',
    model: 'gpt-5.6',
    tokens: 184_320,
    cache: 82,
    credits: 4.8,
    signal: 'efficient',
  },
  {
    id: 'call-1038',
    time: '14:08',
    thread: 'Dashboard architecture pass',
    model: 'gpt-5.6',
    tokens: 267_440,
    cache: 41,
    credits: 8.6,
    signal: 'risk',
  },
  {
    id: 'call-1034',
    time: '13:41',
    thread: 'Parser fixture hardening',
    model: 'gpt-5.5',
    tokens: 96_210,
    cache: 67,
    credits: 2.9,
    signal: 'watch',
  },
  {
    id: 'call-1029',
    time: '12:56',
    thread: 'MCP investigation walk',
    model: 'gpt-5.6-mini',
    tokens: 72_880,
    cache: 89,
    credits: 1.7,
    signal: 'efficient',
  },
  {
    id: 'call-1022',
    time: '11:24',
    thread: 'Release evidence review',
    model: 'gpt-5.5',
    tokens: 148_060,
    cache: 54,
    credits: 4.1,
    signal: 'watch',
  },
];

export const usageTrend = [
  { label: 'Jun 23', value: 28 },
  { label: 'Jun 26', value: 34 },
  { label: 'Jun 29', value: 31 },
  { label: 'Jul 2', value: 47 },
  { label: 'Jul 5', value: 52 },
  { label: 'Jul 8', value: 61 },
  { label: 'Jul 10', value: 58 },
];

export const weeklyAllowanceTrend = [
  { label: 'May 25', value: 91 },
  { label: 'Jun 1', value: 88 },
  { label: 'Jun 8', value: 93 },
  { label: 'Jun 15', value: 89 },
  { label: 'Jun 22', value: 72 },
  { label: 'Jun 29', value: 69 },
  { label: 'Jul 6', value: 71 },
];

export const tokenFlow = [
  { label: 'Uncached', value: 176 },
  { label: 'Cache read', value: 468 },
  { label: 'Output', value: 32 },
  { label: 'Reasoning', value: 51 },
];

export const findings = [
  {
    id: 'rediscovery',
    severity: 'risk' as const,
    title: 'Repeated file rediscovery is concentrated in two threads',
    detail: 'The same 11 safe file identities were reopened 74 times after long gaps.',
    confidence: 'High confidence',
    evidence: '74 reads / 11 files',
  },
  {
    id: 'shell-churn',
    severity: 'watch' as const,
    title: 'Shell inspection loops are costing more than edits',
    detail: 'rg, sed, nl, and git sequences repeat before 38% of modified-file calls.',
    confidence: 'Medium confidence',
    evidence: '43 loops / 6 threads',
  },
  {
    id: 'warm-cache',
    severity: 'efficient' as const,
    title: 'Warm cache is protecting the allowance research workflow',
    detail: 'Recent calls retained 82-91% cache reuse despite high total context.',
    confidence: 'High confidence',
    evidence: '9 calls / 87% median',
  },
];

export const evidenceRows = [
  { thread: 'Dashboard architecture pass', pattern: 'File rediscovery', events: 31, tokens: 418_200, confidence: 'High' },
  { thread: 'Allowance detector research', pattern: 'Shell churn', events: 18, tokens: 206_440, confidence: 'Medium' },
  { thread: 'Parser fixture hardening', pattern: 'Large low-output', events: 7, tokens: 184_090, confidence: 'Medium' },
  { thread: 'Release evidence review', pattern: 'Cold resume', events: 4, tokens: 121_760, confidence: 'Low' },
];

export const callTimeline = [
  { time: '14:08:02', label: 'Call started', tone: 'neutral' as const },
  { time: '14:08:14', label: 'Repository context loaded', tone: 'positive' as const },
  { time: '14:09:21', label: 'Repeated file group detected', tone: 'warning' as const },
  { time: '14:11:06', label: 'Context compaction', tone: 'context' as const },
  { time: '14:12:48', label: 'Call completed', tone: 'neutral' as const },
];

export function compactNumber(value: number): string {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}
