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
  homeStatusLoading: boolean;
  homeStatusError: string | null;
} {
  const canUseLiveApi = Boolean(dashboardPayload?.api_token);
  const lastCompletedPayload = useRef<DashboardBootPayload | null>(null);
  const [readiness, setReadiness] = useState(initialPayload?.conversational_analysis);
  const [homeSummary, setHomeSummary] = useState(initialPayload?.home_summary);
  const [homeStatusLoading, setHomeStatusLoading] = useState(false);
  const [homeStatusError, setHomeStatusError] = useState<string | null>(null);
  useEffect(() => {
    const readinessDeferred = initialPayload?.readiness_deferred === true && !readiness;
    const homeDeferred = initialPayload?.home_summary_deferred === true && !homeSummary;
    const dashboardSnapshotChanged = dashboardPayload !== initialPayload;
    if (
      (!readinessDeferred && !homeDeferred && !dashboardSnapshotChanged)
      || !canUseLiveApi
      || lastCompletedPayload.current === dashboardPayload
    ) return;
    const controller = new AbortController();
    setHomeStatusLoading(true);
    setHomeStatusError(null);
    void loadHomeStatus({
      apiToken: String(dashboardPayload?.api_token ?? ''),
      contextApiEnabled: Boolean(dashboardPayload?.context_api_enabled),
      fileMode: false,
    }, controller.signal).then(status => {
      if (controller.signal.aborted) return;
      lastCompletedPayload.current = dashboardPayload;
      setReadiness(status.conversational_analysis);
      setHomeSummary(status.home_summary);
    }).catch(error => {
      if (!controller.signal.aborted) {
        lastCompletedPayload.current = dashboardPayload;
        setHomeStatusError(error instanceof Error ? error.message : 'Home status is unavailable.');
      }
    }).finally(() => {
      if (!controller.signal.aborted) setHomeStatusLoading(false);
    });
    return () => controller.abort();
  }, [
    canUseLiveApi,
    dashboardPayload,
    homeSummary,
    initialPayload?.home_summary_deferred,
    initialPayload?.readiness_deferred,
    readiness,
  ]);
  return {
    canUseLiveApi,
    conversationalAnalysis: readiness,
    homeSummary,
    homeStatusLoading,
    homeStatusError,
  };
}
