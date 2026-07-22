import { ArrowLeft, Copy } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { EvidenceApiError, loadEvidence, type EvidenceEnvelope } from '../../api/evidence';
import type { ContextRuntime, DashboardModel } from '../../api/types';
import { copyText } from '../shared/copyText';
import { AllowanceEvidence } from './AllowanceEvidence';
import { CallEvidence } from './CallEvidence';
import {
  buildEvidenceReturnUrl,
  normalizeEvidenceUrl,
  readEvidenceRouteState,
} from './evidenceRouteState';
import { FindingEvidence } from './FindingEvidence';
import { ThreadEvidence } from './ThreadEvidence';
import styles from './EvidencePage.module.css';

type EvidencePageProps = {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onNavigateRecord: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  callBackLabel?: string;
  onCallBack?: () => void;
};

type RemoteState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; envelope: EvidenceEnvelope }
  | { status: 'error'; message: string; code: string | null };

export function EvidencePage(props: EvidencePageProps) {
  const [currentHref, setCurrentHref] = useState(() => window.location.href);
  const [copyStatus, setCopyStatus] = useState('');
  const normalizedUrl = useMemo(() => normalizeEvidenceUrl(currentHref), [currentHref]);
  const route = useMemo(() => readEvidenceRouteState(normalizedUrl), [normalizedUrl]);
  const history = normalizedUrl.searchParams.get('history') === 'all' ? 'all' : 'active';
  const [remote, setRemote] = useState<RemoteState>({ status: 'idle' });

  useEffect(() => {
    if (normalizedUrl.toString() !== window.location.href) {
      window.history.replaceState(null, '', normalizedUrl);
    }
  }, [normalizedUrl]);

  useEffect(() => {
    const update = () => setCurrentHref(window.location.href);
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);

  useEffect(() => {
    if (route.status !== 'ready' || route.kind === 'call') {
      setRemote({ status: 'idle' });
      return;
    }
    let cancelled = false;
    setRemote({ status: 'loading' });
    loadEvidence({
      kind: route.kind,
      selectorId: route.selectorId,
      analysisId: route.analysisId,
      history,
    }, props.contextRuntime)
      .then(envelope => { if (!cancelled) setRemote({ status: 'loaded', envelope }); })
      .catch(error => {
        if (cancelled) return;
        setRemote({
          status: 'error',
          message: error instanceof Error ? error.message : 'The selected evidence is unavailable.',
          code: error instanceof EvidenceApiError ? error.code : null,
        });
      });
    return () => { cancelled = true; };
  }, [history, props.contextRuntime, route]);

  const returnUrl = buildEvidenceReturnUrl(normalizedUrl);
  const backLabel = `Back to ${viewLabel(returnUrl.searchParams.get('view'))}`;

  function navigateBack() {
    window.history.pushState(null, '', returnUrl);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  async function copyLink() {
    try {
      const copied = await copyText(normalizedUrl.toString());
      if (!copied) throw new Error('Clipboard unavailable');
      setCopyStatus('Evidence link copied');
    } catch {
      setCopyStatus('Copy unavailable in this browser');
    }
  }

  if (route.status === 'invalid') {
    return <Unavailable message={route.message} backLabel={backLabel} onBack={navigateBack} />;
  }
  if (route.kind === 'call') {
    return (
      <CallEvidence
        model={props.model}
        recordId={route.selectorId}
        contextRuntime={props.contextRuntime}
        onContextApiEnabledChange={props.onContextApiEnabledChange}
        onNavigateRecord={props.onNavigateRecord}
        onCopyCallLink={props.onCopyCallLink}
        onBack={props.onCallBack ?? navigateBack}
        backLabel={props.callBackLabel ?? backLabel}
      />
    );
  }
  if (remote.status === 'idle' || remote.status === 'loading') {
    return <section className="route-state" role="status" aria-busy="true">Loading evidence…</section>;
  }
  if (remote.status === 'error') {
    const stale = remote.code === 'evidence_not_found' || remote.code === 'evidence_history_mismatch';
    return (
      <Unavailable
        message={stale ? `This saved evidence link is no longer available. ${remote.message}` : remote.message}
        backLabel={backLabel}
        onBack={navigateBack}
      />
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <button className="toolbar-button" type="button" onClick={navigateBack}>
          <ArrowLeft size={16} /> {backLabel}
        </button>
        <button className="toolbar-button" type="button" onClick={copyLink} aria-label="Copy evidence link">
          <Copy size={16} /> Copy link
        </button>
        {copyStatus ? <span role="status">{copyStatus}</span> : null}
      </div>
      {route.kind === 'thread' ? (
        <ThreadEvidence
          envelope={remote.envelope}
          runtime={props.contextRuntime}
          history={history}
          onOpenCall={props.onNavigateRecord}
        />
      ) : null}
      {route.kind === 'finding' ? <FindingEvidence envelope={remote.envelope} /> : null}
      {route.kind === 'allowance' ? (
        <AllowanceEvidence envelope={remote.envelope} analysisId={route.analysisId} />
      ) : null}
    </div>
  );
}

function Unavailable({ message, backLabel, onBack }: { message: string; backLabel: string; onBack: () => void }) {
  return (
    <section className={styles.unavailable}>
      <p className={styles.eyebrow}>Recoverable link state</p>
      <h1>Evidence unavailable</h1>
      <p>{message}</p>
      <button className="toolbar-button" type="button" onClick={onBack}>
        <ArrowLeft size={16} /> {backLabel}
      </button>
    </section>
  );
}

function viewLabel(view: string | null) {
  if (view === 'explore') return 'Explore';
  if (view === 'limits') return 'Limits';
  if (view === 'settings') return 'Settings';
  return 'Home';
}
