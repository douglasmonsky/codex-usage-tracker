(function () {
  const aggregateCacheNamespace = 'codexUsageDashboardPayload:v1';

  function aggregatePayloadCacheKey(payload) {
    const key = payload && payload.payload_cache_key ? String(payload.payload_cache_key) : '';
    return key ? `${aggregateCacheNamespace}:${key}` : '';
  }

  function cacheableAggregatePayload(payload) {
    if (!payload || !Array.isArray(payload.rows) || payload.investigator_boot || payload.shell_boot) return null;
    const cached = { ...payload };
    delete cached.api_token;
    cached.context_api_enabled = false;
    cached.investigator_boot = false;
    cached.shell_boot = false;
    return cached;
  }

  function readAggregatePayloadCache(payload) {
    const key = aggregatePayloadCacheKey(payload);
    if (!key) return null;
    try {
      const parsed = JSON.parse(window.sessionStorage?.getItem(key) || 'null');
      if (!parsed || parsed.payload_cache_key !== payload.payload_cache_key || !Array.isArray(parsed.rows)) return null;
      return parsed;
    } catch (_error) {
      return null;
    }
  }

  function writeAggregatePayloadCache(payload) {
    const key = aggregatePayloadCacheKey(payload);
    const cached = cacheableAggregatePayload(payload);
    if (!key || !cached) return false;
    try {
      cached.cached_at = new Date().toISOString();
      window.sessionStorage?.setItem(key, JSON.stringify(cached));
      return true;
    } catch (_error) {
      return false;
    }
  }

  function resolveInitialPayload(initialPayload) {
    const cachedInitialPayload = initialPayload.investigator_boot || initialPayload.shell_boot
      ? readAggregatePayloadCache(initialPayload)
      : null;
    const activeInitialPayload = cachedInitialPayload
      ? {
          ...cachedInitialPayload,
          api_token: initialPayload.api_token || '',
          context_api_enabled: Boolean(initialPayload.context_api_enabled),
          investigator_boot: Boolean(initialPayload.investigator_boot),
          shell_boot: Boolean(initialPayload.shell_boot),
        }
      : initialPayload;
    return {
      activeInitialPayload,
      restoredAggregatePayloadFromCache: Boolean(cachedInitialPayload),
    };
  }

  window.CodexUsageDashboardPayloadCache = {
    readAggregatePayloadCache,
    writeAggregatePayloadCache,
    resolveInitialPayload,
  };
})();
