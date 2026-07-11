import {
  createBrowserHistory,
  createRootRoute,
  createRouter,
  lazyRouteComponent,
  type ErrorComponentProps,
  type RouterHistory,
} from '@tanstack/react-router';

import { validateDashboardSearch } from '../routes/dashboardSearch';

const LazyDashboardApp = lazyRouteComponent(() => import('../App'), 'RoutedApp');

type DashboardRouterOptions = {
  history?: RouterHistory;
  basepath?: string;
};

export function createDashboardRouter(options: DashboardRouterOptions = {}) {
  const rootRoute = createRootRoute({
    validateSearch: validateDashboardSearch,
    component: LazyDashboardApp,
    pendingComponent: DashboardRoutePending,
    errorComponent: DashboardRouteError,
  });

  return createRouter({
    routeTree: rootRoute,
    history: options.history ?? createBrowserHistory(),
    basepath: options.basepath ?? dashboardBasepath(),
    defaultPreload: 'intent',
    defaultPendingMs: 120,
    defaultPendingMinMs: 180,
    scrollRestoration: true,
    search: { strict: false },
  });
}

export const dashboardRouter = createDashboardRouter();

type DashboardRouter = typeof dashboardRouter;

declare module '@tanstack/react-router' {
  interface Register {
    router: DashboardRouter;
  }
}

function dashboardBasepath(): string {
  const configured = import.meta.env.BASE_URL.replace(/\/$/, '');
  return configured || '/';
}

function DashboardRoutePending() {
  return (
    <main aria-busy="true" aria-live="polite" className="route-state" role="status">
      <strong>Loading dashboard</strong>
      <span>Restoring the local usage workspace...</span>
    </main>
  );
}

function DashboardRouteError({ error, reset }: ErrorComponentProps) {
  return (
    <main className="route-state" role="alert">
      <strong>Dashboard route could not load</strong>
      <span>{error instanceof Error ? error.message : String(error)}</span>
      <button type="button" onClick={reset}>Retry</button>
    </main>
  );
}
