import {
  Activity,
  AlertTriangle,
  Database,
  Gauge,
  Languages,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

import type { DashboardBootPayload, DashboardLanguage, DashboardModel } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { loadWindowLabel, type LoadWindow } from '../../data/dataScope';
import {
  allowanceWindowSubtitle,
  allowanceWindowSummary,
  projectMetadataPrivacyLabel,
  sourceHealthSummary,
  sourceLabel,
} from './settingsModel';
import { settingsSections, useSettingsSection } from './useSettingsSection';
import styles from './SettingsPage.module.css';

type HistoryScope = 'active' | 'all';

type ApplicationI18n = {
  language: string;
  direction: 'ltr' | 'rtl';
  languages: DashboardLanguage[];
};

type SettingsPageProps = {
  model: DashboardModel;
  payload: DashboardBootPayload | null;
  historyScope: HistoryScope;
  loadWindow: LoadWindow;
  loadLimit: number;
  scopeSince: string | null;
  loadedRowCount: number;
  totalAvailableRows: number;
  canUseLiveApi: boolean;
  autoRefreshEnabled: boolean;
  refreshState: string;
  applicationI18n: ApplicationI18n;
};

const sectionCopy = {
  data: ['Data', 'Loaded history and local runtime state.'],
  estimates: ['Estimates', 'Pricing and allowance inputs used for local estimates.'],
  content: ['Content Access', 'Privacy boundaries and explicit raw-context gates.'],
  application: ['Application', 'Dashboard refresh, API, and language visibility.'],
  sources: ['Source Health', 'Configuration and parser diagnostics.'],
} as const;

export function SettingsPage(props: SettingsPageProps) {
  const { selectedSection, selectSection } = useSettingsSection();
  const { model, payload, canUseLiveApi } = props;
  const contextRuntime = model.contextRuntime;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Local configuration</p>
          <h1>Settings</h1>
          <p>Inspect dashboard behavior and configuration truth without changing server-owned settings.</p>
        </div>
        <div className={styles.badges}>
          <StatusBadge label={canUseLiveApi ? 'Live API available' : 'Static snapshot'} tone={canUseLiveApi ? 'green' : 'orange'} />
          <StatusBadge label={contextRuntime.contextApiEnabled ? 'Content access enabled' : 'Content access gated'} tone={contextRuntime.contextApiEnabled ? 'blue' : 'orange'} />
        </div>
      </header>

      <nav className={styles.navigator} aria-label="Settings sections">
        {settingsSections.map(section => (
          <button
            key={section}
            type="button"
            aria-pressed={selectedSection === section}
            onClick={() => selectSection(section)}
          >
            {sectionCopy[section][0]}
          </button>
        ))}
      </nav>

      <section aria-labelledby={`settings-${selectedSection}-title`}>
        <div className={styles.sectionHeading}>
          <h2 id={`settings-${selectedSection}-title`}>{sectionCopy[selectedSection][0]}</h2>
          <p>{sectionCopy[selectedSection][1]}</p>
        </div>
        {selectedSection === 'data' && <DataSection {...props} />}
        {selectedSection === 'estimates' && <EstimatesSection payload={payload} />}
        {selectedSection === 'content' && <ContentAccessSection {...props} />}
        {selectedSection === 'application' && <ApplicationSection {...props} />}
        {selectedSection === 'sources' && <SourceHealthSection payload={payload} />}
      </section>
    </div>
  );
}

function DataSection({ payload, historyScope, loadWindow, loadLimit, loadedRowCount, totalAvailableRows }: SettingsPageProps) {
  const loadedLabel = `${formatNumber(loadedRowCount)} of ${formatNumber(totalAvailableRows || loadedRowCount)}`;
  return (
    <div className={styles.grid}>
      <FactPanel title="Loaded Data" subtitle={payload?.shell_boot ? 'Served shell payload' : 'Embedded payload'} facts={[
        ['Data window', loadWindowLabel(loadWindow, loadLimit), Gauge],
        ['Evidence rows', loadedLabel, Database],
        ['Session scope', historyScope === 'all' ? 'Include archived' : 'Active sessions', Activity],
        ['Usage index', payload?.shell_boot ? 'served shell' : 'embedded payload', Database],
      ]} />
    </div>
  );
}

