import { createContext, useContext, type ReactNode } from 'react';
import { createShellI18n, type ShellI18n } from './i18n';

const fallbackShellI18n = createShellI18n(null, 'en');
const ShellI18nContext = createContext<ShellI18n>(fallbackShellI18n);

export function ShellI18nProvider({ value, children }: { value: ShellI18n; children: ReactNode }) {
  return <ShellI18nContext.Provider value={value}>{children}</ShellI18nContext.Provider>;
}

export function useShellI18n(): ShellI18n {
  return useContext(ShellI18nContext);
}
