document.addEventListener('DOMContentLoaded', () => {
  const container = document.querySelector('[data-live-balances]');
  let status = document.querySelector('[data-balance-status]');
  if (!container) return;
  let busy = false;
  let lastContent = container.innerHTML.trim();
  async function refresh() {
    if (busy || document.hidden || container.contains(document.activeElement)
      || document.querySelector('dialog[open], .dropdown-menu:not([hidden])')) return;
    busy = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(location.href, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store', signal: controller.signal,
      });
      if (!response.ok || response.redirected) throw new Error('refresh failed');
      const content = (await response.text()).trim();
      if (content !== lastContent) {
        const scrollSelector = '.table-container, .contract-picker-list';
        const positions = [...container.querySelectorAll(scrollSelector)].map(el => [el.scrollLeft, el.scrollTop]);
        const contractSearch = container.querySelector('[data-contract-search]')?.value;
        const disclosures = [...container.querySelectorAll('details[open][id]')].map(el => el.id);
        const expanded = [...container.querySelectorAll('[data-operation-details]:not([hidden])')].map(el => el.dataset.operationDetails);
        container.innerHTML = content;
        disclosures.forEach(id => { const el = document.getElementById(id); if (el) el.open = true; });
        expanded.forEach(key => {
          const row = container.querySelector('[data-operation-details="' + key + '"]');
          const button = container.querySelector('[data-operation-toggle="' + key + '"]');
          if (row) row.hidden = false;
          if (button) { button.setAttribute('aria-expanded', 'true'); button.textContent = 'Свернуть'; }
        });
        const searchInput = container.querySelector('[data-contract-search]');
        if (searchInput && contractSearch !== undefined) searchInput.value = contractSearch;
        document.dispatchEvent(new Event('balances:updated'));
        container.querySelectorAll(scrollSelector).forEach((el, index) => {
          const position = positions[index];
          if (position) { el.scrollLeft = position[0]; el.scrollTop = position[1]; }
        });
        lastContent = content;
        status = document.querySelector('[data-balance-status]');
        const count = document.querySelector('[data-record-count]');
        const total = container.querySelector('[data-record-total]');
        if (count && total) count.textContent = total.dataset.recordTotal;
      }
      if (status) status.textContent = 'Обновлено: ' + new Date().toLocaleTimeString('ru-RU') + '. Автообновление включено.';
    } catch (_) {
      if (status) status.textContent = 'Не удалось обновить данные. Повторим автоматически.';
    } finally {
      clearTimeout(timeout);
      busy = false;
    }
  }
  setInterval(refresh, 15000);
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
});