function EstimatesSection({ payload }: { payload: DashboardBootPayload | null }) {
  const windows = allowanceWindowSummary(payload);
  return (
    <div className={styles.grid}>
      <FactPanel title="Estimate Inputs" subtitle="Read-only local configuration" facts={[
        ['Pricing', sourceLabel(payload?.pricing_source) || 'local pricing config', Gauge],
        ['Allowance', sourceLabel(payload?.allowance_source) || 'local allowance config', Gauge],
        ['Rate card', payload?.rate_card_configured ? 'Loaded' : 'Not loaded', Gauge],
      ]} />
      <FactPanel title="Allowance Windows" subtitle={allowanceWindowSubtitle(payload)} facts={windows.map(row => [row.label, row.value, RefreshCw])} />
    </div>
  );
}

function ContentAccessSection({ model, payload, canUseLiveApi }: SettingsPageProps) {
  const runtime = model.contextRuntime;
  const privacyMode = payload?.privacy_mode || 'aggregate-only snapshot';
  return (
    <div className={styles.grid}>
      <FactPanel title="Privacy Boundary" subtitle={privacyMode} facts={[
        ['Payload mode', privacyMode, ShieldCheck],
        ['Project metadata', projectMetadataPrivacyLabel(payload?.project_metadata_privacy, payload?.privacy_mode), ShieldCheck],
        ['Raw context', runtime.contextApiEnabled ? 'Explicit localhost request, selected call only' : 'Disabled until context API is enabled', LockKeyhole],
        ['Live requests', canUseLiveApi ? 'Local API token present' : 'Static embedded snapshot', Database],
      ]} />
      <Panel title="Content Access Rules" subtitle="Local and explicit">
        <ul className={styles.rules}>
          <li>Aggregate payloads avoid prompts, assistant text, and raw tool output.</li>
          <li>Raw context actions remain gated behind explicit Call Investigator controls.</li>
          <li>Live refresh and context requests stay local and require the dashboard API token.</li>
        </ul>
      </Panel>
    </div>
  );
}

function ApplicationSection({
  canUseLiveApi,
  autoRefreshEnabled,
  refreshState,
  applicationI18n,
}: SettingsPageProps) {
  return (
    <div className={styles.grid}>
      <FactPanel title="Dashboard Runtime" subtitle={refreshState} facts={[
        ['Data connection', canUseLiveApi ? 'Local API token present' : 'Static embedded snapshot', Database],
        ['Auto refresh', autoRefreshEnabled ? 'Enabled' : 'Paused', RefreshCw],
        ['Interface language', applicationI18n.language, Languages],
        ['Available languages', applicationI18n.languages.map(item => item.code).join(', ') || 'English (en)', Languages],
        ['Text direction', applicationI18n.direction, Languages],
      ]} />
    </div>
  );
}

function SourceHealthSection({ payload }: { payload: DashboardBootPayload | null }) {
  return (
    <div className={styles.grid}>
      <FactPanel title="Configuration Checks" subtitle="Configuration and ingestion facts" facts={sourceHealthSummary(payload).map(row => [
        row.label,
        row.value,
        row.issue ? AlertTriangle : ShieldCheck,
      ])} />
    </div>
  );
}

type Fact = readonly [label: string, value: string, icon: typeof Database];

function FactPanel({ title, subtitle, facts }: { title: string; subtitle: string; facts: readonly Fact[] }) {
  return (
    <Panel title={title} subtitle={subtitle}>
      <dl className={styles.facts}>
        {facts.map(([label, value, Icon]) => (
          <div key={label}>
            <dt><Icon aria-hidden="true" />{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}
