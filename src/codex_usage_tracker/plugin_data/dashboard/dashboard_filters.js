(function () {
  function padDatePart(value) {
    return String(value).padStart(2, '0');
  }

  function localDateKey(date) {
    return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;
  }

  function localDay(value = new Date()) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  function addDays(date, days) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
  }

  function parseDateInput(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
    const [year, month, day] = value.split('-').map(Number);
    const date = new Date(year, month - 1, day);
    return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
  }

  function cleanDateInput(value) {
    const date = parseDateInput(value);
    return date ? localDateKey(date) : '';
  }

  function weekStart(date) {
    const day = date.getDay();
    const offset = day === 0 ? -6 : 1 - day;
    return addDays(date, offset);
  }

  function presetDateRange(preset) {
    const today = localDay();
    if (preset === 'today') {
      return { start: today, endExclusive: addDays(today, 1) };
    }
    if (preset === 'this-week') {
      const start = weekStart(today);
      return { start, endExclusive: addDays(start, 7) };
    }
    if (preset === 'last-7-days') {
      return { start: addDays(today, -6), endExclusive: addDays(today, 1) };
    }
    if (preset === 'this-month') {
      return {
        start: new Date(today.getFullYear(), today.getMonth(), 1),
        endExclusive: new Date(today.getFullYear(), today.getMonth() + 1, 1),
      };
    }
    return { start: null, endExclusive: null };
  }

  function formatDateRangeLabel(prefix, start, end, translate) {
    const startLabel = start ? localDateKey(start) : '';
    const endLabel = end ? localDateKey(end) : '';
    if (startLabel && endLabel && startLabel === endLabel) return translate('date.range_exact', { prefix, date: startLabel });
    if (startLabel && endLabel) return translate('date.range_between', { prefix, start: startLabel, end: endLabel });
    if (startLabel) return translate('date.range_from', { prefix, start: startLabel });
    if (endLabel) return translate('date.range_through', { prefix, end: endLabel });
    return prefix;
  }

  function rowMatchesDateRange(row, range) {
    if (range.invalid) return false;
    if (!range.active) return true;
    const timestamp = row.event_timestamp ? new Date(row.event_timestamp) : null;
    if (!timestamp || Number.isNaN(timestamp.getTime())) return false;
    if (range.start && timestamp < range.start) return false;
    if (range.endExclusive && timestamp >= range.endExclusive) return false;
    return true;
  }

  window.CodexUsageDashboardFilters = {
    addDays,
    cleanDateInput,
    formatDateRangeLabel,
    localDateKey,
    parseDateInput,
    presetDateRange,
    rowMatchesDateRange,
  };
})();
