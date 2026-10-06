document.addEventListener('DOMContentLoaded', () => {
  const container = document.querySelector('[data-live-balances]');
  const status = document.querySelector('[data-balance-status]');
  if (!container) return;
  let busy = false;
  let lastContent = container.innerHTML.trim();
  async function refresh() {
    if (busy || document.hidden || container.contains(document.activeElement)) return;
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
        const positions = [...container.querySelectorAll('.table-container')].map(el => [el.scrollLeft, el.scrollTop]);
        container.innerHTML = content;
        container.querySelectorAll('.table-container').forEach((el, index) => {
          const position = positions[index];
          if (position) { el.scrollLeft = position[0]; el.scrollTop = position[1]; }
        });
        lastContent = content;
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
