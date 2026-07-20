import { ArrowRight, FlaskConical, Waypoints } from 'lucide-react';

import { useShellI18n } from '../app/i18nContext';
import styles from './FeatureMaturityBanner.module.css';

type FeatureMaturityBannerProps = {
  kind: 'experimental' | 'transitioning';
  title: string;
  description: string;
  className?: string;
  replacementAction?: {
    label: string;
    onSelect: () => void;
  };
};

export function FeatureMaturityBanner({
  kind,
  title,
  description,
  className,
  replacementAction,
}: FeatureMaturityBannerProps) {
  const i18n = useShellI18n();
  const Icon = kind === 'experimental' ? FlaskConical : Waypoints;
  const rootClassName = className ? `${styles.root} ${className}` : styles.root;
  const localizedTitle = i18n.translateText(title);
  const localizedDescription = i18n.translateText(description);

  return (
    <aside
      aria-label={i18n.formatText(
        i18n.t('maturity.aria', 'Feature maturity: {title}'),
        { title: localizedTitle },
      )}
      className={rootClassName}
      data-kind={kind}
      role="note"
    >
      <Icon aria-hidden="true" className={styles.icon} />
      <div className={styles.copy}>
        <strong>{localizedTitle}</strong>
        <p>{localizedDescription}</p>
      </div>
      {replacementAction ? (
        <button className={styles.action} type="button" onClick={replacementAction.onSelect}>
          {i18n.translateText(replacementAction.label)}<ArrowRight aria-hidden="true" />
        </button>
      ) : null}
    </aside>
  );
}
