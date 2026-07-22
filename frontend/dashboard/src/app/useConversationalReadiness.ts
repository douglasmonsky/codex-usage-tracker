import { useEffect, useRef, useState } from 'react';
import { loadHomeStatus } from '../api/readiness';
import type {
  ConversationalReadiness,
  DashboardBootPayload,
  HomeSummaryPayload,
} from '../api/types';

export function useConversationalReadiness(
  initialPayload: DashboardBootPayload | null,
  dashboardPayload: DashboardBootPayload | null,
): {
  canUseLiveApi: boolean;
  conversationalAnalysis: ConversationalReadiness | undefined;
  homeSummary: HomeSummaryPayload | undefined;
} {
  const canUseLiveApi = Boolean(dashboardPayload?.api_token);
  const lastRequestedPayload = useRef<DashboardBootPayload | null>(null);
  const [readiness, setReadiness] = useState(initialPayload?.conversational_analysis);
  const [homeSummary, setHomeSummary] = useState(initialPayload?.home_summary);
  useEffect(() => {
    const readinessDeferred = initialPayload?.readiness_deferred === true && !readiness;
    const homeDeferred = initialPayload?.home_summary_deferred === true && !homeSummary;
    const dashboardSnapshotChanged = dashboardPayload !== initialPayload;
    if (
      (!readinessDeferred && !homeDeferred && !dashboardSnapshotChanged)
      || !canUseLiveApi
      || lastRequestedPayload.current === dashboardPayload
    ) return;
    lastRequestedPayload.current = dashboardPayload;
    const controller = new AbortController();
    void loadHomeStatus({
      apiToken: String(dashboardPayload?.api_token ?? ''),
      contextApiEnabled: Boolean(dashboardPayload?.context_api_enabled),
      fileMode: false,
    }, controller.signal).then(status => {
      setReadiness(status.conversational_analysis);
      setHomeSummary(status.home_summary);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [
    canUseLiveApi,
    dashboardPayload,
    homeSummary,
    initialPayload?.home_summary_deferred,
    initialPayload?.readiness_deferred,
    readiness,
  ]);
  return { canUseLiveApi, conversationalAnalysis: readiness, homeSummary };
}
