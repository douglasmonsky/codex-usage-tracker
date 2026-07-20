import {
  Activity,
  Boxes,
  FileText,
  type LucideIcon,
} from 'lucide-react';
import { isDashboardViewId, type DashboardViewId } from '../routes/dashboardSearch';
import {
  navigationForPhase,
  type RouteLifecycle,
  type RouteMaturity,
  type RoutePlacement,
} from './routeCatalog';

export type ViewId = DashboardViewId;

export type NavItem = {
  id: ViewId;
  label: string;
  description: string;
  icon: LucideIcon;
};

export const navItems: NavItem[] = navigationForPhase('foundation').map(({ id, label, description, icon }) => ({
  id, label, description, icon,
}));

type SecondaryNavItem = {
  label: string;
  icon: LucideIcon;
  target: ViewId;
  maturity: RouteMaturity;
  placement: RoutePlacement;
  lifecycle: RouteLifecycle;
};

export const secondaryNavItems: SecondaryNavItem[] = [
  { label: 'Files', icon: FileText, target: 'settings', maturity: 'stable', placement: 'hidden', lifecycle: 'deprecated' },
  { label: 'Commands', icon: Activity, target: 'investigator', maturity: 'stable', placement: 'hidden', lifecycle: 'deprecated' },
  { label: 'Models', icon: Boxes, target: 'calls', maturity: 'stable', placement: 'hidden', lifecycle: 'deprecated' },
];

export function isViewId(value: string | null): value is ViewId {
  return isDashboardViewId(value);
}
