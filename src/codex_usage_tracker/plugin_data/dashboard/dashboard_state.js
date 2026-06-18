(function () {
  const ALLOWED_VIEWS = new Set(['insights', 'calls', 'threads', 'call']);
  const ALLOWED_DIRECTIONS = new Set(['asc', 'desc']);
  const STATE_KEYS = [
    'view',
    'q',
    'model',
    'effort',
    'confidence',
    'pricing',
    'date',
    'from',
    'to',
    'history',
    'sort',
    'direction',
    'preset',
    'page',
    'record',
    'thread',
    'expand',
    'threads',
  ];

  function clean(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function defaultSortDirection(key) {
    return {
      cache: 'asc',
      effort: 'asc',
      initiator: 'asc',
      model: 'asc',
      thread: 'asc',
    }[key] || 'desc';
  }

  function read(params = new URLSearchParams(window.location.search)) {
    const page = Number(params.get('page') || 1);
    return {
      view: ALLOWED_VIEWS.has(params.get('view')) ? params.get('view') : '',
      search: clean(params.get('q')),
      model: clean(params.get('model')),
      effort: clean(params.get('effort')),
      confidence: clean(params.get('confidence') || params.get('pricing')),
      datePreset: clean(params.get('date')),
      dateStart: clean(params.get('from')),
      dateEnd: clean(params.get('to')),
      historyScope: params.get('history') === 'all' ? 'all' : '',
      sort: clean(params.get('sort')),
      direction: ALLOWED_DIRECTIONS.has(params.get('direction')) ? params.get('direction') : '',
      preset: clean(params.get('preset')),
      page: Number.isFinite(page) && page > 0 ? Math.floor(page) : 1,
      record: clean(params.get('record')),
      thread: clean(params.get('thread')),
      expand: clean(params.get('expand')),
      expandedThreads: clean(params.get('threads')).split(',').filter(Boolean).slice(0, 30).map(decodePart),
    };
  }

  function serialize(state) {
    const params = new URLSearchParams(window.location.search);
    STATE_KEYS.forEach(key => params.delete(key));
    set(params, 'view', ALLOWED_VIEWS.has(state.view) && state.view !== 'calls' ? state.view : '');
    set(params, 'q', state.search);
    set(params, 'model', state.model);
    set(params, 'effort', state.effort);
    set(params, 'confidence', state.confidence);
    set(params, 'date', state.datePreset && state.datePreset !== 'all' ? state.datePreset : '');
    set(params, 'from', state.dateStart);
    set(params, 'to', state.dateEnd);
    set(params, 'history', state.historyScope === 'all' ? 'all' : '');
    set(params, 'sort', state.sort && state.sort !== 'time' ? state.sort : '');
    const direction = ALLOWED_DIRECTIONS.has(state.direction) ? state.direction : '';
    const sort = state.sort || 'time';
    set(params, 'direction', direction && !(sort === 'time' && direction === defaultSortDirection(sort)) ? direction : '');
    set(params, 'preset', state.preset);
    set(params, 'page', state.page && Number(state.page) > 1 ? String(Math.floor(Number(state.page))) : '');
    set(params, 'record', state.record);
    set(params, 'thread', state.thread);
    set(params, 'expand', state.expand);
    set(params, 'threads', Array.isArray(state.expandedThreads) ? state.expandedThreads.slice(0, 30).map(encodeURIComponent).join(',') : '');
    return params;
  }

  function set(params, key, value) {
    const text = clean(value);
    if (text) params.set(key, text);
  }

  function urlFor(state) {
    const params = serialize(state);
    const query = params.toString();
    const base = window.location.href.split('#')[0].split('?')[0];
    return `${base}${query ? `?${query}` : ''}${window.location.hash || ''}`;
  }

  function replace(state) {
    if (!window.history || !window.history.replaceState) return;
    const nextUrl = urlFor(state);
    if (nextUrl !== window.location.href) {
      window.history.replaceState(null, '', nextUrl);
    }
  }

  async function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', 'readonly');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand('copy');
    textarea.remove();
    return copied;
  }

  function downloadText(filename, text, type = 'text/plain;charset=utf-8') {
    const blob = new Blob([text], { type });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  function toCsv(rows, columns) {
    const header = columns.map(column => csvCell(column.label)).join(',');
    const body = rows.map(row => columns.map(column => csvCell(resolveValue(row, column.field))).join(','));
    return [header, ...body].join('\n') + '\n';
  }

  function resolveValue(row, field) {
    if (typeof field === 'function') return field(row);
    return row && Object.prototype.hasOwnProperty.call(row, field) ? row[field] : '';
  }

  function csvCell(value) {
    if (value === null || value === undefined) return '';
    const text = Array.isArray(value) ? value.join('; ') : String(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function decodePart(value) {
    try {
      return decodeURIComponent(value);
    } catch (error) {
      return value;
    }
  }

  window.CodexUsageDashboardState = {
    read,
    replace,
    urlFor,
    copyText,
    downloadText,
    toCsv,
  };
}());
