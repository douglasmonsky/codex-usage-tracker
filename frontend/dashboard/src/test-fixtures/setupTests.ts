import '@testing-library/jest-dom/vitest';
import { beforeAll } from 'vitest';

import { preloadDashboardRouteViews } from '../routes/DashboardRouteView';

beforeAll(async () => {
  await preloadDashboardRouteViews();
});
