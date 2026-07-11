import {
  Activity,
  BarChart3,
  BookOpen,
  Boxes,
  Database,
  FileText,
  FlaskConical,
  Home,
  Settings,
  Table2,
  TimerReset,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { isDashboardViewId, type DashboardViewId } from '../routes/dashboardSearch';

export type ViewId = DashboardViewId;

export type NavItem = {
  id: ViewId;
  label: string;
  description: string;
  icon: LucideIcon;
};

export const navItems: NavItem[] = [
  { id: 'overview', label: 'Overview', description: 'High-level telemetry', icon: Home },
  { id: 'investigator', label: 'Investigate', description: 'Root-cause evidence', icon: FlaskConical },
  { id: 'calls', label: 'Calls', description: 'Model-call table', icon: Table2 },
  { id: 'threads', label: 'Threads', description: 'Thread efficiency', icon: Workflow },
  { id: 'usage-drain', label: 'Limits', description: 'Allowance intelligence', icon: TimerReset },
  { id: 'cache-context', label: 'Cache And Context', description: 'Cache and cold resumes', icon: Database },
  { id: 'diagnostics', label: 'Diagnostics Notebook', description: 'Technical report', icon: BookOpen },
  { id: 'reports', label: 'Reports', description: 'Generated analyses', icon: BarChart3 },
  { id: 'settings', label: 'Settings', description: 'Local configuration', icon: Settings },
];

export const secondaryNavItems: Array<{ label: string; icon: LucideIcon; target: ViewId }> = [
  { label: 'Files', icon: FileText, target: 'settings' },
  { label: 'Commands', icon: Activity, target: 'investigator' },
  { label: 'Models', icon: Boxes, target: 'calls' },
];

export function isViewId(value: string | null): value is ViewId {
  return isDashboardViewId(value);
}
