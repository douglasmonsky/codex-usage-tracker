export type DashboardDataScope = {
  history_scope?: string;
  include_archived?: boolean;
  load_window?: 'day' | 'week' | 'rows' | 'all';
  default_load_window?: 'day' | 'week' | 'rows' | 'all';
  since?: string | null;
};
