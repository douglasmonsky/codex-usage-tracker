import type { ReactNode } from 'react';
import { useShellI18n } from '../app/i18nContext';

type PanelProps = {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Panel({ title, subtitle, action, children, className = '' }: PanelProps) {
  const i18n = useShellI18n();
  return (
    <section className={`panel ${className}`.trim()}>
      <div className="panel-header">
        <div>
          <h2>{i18n.translateText(title)}</h2>
          {subtitle ? <p>{i18n.translateText(subtitle)}</p> : null}
        </div>
        {action ? <div className="panel-action">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}
