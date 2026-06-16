(() => {
  const number = new Intl.NumberFormat();
  const tableDateFormat = new Intl.DateTimeFormat([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const tableTimeFormat = new Intl.DateTimeFormat([], {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  });
  const detailDateTimeFormat = new Intl.DateTimeFormat([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  });

  const money = (value, missingLabel = 'No price') => {
    if (value === null || value === undefined) return missingLabel;
    const amount = Number(value) || 0;
    if (amount > 0 && amount < 0.01) return `$${amount.toFixed(4)}`;
    return `$${amount.toFixed(2)}`;
  };

  const credits = (value, missingLabel = 'No rate') => {
    if (value === null || value === undefined) return missingLabel;
    const amount = Number(value) || 0;
    if (amount > 0 && amount < 1) return amount.toFixed(2);
    if (amount < 100) return amount.toFixed(1);
    return number.format(Math.round(amount));
  };

  const compactNumber = (value, threshold = 1_000_000_000) => {
    const amount = Number(value) || 0;
    if (Math.abs(amount) < threshold) return number.format(Math.round(amount));
    const scaled = amount / threshold;
    const maximumFractionDigits = Math.abs(scaled) >= 10 ? 0 : 1;
    const compacted = new Intl.NumberFormat([], {
      maximumFractionDigits,
      minimumFractionDigits: 0,
    }).format(scaled);
    return `${compacted}B`;
  };

  const pct = value => `${((Number(value) || 0) * 100).toFixed(1)}%`;
  const short = (value, fallback = 'Unknown') => value || fallback;
  const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
  const truncate = (value, size = 54) => {
    const text = short(value, '');
    return text.length > size ? `${text.slice(0, size - 1)}...` : text;
  };

  function parsedTimestamp(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatTimestamp(value, fallback = 'Unknown') {
    const date = parsedTimestamp(value);
    return date ? detailDateTimeFormat.format(date) : short(value, fallback);
  }

  function formatTimestampTitle(value) {
    const formatted = formatTimestamp(value, '');
    return [formatted, value].filter(Boolean).join(' - ');
  }

  function renderTimeCell(value) {
    const date = parsedTimestamp(value);
    if (!date) return escapeHtml(truncate(value, 20));
    return `
      <span class="time-cell" title="${escapeHtml(formatTimestampTitle(value))}">
        <span class="time-date">${escapeHtml(tableDateFormat.format(date))}</span>
        <span class="time-clock">${escapeHtml(tableTimeFormat.format(date))}</span>
      </span>
    `;
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

  function textValue(value) {
    return short(value, '').toLowerCase();
  }

  function compareValues(left, right) {
    if (typeof left === 'number' || typeof right === 'number') {
      return (Number(left) || 0) - (Number(right) || 0);
    }
    return String(left || '').localeCompare(String(right || ''));
  }

  function sortLabel(key) {
    return {
      attention: 'Needs attention',
      cache: 'Cache',
      context: 'Context use',
      cost: 'Cost',
      effort: 'Effort',
      model: 'Model',
      cached: 'Cached',
      uncached: 'Uncached',
      output: 'Output',
      reasoning: 'Reasoning output',
      thread: 'Thread',
      time: 'Time',
      total: 'Tokens',
      usage: 'Codex credits',
    }[key] || 'Sort';
  }

  window.CodexUsageDashboardFormat = Object.freeze({
    number,
    money,
    credits,
    compactNumber,
    pct,
    short,
    escapeHtml,
    truncate,
    parsedTimestamp,
    formatTimestamp,
    formatTimestampTitle,
    renderTimeCell,
    defaultSortDirection,
    textValue,
    compareValues,
    sortLabel,
  });
})();
