export const legacyWorkbenchViewIds = [
  'investigator',
  'compression-lab',
  'cache-context',
  'diagnostics',
  'reports',
] as const;

export type LegacyWorkbenchViewId = (typeof legacyWorkbenchViewIds)[number];

export type LegacyWorkbenchDescriptor = {
  label: string;
  description: string;
  replacementMcpOperation: string;
  deprecatedIn: string;
  noticeOnlyIn: string;
  removalRelease: string;
};

export const legacyWorkbenchDescriptors: Record<
  LegacyWorkbenchViewId,
  LegacyWorkbenchDescriptor
> = {
  investigator: {
    label: 'Investigate',
    description: 'Root-cause evidence',
    replacementMcpOperation:
      'usage_analyze(goal="usage_spike") → usage_evidence',
    deprecatedIn: '0.23.0',
    noticeOnlyIn: '0.24.x',
    removalRelease: '0.25.0',
  },
  'compression-lab': {
    label: 'Compression Lab',
    description: 'Context savings',
    replacementMcpOperation:
      'usage_analyze(goal="token_waste"); full-profile compression tools through 0.24.x',
    deprecatedIn: '0.23.0',
    noticeOnlyIn: '0.24.x',
    removalRelease: '0.25.0',
  },
  'cache-context': {
    label: 'Cache And Context',
    description: 'Cache and cold resumes',
    replacementMcpOperation:
      'usage_analyze(goal="context_bloat") or usage_analyze(goal="cache_failure")',
    deprecatedIn: '0.23.0',
    noticeOnlyIn: '0.24.x',
    removalRelease: '0.25.0',
  },
  diagnostics: {
    label: 'Diagnostics Notebook',
    description: 'Technical report',
    replacementMcpOperation:
      'usage_query(entity="call", measures=["tokens"]) → usage_evidence',
    deprecatedIn: '0.23.0',
    noticeOnlyIn: '0.24.x',
    removalRelease: '0.25.0',
  },
  reports: {
    label: 'Reports',
    description: 'Generated analyses',
    replacementMcpOperation:
      'usage_analyze(goal="usage_spike") or usage_query(...)',
    deprecatedIn: '0.23.0',
    noticeOnlyIn: '0.24.x',
    removalRelease: '0.25.0',
  },
};
