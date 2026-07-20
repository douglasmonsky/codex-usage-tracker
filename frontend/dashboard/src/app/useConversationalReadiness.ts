import { useEffect, useRef, useState } from 'react';
import { loadConversationalReadiness } from '../api/readiness';
import type { ConversationalReadiness, DashboardBootPayload } from '../api/types';

export function useConversationalReadiness(
  initialPayload: DashboardBootPayload | null,
  dashboardPayload: DashboardBootPayload | null,
): { canUseLiveApi: boolean; conversationalAnalysis: ConversationalReadiness | undefined } {
  const canUseLiveApi = Boolean(dashboardPayload?.api_token);
  const attempted = useRef(false);
  const [readiness, setReadiness] = useState(initialPayload?.conversational_analysis);
  useEffect(() => {
    if (readiness || initialPayload?.readiness_deferred !== true || !canUseLiveApi ||
      dashboardPayload?.shell_boot === true || attempted.current) return;
    attempted.current = true;
    const controller = new AbortController();
    void loadConversationalReadiness(controller.signal).then(setReadiness).catch(() => undefined);
    return () => controller.abort();
  }, [canUseLiveApi, dashboardPayload?.shell_boot, initialPayload?.readiness_deferred, readiness]);
  return { canUseLiveApi, conversationalAnalysis: readiness };
}
