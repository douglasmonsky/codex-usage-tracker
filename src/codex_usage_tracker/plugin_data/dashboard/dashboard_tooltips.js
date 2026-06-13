(function () {
  function create(helpers = {}) {
    const escapeHtml = helpers.escapeHtml || (value => String(value ?? ''));
    const clamp = helpers.clamp || ((value, min, max) => Math.min(Math.max(value, min), max));
    let fastTooltipEl = null;
    let fastTooltipTarget = null;
    let fastTooltipTimer = null;

    function tooltipAttributes(text) {
      const safe = escapeHtml(text || '');
      return `title="${safe}" data-fast-tooltip data-tooltip="${safe}"`;
    }

    function setFastTooltip(element, text) {
      if (!element) return;
      const value = text || '';
      if (!value) {
        element.removeAttribute('title');
        element.removeAttribute('data-tooltip');
        element.removeAttribute('data-fast-tooltip');
        return;
      }
      element.setAttribute('title', value);
      element.dataset.tooltip = value;
      element.dataset.fastTooltip = '';
    }

    function ensureFastTooltipElement() {
      if (fastTooltipEl) return fastTooltipEl;
      fastTooltipEl = document.createElement('div');
      fastTooltipEl.className = 'fast-tooltip';
      fastTooltipEl.hidden = true;
      document.body.appendChild(fastTooltipEl);
      return fastTooltipEl;
    }

    function restoreNativeTooltip(target = fastTooltipTarget) {
      if (!target || !target.dataset) return;
      if (target.dataset.nativeTitle !== undefined) {
        target.setAttribute('title', target.dataset.nativeTitle);
        delete target.dataset.nativeTitle;
      }
    }

    function hideFastTooltip() {
      if (fastTooltipTimer) window.clearTimeout(fastTooltipTimer);
      fastTooltipTimer = null;
      restoreNativeTooltip();
      if (fastTooltipEl) fastTooltipEl.hidden = true;
      fastTooltipTarget = null;
    }

    function positionFastTooltip(target) {
      if (!fastTooltipEl || fastTooltipEl.hidden) return;
      const rect = target.getBoundingClientRect();
      const gap = 8;
      const width = fastTooltipEl.offsetWidth;
      const height = fastTooltipEl.offsetHeight;
      const left = clamp(rect.left + rect.width / 2 - width / 2, 8, window.innerWidth - width - 8);
      const above = rect.top - height - gap;
      const top = above >= 8 ? above : Math.min(rect.bottom + gap, window.innerHeight - height - 8);
      fastTooltipEl.style.left = `${left}px`;
      fastTooltipEl.style.top = `${Math.max(8, top)}px`;
    }

    function showFastTooltip(target) {
      const text = target.dataset.tooltip || target.getAttribute('title') || '';
      if (!text.trim()) {
        hideFastTooltip();
        return;
      }
      if (target.hasAttribute('title') && target.dataset.nativeTitle === undefined) {
        target.dataset.nativeTitle = target.getAttribute('title') || '';
        target.removeAttribute('title');
      }
      fastTooltipTarget = target;
      const tooltip = ensureFastTooltipElement();
      tooltip.textContent = text;
      tooltip.hidden = false;
      positionFastTooltip(target);
    }

    function scheduleFastTooltip(target) {
      if (!target) return;
      if (fastTooltipTimer) window.clearTimeout(fastTooltipTimer);
      restoreNativeTooltip();
      if (fastTooltipEl) fastTooltipEl.hidden = true;
      fastTooltipTarget = target;
      fastTooltipTimer = window.setTimeout(() => {
        fastTooltipTimer = null;
        showFastTooltip(target);
      }, 70);
    }

    function closestFastTooltipTarget(eventTarget) {
      return eventTarget && eventTarget.closest ? eventTarget.closest('[data-fast-tooltip]') : null;
    }

    return {
      tooltipAttributes,
      setFastTooltip,
      hideFastTooltip,
      scheduleFastTooltip,
      closestFastTooltipTarget,
    };
  }

  window.CodexUsageDashboardTooltips = { create };
})();
