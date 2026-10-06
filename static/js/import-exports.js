/* Durable report jobs survive modal close and navigation in the same tab. */
(function (A) {
  'use strict';
  const active = new Map();
  const requesting = new Set();
  const storageKey = `collectra.importExports.${document.body.dataset.userId}`;
  const sameOriginURL = value => {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin) throw new Error('Некорректная ссылка на отчёт.');
    return url.href;
  };
  function persist() {
    try { sessionStorage.setItem(storageKey, JSON.stringify([...active.values()].map(job => ({ id: job.id, url: job.url, sourceURL: job.sourceURL })))); } catch (_) { /* Progress stays on the server. */ }
  }
  function syncButtons() {
    const busy = new Set([...requesting, ...Array.from(active.values(), job => job.sourceURL)]);
    document.querySelectorAll('[data-import-download]').forEach(link => {
      if (busy.has(sameOriginURL(link.href))) {
        link.setAttribute('aria-busy', 'true');
        link.setAttribute('aria-disabled', 'true');
      } else {
        link.removeAttribute('aria-busy');
        link.removeAttribute('aria-disabled');
      }
    });
  }
  function finish(job) {
    job.notice();
    active.delete(job.id);
    persist();
    syncButtons();
  }
  function download(url) {
    const link = document.createElement('a');
    link.href = sameOriginURL(url);
    link.download = '';
    document.body.append(link);
    link.click();
    link.remove();
  }
  async function poll(job) {
    try {
      const response = await fetch(job.url, { credentials: 'same-origin', cache: 'no-store' });
      if ([401, 403, 404].includes(response.status) || response.redirected) throw new Error('Нет доступа к отчёту.');
      if (!response.ok) {
        job.notice.update('Подготовка отчёта', 'Нет связи. Повторяем запрос…');
        setTimeout(() => poll(job), 2000);
        return;
      }
      const result = await response.json();
      if (result.status === 'failed') throw new Error(result.error || 'Не удалось подготовить файл.');
      if (result.status === 'completed') {
        download(result.download_url);
        finish(job);
        return;
      }
      job.notice.update('Подготовка отчёта', `${result.stage} — ${result.progress}%`);
      setTimeout(() => poll(job), 1000);
    } catch (error) {
      if (error instanceof TypeError) {
        job.notice.update('Подготовка отчёта', 'Нет связи. Повторяем запрос…');
        setTimeout(() => poll(job), 2000);
        return;
      }
      finish(job);
      A.notify('error', 'Ошибка скачивания', error.message);
    }
  }
  function watch(id, url, sourceURL, notice) {
    if (active.has(id)) {
      const job = active.get(id);
      if (!job.sourceURL && sourceURL) job.sourceURL = sameOriginURL(sourceURL);
      notice?.();
      persist();
      syncButtons();
      return;
    }
    const job = { id, url: sameOriginURL(url), sourceURL: sourceURL ? sameOriginURL(sourceURL) : null,
      notice: notice || A.notify('info', 'Подготовка отчёта', 'Ожидание — 0%') };
    active.set(id, job);
    persist();
    syncButtons();
    poll(job);
  }
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const jobs = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
      if (Array.isArray(jobs)) jobs.forEach(job => watch(job.id, job.url, job.sourceURL));
    } catch (_) { /* Ignore invalid saved state. */ }
  });
  // Modal content can be replaced while its report is still being prepared.
  new MutationObserver(syncButtons).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('auxclick', event => {
    if (event.target.closest('[data-import-download][aria-disabled="true"]')) event.preventDefault();
  });
  document.addEventListener('click', async event => {
    const link = event.target.closest('[data-import-download]');
    if (!link) return;
    if (link.getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const sourceURL = sameOriginURL(link.href);
    requesting.add(sourceURL);
    syncButtons();
    try {
      const response = await fetch(link.href, { credentials: 'same-origin', cache: 'no-store', headers: { 'X-Import-Export': '1' } });
      if (response.redirected || !(response.headers.get('Content-Type') || '').includes('application/json')) throw new Error('Не удалось запустить подготовку отчёта.');
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Не удалось запустить подготовку отчёта.');
      if (result.status === 'completed') {
        download(result.download_url);
      } else {
        watch(result.job_id, result.status_url, sourceURL);
      }
    } catch (error) {
      A.notify('error', 'Ошибка скачивания', error.message);
    } finally {
      requesting.delete(sourceURL);
      syncButtons();
    }
  });
})(window.Admin);
