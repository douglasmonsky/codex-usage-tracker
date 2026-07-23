import type { LucideIcon } from 'lucide-react';
import { isDashboardViewId, type DashboardViewId } from '../routes/dashboardSearch';
import {
  evidenceConsolePrimaryRoutes,
  evidenceConsoleSettingsRoute,
} from './evidenceConsoleRoutes';

export type ViewId = DashboardViewId;

export type NavItem = {
  id: ViewId;
  label: string;
  description: string;
  icon: LucideIcon;
};

export const navItems: NavItem[] = evidenceConsolePrimaryRoutes.map(({ id, label, description, icon }) => ({
  id, label, description, icon,
}));

export const settingsNavItem: NavItem = evidenceConsoleSettingsRoute;

export function isViewId(value: string | null): value is ViewId {
  return isDashboardViewId(value);
}
