import { Clipboard, ExternalLink } from 'lucide-react';

import type { DashboardTarget } from '../app/dashboardTargets';
import type { ShellI18n } from '../app/i18n';
import { useShellI18n } from '../app/i18nContext';
import { Button } from '../design';
import primitiveStyles from '../design/primitives/primitives.module.css';
import { copyText } from '../features/shared/copyText';

type DashboardEvidenceActionsProps = {
  target: DashboardTarget;
  question: string;
  onStatus: (message: string) => void;
};

const fallbackQuestion = 'Investigate the selected aggregate usage evidence.';
type EvidenceI18n = Pick<ShellI18n, 't' | 'formatText'>;

export function DashboardEvidenceActions({
  target,
  question,
  onStatus,
}: DashboardEvidenceActionsProps) {
  const i18n = useShellI18n();
  const href = safeEvidenceHref(target);

  async function copyPrompt() {
    try {
      const copied = await copyText(buildInvestigationPrompt(target, question, i18n));
      onStatus(copied
        ? i18n.t('evidence.prompt_copied', 'Investigation prompt copied')
        : i18n.t('evidence.prompt_copy_failed', 'Unable to copy investigation prompt'));
    } catch {
      onStatus(i18n.t('evidence.prompt_copy_failed', 'Unable to copy investigation prompt'));
    }
  }

  function showLaunchGuidance() {
    onStatus(i18n.formatText(
      i18n.t('evidence.launch_guidance', 'Start the local dashboard first: {instruction}'),
      { instruction: target.fallback_instruction ?? 'codex-usage-tracker serve-dashboard --open' },
    ));
  }

  return (
    <div role="group" aria-label={i18n.t('evidence.actions.aria', 'Dashboard evidence actions')}>
      {href ? (
        <a
          className={`${primitiveStyles.button} ${primitiveStyles.secondary}`}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink aria-hidden="true" />{i18n.t('evidence.open', 'Open evidence')}
        </a>
      ) : (
        <Button onClick={showLaunchGuidance}>
          <ExternalLink aria-hidden="true" />{i18n.t('evidence.open', 'Open evidence')}
        </Button>
      )}
      <Button onClick={() => void copyPrompt()}>
        <Clipboard aria-hidden="true" />{i18n.t('evidence.copy_prompt', 'Copy investigation prompt')}
      </Button>
    </div>
  );
}

function buildInvestigationPrompt(
  target: DashboardTarget,
  question: string,
  i18n?: EvidenceI18n,
): string {
  const translate = i18n ?? englishEvidenceI18n;
  const safeQuestion = target.privacy_mode === 'strict'
    ? translate.t('evidence.question.default', fallbackQuestion)
    : sanitizeQuestion(question, translate.t('evidence.question.default', fallbackQuestion));
  const identifiers = [
    target.record_id && `record_id=${target.record_id}`,
    target.thread_key && `thread_key=${target.thread_key}`,
    target.diagnostic_fact && `diagnostic_fact=${target.diagnostic_fact}`,
    target.limit_evidence && `limit_evidence=${target.limit_evidence}`,
  ].filter(Boolean).join(', ') || translate.t('evidence.aggregate_selection', 'aggregate selection');
  const launch = target.absolute_url
    ? ''
    : translate.formatText(
      translate.t('evidence.prompt.launch', ' Launch locally with: {instruction}.'),
      { instruction: target.fallback_instruction ?? 'codex-usage-tracker serve-dashboard --open' },
    );
  return translate.formatText(
    translate.t(
      'evidence.prompt.template',
      '{question} Evidence: {identifiers}. Scope: history={history}, privacy_mode={privacy}. Target: {target}.{launch}',
    ),
    {
      question: safeQuestion,
      identifiers,
      history: target.history,
      privacy: target.privacy_mode,
      target: target.relative_url,
      launch,
    },
  );
}

const englishEvidenceI18n: EvidenceI18n = {
  t: (_key, fallback) => fallback ?? _key,
  formatText: (template, values) => template.replace(
    /\{([A-Za-z][A-Za-z0-9_]*)\}/gu,
    (token, key) => String(values[key] ?? token),
  ),
};

function sanitizeQuestion(question: string, defaultQuestion: string): string {
  const trimmed = question.trim();
  if (!trimmed
    || trimmed.length > 160
    || !/^[\p{L}\p{N} .,?!:'"()_%=-]+$/u.test(trimmed)
    || /(?:^|\s)\/\S+/u.test(trimmed)
    || /(?:sk-|xox[a-z]-|gh[pousr]_|github_pat_|\[redacted|bearer\s+\S{8,}|(?:api[_ -]?key|access[_ -]?token|token|secret|credential|authorization)\s*[:=]\s*\S+)/i.test(trimmed)
    || /[\r\n\t]/.test(trimmed)) {
    return defaultQuestion;
  }
  return trimmed;
}

function safeEvidenceHref(target: DashboardTarget): string | null {
  try {
    if (target.absolute_url) {
      const absolute = new URL(target.absolute_url);
      if (absolute.protocol !== 'http:' || !isLoopback(absolute.hostname) || absolute.username || absolute.password) {
        return null;
      }
      return absolute.toString();
    }
    const page = new URL(window.location.href);
    if (!['http:', 'https:'].includes(page.protocol)) return null;
    const relative = new URL(target.relative_url, page);
    return relative.origin === page.origin ? relative.toString() : null;
  } catch {
    return null;
  }
}

function isLoopback(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]';
}

export function currentDashboardServiceOrigin(href = window.location.href): string | null {
  try {
    const url = new URL(href);
    const port = Number(url.port);
    return url.protocol === 'http:'
      && isLoopback(url.hostname)
      && Number.isInteger(port)
      && port >= 1024
      && port <= 65535
      ? url.origin
      : null;
  } catch {
    return null;
  }
}
