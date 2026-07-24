import { useState } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import type { DashboardViewId } from '../../routes/dashboardSearch';
import {
  legacyWorkbenchDescriptors,
  type LegacyWorkbenchViewId,
} from '../../data/legacyWorkbenchDescriptors';
import { Button, StatusBadge, Surface } from '../../design';
import { copyText } from '../shared/copyText';
import styles from './LegacyWorkbenchNotice.module.css';

type LegacyWorkbenchNoticeProps = {
  viewId: LegacyWorkbenchViewId;
  onNavigate: (view: DashboardViewId) => void;
};

export function LegacyWorkbenchNotice({
  viewId,
  onNavigate,
}: LegacyWorkbenchNoticeProps) {
  const i18n = useShellI18n();
  const route = legacyWorkbenchDescriptors[viewId];
  const [copyStatus, setCopyStatus] = useState('');
  const replacementOperation = route.replacementMcpOperation;
  const noticeOnlyIn = route.noticeOnlyIn;
  const removalRelease = route.removalRelease;
  const replacementPrompt = i18n.formatText(
    i18n.t(
      'compatibility.prompt_template',
      'Use Codex Usage Tracker to replace the retired {feature} dashboard. Start with: {operation}. Summarize the result and cite the exact evidence identifiers.',
    ),
    { feature: route.label, operation: replacementOperation },
  );

  async function copyReplacementPrompt() {
    try {
      const copied = await copyText(replacementPrompt);
      setCopyStatus(
        copied
          ? i18n.t('compatibility.prompt_copied', 'Replacement prompt copied')
          : i18n.t(
              'compatibility.prompt_copy_failed',
              'Unable to copy replacement prompt',
            ),
      );
    } catch {
      setCopyStatus(
        i18n.t(
          'compatibility.prompt_copy_failed',
          'Unable to copy replacement prompt',
        ),
      );
    }
  }

  return (
    <main className={styles.page}>
      <Surface className={styles.notice}>
        <div className={styles.heading}>
          <div>
            <p className={styles.eyebrow}>
              {i18n.t('compatibility.eyebrow', 'Compatibility route')}
            </p>
            <h1>{route.label}</h1>
          </div>
          <StatusBadge tone="caution">
            {i18n.t('compatibility.notice_only', 'Notice only')}
          </StatusBadge>
        </div>

        <p className={styles.summary}>
          {i18n.t(
            'compatibility.notice',
            'This legacy workbench is notice-only. Its previous dashboard queries and background jobs are no longer loaded.',
          )}
        </p>

        <p className={styles.summary}>
          {i18n.formatText(
            i18n.t(
              'compatibility.backend_support',
              'CLI, HTTP API, export, and full-profile MCP compatibility remain available through {release}.',
            ),
            { release: noticeOnlyIn },
          )}
        </p>

        <dl className={styles.metadata}>
          <div>
            <dt>
              {i18n.t('compatibility.prior_feature', 'Previous feature')}
            </dt>
            <dd>{route.description}</dd>
          </div>
          <div>
            <dt>
              {i18n.t(
                'compatibility.replacement_request',
                'Replacement core request',
              )}
            </dt>
            <dd>
              <code>{replacementOperation}</code>
            </dd>
          </div>
          <div>
            <dt>
              {i18n.t(
                'compatibility.final_support',
                'Final supported release',
              )}
            </dt>
            <dd>{noticeOnlyIn}</dd>
          </div>
          <div>
            <dt>
              {i18n.t('compatibility.removal_release', 'Removal release')}
            </dt>
            <dd>{removalRelease}</dd>
          </div>
        </dl>

        <div className={styles.prompt}>
          <p>{replacementPrompt}</p>
          <Button variant="primary" onClick={() => void copyReplacementPrompt()}>
            {i18n.t(
              'compatibility.copy_prompt',
              'Copy replacement prompt',
            )}
          </Button>
        </div>

        <div
          className={styles.actions}
          role="group"
          aria-label={i18n.t(
            'compatibility.destinations_aria',
            'Supported Evidence Console destinations',
          )}
        >
          <Button onClick={() => onNavigate('evidence')}>
            {i18n.t('compatibility.open_evidence', 'Open Evidence')}
          </Button>
          <Button onClick={() => onNavigate('explore')}>
            {i18n.t('compatibility.open_explore', 'Open Explore')}
          </Button>
          <Button onClick={() => onNavigate('limits')}>
            {i18n.t('compatibility.open_limits', 'Open Limits')}
          </Button>
        </div>

        <p className={styles.status} role="status" aria-live="polite">
          {copyStatus}
        </p>
      </Surface>
    </main>
  );
}
