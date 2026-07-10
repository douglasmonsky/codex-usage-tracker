import type { DiagnosticSnapshotDefinition, DiagnosticSnapshotPayload } from '../../api/diagnostics';
import { formatCompact, formatNumber, money, pct } from '../shared/format';

type SnapshotMetric = {
  label: string;
  value: string;
};

type SnapshotChildRow = {
  label: string;
  value: string;
};

export type SnapshotRow = {
  label: string;
  detail: string;
  value: string;
  recordId?: string;
  children?: SnapshotChildRow[];
};

export type SnapshotCard = {
  title: string;
  status: string;
  subtitle: string;
  metrics: SnapshotMetric[];
  rows: SnapshotRow[];
};

export function snapshotCard(definition: DiagnosticSnapshotDefinition, payload?: DiagnosticSnapshotPayload): SnapshotCard {
  const status = stringValue(payload?.status) || 'missing';
  const subtitle = snapshotSubtitle(payload);
  switch (definition.key) {
    case 'overview':
      return overviewCard(definition, payload, status, subtitle);
    case 'toolOutput':
      return toolOutputCard(definition, payload, status, subtitle);
    case 'commands':
      return commandsCard(definition, payload, status, subtitle);
    case 'gitInteractions':
      return gitInteractionsCard(definition, payload, status, subtitle);
    case 'fileReads':
      return fileReadsCard(definition, payload, status, subtitle);
    case 'fileModifications':
      return fileModificationsCard(definition, payload, status, subtitle);
    case 'readProductivity':
      return readProductivityCard(definition, payload, status, subtitle);
    case 'concentration':
      return concentrationCard(definition, payload, status, subtitle);
    case 'guidedSummary':
      return guidedSummaryCard(definition, payload, status, subtitle);
    case 'usageDrain':
      return usageDrainCard(definition, payload, status, subtitle);
  }
}

function overviewCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const overview = objectValue(payload?.overview);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Usage rows', numberText(overview?.usage_rows)),
      metric('Total tokens', tokenText(overview?.total_tokens)),
      metric('Cache ratio', ratioText(overview?.cache_ratio)),
    ],
    rows: [
      row('Threads', 'Distinct aggregate thread labels', numberText(overview?.thread_count)),
      row('Models', 'Distinct model labels', numberText(overview?.model_count)),
    ],
  };
}

function toolOutputCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  const functions = listValue(payload?.functions);
  const commandRoots = listValue(payload?.command_roots);
  const rows = functions.length ? functions : commandRoots;
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Function calls', numberText(summary?.function_calls)),
      metric('Function outputs', numberText(summary?.function_outputs)),
      metric('Original tokens', tokenText(summary?.original_token_sum)),
    ],
    rows: rows.map(item =>
      row(
        stringValue(item.function) || stringValue(item.root) || 'tool',
        `${numberText(item.calls)} calls`,
        tokenText(item.original_token_sum),
        recordIdFromSnapshotRow(item),
      ),
    ),
  };
}

function commandsCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  const commands = listValue(payload?.commands);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Shell calls', numberText(summary?.shell_function_calls)),
      metric('Roots', numberText(summary?.command_root_count)),
      metric('Missing root', numberText(summary?.missing_command)),
    ],
    rows: commands.map(item => {
      const children = commandChildren(item.children);
      return row(
        stringValue(item.root) || 'command',
        children.length ? `${numberText(children.length)} child commands` : 'No child commands',
        numberText(item.total),
        recordIdFromSnapshotRow(item),
        children,
      );
    }),
  };
}

function gitInteractionsCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Git calls', numberText(summary?.git_shell_calls)),
      metric('Git commands', numberText(summary?.git_command_calls)),
      metric('GitHub CLI', numberText(summary?.github_cli_calls)),
    ],
    rows: listValue(payload?.interactions).map(item =>
      row(
        stringValue(item.operation) || stringValue(item.root) || 'git',
        stringValue(item.category) || stringValue(item.mutability) || stringValue(item.root),
        numberText(item.calls),
        recordIdFromSnapshotRow(item),
      ),
    ),
  };
}

function fileReadsCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  const readers = listValue(payload?.by_reader);
  const paths = listValue(payload?.top_paths);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Read events', numberText(summary?.read_events)),
      metric('Readers', numberText(readers.length)),
      metric('Output tokens', tokenText(summary?.allocated_output_token_sum)),
    ],
    rows: (readers.length ? readers : paths).map(item =>
      row(
        stringValue(item.reader) || pathLabel(item),
        `${numberText(item.read_events)} reads`,
        tokenText(item.allocated_output_token_sum),
        recordIdFromSnapshotRow(item),
      ),
    ),
  };
}

function fileModificationsCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  const paths = listValue(payload?.top_paths);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Events', numberText(summary?.modification_events)),
      metric('Unique paths', numberText(summary?.unique_paths_modified)),
      metric('Largest event', numberText(summary?.largest_event_path_count)),
    ],
    rows: (paths.length ? paths : listValue(payload?.by_extension)).map(item =>
      row(
        pathLabel(item) || stringValue(item.extension) || 'path',
        'Modification events',
        numberText(item.modification_events ?? item.count),
        recordIdFromSnapshotRow(item),
      ),
    ),
  };
}

function readProductivityCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Read events', numberText(summary?.read_events)),
      metric('Modified later', numberText(summary?.read_events_modified_later)),
      metric('Rate', ratioText(summary?.read_events_modified_later_pct)),
    ],
    rows: listValue(payload?.by_reader).map(item =>
      row(
        stringValue(item.reader) || 'reader',
        `${numberText(item.read_events_modified_later)} modified later`,
        ratioText(item.read_events_modified_later_pct),
        recordIdFromSnapshotRow(item),
      ),
    ),
  };
}

function concentrationCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  const dimensions = listValue(payload?.dimensions);
  const impactRows = listValue(payload?.largest_impact_rows);
  const topRows = dimensions.flatMap(item => listValue(item.top_rows)).concat(impactRows);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Usage rows', numberText(summary?.usage_rows)),
      metric('Top thread share', ratioText(summary?.top_thread_share ?? dimensions[0]?.top_1_share)),
      metric('Groups', numberText(dimensions[0]?.group_count)),
    ],
    rows: topRows.map(item =>
      row(
        stringValue(item.label) || stringValue(item.dimension) || 'group',
        stringValue(item.dimension) || 'largest impact',
        ratioText(item.share),
        stringValue(item.largest_record_id),
      ),
    ),
  };
}

function guidedSummaryCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  const drivers = listValue(payload?.drivers);
  const signals = listValue(payload?.signals);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Usage rows', numberText(summary?.usage_rows)),
      metric('Total tokens', tokenText(summary?.total_tokens)),
      metric('Cache ratio', ratioText(summary?.cache_ratio)),
    ],
    rows: (drivers.length ? drivers : signals).map(item =>
      row(
        stringValue(item.title) || 'driver',
        stringValue(item.label) || stringValue(item.finding) || stringValue(item.severity),
        item.share === null || item.share === undefined ? stringValue(item.action) || 'review' : ratioText(item.share),
        recordIdFromSnapshotRow(item),
      ),
    ),
  };
}

function usageDrainCard(
  definition: DiagnosticSnapshotDefinition,
  payload: DiagnosticSnapshotPayload | undefined,
  status: string,
  subtitle: string,
): SnapshotCard {
  const summary = objectValue(payload?.summary);
  const curves = objectValue(payload?.thread_cost_curves);
  return {
    title: definition.title,
    status,
    subtitle,
    metrics: [
      metric('Usage rows', numberText(summary?.usage_rows)),
      metric('Estimated cost', moneyText(summary?.estimated_cost_usd)),
      metric('Usage credits', numberText(summary?.usage_credits)),
    ],
    rows: listValue(curves?.threads).map(item =>
      row(
        stringValue(item.thread) || 'thread',
        `${numberText(item.call_count)} calls`,
        moneyText(item.estimated_cost_usd),
        recordIdFromSnapshotRow(item),
      ),
    ),
  };
}

function metric(label: string, value: string): SnapshotMetric {
  return { label, value };
}

function snapshotSubtitle(payload?: DiagnosticSnapshotPayload): string {
  const snapshot = payload?.snapshot && typeof payload.snapshot === 'object' ? objectValue(payload.snapshot) : null;
  if (snapshot) {
    const computed = snapshot.computed_at ? `Computed ${shortTimestamp(String(snapshot.computed_at))}` : 'Computed unknown time';
    const fields = [
      computed,
      `history ${stringValue(snapshot.history_scope) || 'active'}`,
      `logs scanned ${tokenText(snapshot.source_logs_scanned)}`,
    ];
    if (snapshot.usage_rows_scanned !== undefined && snapshot.usage_rows_scanned !== null) {
      fields.push(`rows scanned ${tokenText(snapshot.usage_rows_scanned)}`);
    }
    return fields.join(' · ');
  }
  const payloadScope = stringValue(payload?.history_scope);
  if (payloadScope) return `history ${payloadScope} · no stored snapshot`;
  return 'Aggregate fallback module';
}

function row(label: string, detail: string, value: string, recordId = '', children: SnapshotChildRow[] = []): SnapshotRow {
  return { label, detail, value, recordId: recordId || undefined, children: children.length ? children : undefined };
}

function commandChildren(value: unknown): SnapshotChildRow[] {
  return listValue(value).map(child => ({
    label: stringValue(child.child) || '<child>',
    value: numberText(child.count),
  }));
}

function recordIdFromSnapshotRow(row: Record<string, unknown>): string {
  const direct = [
    row.record_id,
    row.recordId,
    row.largest_record_id,
    row.largestRecordId,
    row.representative_record_id,
    row.sample_record_id,
    row.latest_record_id,
    row.first_record_id,
  ].map(stringValue).find(Boolean);
  if (direct) return direct;

  const recordIds = row.record_ids;
  if (Array.isArray(recordIds)) {
    const first = recordIds.map(stringValue).find(Boolean);
    if (first) return first;
  }

  return '';
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function listValue(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? (value.filter(item => item && typeof item === 'object') as Array<Record<string, unknown>>)
    : [];
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function numberValue(value: unknown): number {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
}

function numberText(value: unknown): string {
  return formatNumber(numberValue(value));
}

function tokenText(value: unknown): string {
  return formatCompact(numberValue(value));
}

function moneyText(value: unknown): string {
  return money(numberValue(value));
}

function ratioText(value: unknown): string {
  const numeric = numberValue(value);
  return pct(numeric <= 1 ? numeric * 100 : numeric);
}

function pathLabel(item: Record<string, unknown>): string {
  return stringValue(item.path_label) || stringValue(item.label) || stringValue(item.path_hash) || stringValue(item.path);
}

function shortTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(parsed);
}
