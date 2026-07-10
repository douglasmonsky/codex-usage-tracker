import { ArrowLeft, ArrowRight, ArrowUpRight, Link } from 'lucide-react';
import type { ReactNode } from 'react';

import { Button, MetricReadout, StatusBadge, Surface } from '../index';
import evidenceStyles from './Evidence.module.css';
import styles from './Scenarios.module.css';
import { callTimeline, compactNumber, type LabCall, type LabScenarioProps } from './visualContractData';

type ScenarioFrameProps = {
  actions?: ReactNode;
  children: ReactNode;
  description: string;
  eyebrow: string;
  title: string;
};

export function ScenarioFrame({ actions, children, description, eyebrow, title }: ScenarioFrameProps) {
  return (
    <section className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>{eyebrow}</p>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        {actions ? <div className={styles.headerActions}>{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

type AnswerBandProps = {
  confidence: string;
  detail: string;
  evidence: string;
  label: string;
  title: string;
  tone?: 'risk' | 'caution' | 'positive';
};

export function AnswerBand({ confidence, detail, evidence, label, title, tone = 'risk' }: AnswerBandProps) {
  return (
    <section className={styles.answerBand} data-tone={tone}>
      <div>
        <p className={styles.answerLabel}>{label}</p>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
      <div className={styles.confidenceBlock}>
        <strong>{confidence}</strong>
        <span>{evidence}</span>
      </div>
    </section>
  );
}

type CallInspectorProps = {
  call: LabCall;
  fullPage?: boolean;
  onCopy?: () => void;
  onOpen?: () => void;
};

const toneForSignal = {
  efficient: 'positive',
  watch: 'caution',
  risk: 'risk',
} as const;

export function CallInspector({ call, fullPage = false, onCopy, onOpen }: CallInspectorProps) {
  const cached = Math.round(call.tokens * (call.cache / 100));
  const uncached = call.tokens - cached;

  return (
    <Surface className={evidenceStyles.inspector} aria-label="Selected call inspector">
      <div className={evidenceStyles.inspectorHero}>
        <StatusBadge tone={toneForSignal[call.signal]}>{call.signal} signal</StatusBadge>
        <strong>{call.thread}</strong>
        <span>{call.id} / {call.model} / {call.time}</span>
      </div>

      <div className={evidenceStyles.tokenRows} aria-label="Token accounting">
        <div className={evidenceStyles.tokenRow}><span>Cached input</span><strong>{compactNumber(cached)}</strong></div>
        <div className={evidenceStyles.tokenRow}><span>Uncached input</span><strong>{compactNumber(uncached)}</strong></div>
        <div className={evidenceStyles.tokenRow}><span>Output</span><strong>{compactNumber(Math.round(call.tokens * 0.06))}</strong></div>
        <div className={evidenceStyles.tokenRow}><span>Reasoning</span><strong>{compactNumber(Math.round(call.tokens * 0.09))}</strong></div>
        <div className={evidenceStyles.tokenRow}><span>Estimated credits</span><strong>{call.credits.toFixed(1)}</strong></div>
      </div>

      <div>
        <strong>Lifecycle</strong>
        <div className={evidenceStyles.timeline}>
          {callTimeline.map((item) => (
            <div className={evidenceStyles.timelineItem} key={`${item.time}-${item.label}`}>
              <span>{item.time}</span>
              <i className={evidenceStyles.timelineDot} data-tone={item.tone} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={evidenceStyles.inspectorActions}>
        <Button variant="primary" onClick={onOpen}><ArrowUpRight />{fullPage ? 'Open evidence' : 'Full investigator'}</Button>
        <Button onClick={onCopy}><Link />Copy link</Button>
      </div>
    </Surface>
  );
}

type CallScenarioProps = LabScenarioProps & {
  call: LabCall;
};

export function CallScenario({ call, onAnnounce, onNavigate }: CallScenarioProps) {
  return (
    <ScenarioFrame
      eyebrow="Call investigator"
      title={call.thread}
      description={`${call.id} / ${call.model} / started ${call.time}. Aggregate evidence first; raw local context remains explicit.`}
      actions={
        <>
          <Button onClick={() => onNavigate('explore')}><ArrowLeft />Back to Calls</Button>
          <Button onClick={() => onAnnounce('Call link copied')}><Link />Copy link</Button>
        </>
      }
    >
      <AnswerBand
        label="Why this call matters"
        title={call.signal === 'risk' ? 'Large uncached input makes this a clear investigation candidate' : 'High cache reuse kept a large-context call comparatively efficient'}
        detail="The decision summary stays visible before token details, timeline events, and optional local context."
        confidence={call.signal === 'risk' ? 'High-priority review' : 'Efficient pattern'}
        evidence={`${compactNumber(call.tokens)} tokens / ${call.cache}% cache`}
        tone={call.signal === 'risk' ? 'risk' : 'positive'}
      />

      <div className={styles.metricGrid}>
        <Surface><MetricReadout label="Total tokens" value={compactNumber(call.tokens)} detail="All four token classes below" /></Surface>
        <Surface><MetricReadout label="Cache reuse" value={`${call.cache}%`} detail="Warm context evidence" /></Surface>
        <Surface><MetricReadout label="Estimated credits" value={call.credits.toFixed(1)} detail="Medium-confidence rate card" /></Surface>
        <Surface><MetricReadout label="Context pressure" value="68%" detail="Below compaction threshold" /></Surface>
      </div>

      <div className={evidenceStyles.splitWorkspace}>
        <CallInspector
          call={call}
          fullPage
          onCopy={() => onAnnounce('Call link copied')}
          onOpen={() => onAnnounce('Evidence section focused')}
        />

        <Surface>
          <div className={styles.panelHeader}>
            <div><h2>Context attribution</h2><p>Explicit local evidence with provenance and bounded access.</p></div>
            <StatusBadge tone="context">Local content enabled</StatusBadge>
          </div>
          <div className={styles.findingList}>
            <button className={styles.findingButton} type="button" onClick={() => onAnnounce('Repository reads expanded')}>
              <i className={styles.findingSignal} data-tone="watch" />
              <span className={styles.findingCopy}><strong>Repository reads</strong><span>18 events / 11 repeated safe file identities</span></span>
              <ArrowRight />
            </button>
            <button className={styles.findingButton} type="button" onClick={() => onAnnounce('Command evidence expanded')}>
              <i className={styles.findingSignal} data-tone="risk" />
              <span className={styles.findingCopy}><strong>Command evidence</strong><span>7 repeated rg, sed, nl, and git sequences</span></span>
              <ArrowRight />
            </button>
            <button className={styles.findingButton} type="button" onClick={() => onAnnounce('Compaction evidence expanded')}>
              <i className={styles.findingSignal} data-tone="efficient" />
              <span className={styles.findingCopy}><strong>Compaction history</strong><span>One replacement summary preserved the active plan</span></span>
              <ArrowRight />
            </button>
          </div>
          <p className={styles.methodNote}>Raw snippets are never part of the default shareable view. Opening a context group is a local, explicit action.</p>
        </Surface>
      </div>
    </ScenarioFrame>
  );
}
