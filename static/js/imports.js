document.addEventListener('DOMContentLoaded', () => {
  const A = window.Admin;
  const preview = document.getElementById('import-preview-modal');
  const upload = document.getElementById('import-upload-modal');
  let controller;
  let generation = 0;
  const tableContainer = document.querySelector('[data-import-status-url]');
  let statusTimer;
  let statusRequest = false;
  let refreshQueued = false;

  async function refreshStatus() {
    if (!tableContainer) return;
    if (statusRequest) { refreshQueued = true; return; }
    clearTimeout(statusTimer);
    statusRequest = true;
    let pending = true;
    try {
      const response = await fetch(tableContainer.dataset.importStatusUrl, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error('Не удалось обновить статус');
      const result = await response.json();
      const tbody = tableContainer.querySelector('tbody');
      if (tbody.innerHTML !== result.html) tbody.innerHTML = result.html;
      const count = document.querySelector('[title="Количество импортов"]');
      if (count) count.textContent = result.count;
      pending = result.pending;
    } catch (_) {
      // Retry temporary connection failures without interrupting the import.
    } finally {
      statusRequest = false;
      if (pending || refreshQueued) statusTimer = setTimeout(refreshStatus, refreshQueued ? 0 : 1000);
      refreshQueued = false;
    }
  }
  if (tableContainer?.querySelector('[data-import-status="new"], [data-import-status="processing"]')) refreshStatus();
  const autoOpen = document.querySelector('[data-auto-open]');
  if (autoOpen) {
    if (autoOpen.open) autoOpen.close();
    A.modal.show(autoOpen);
  }
  if (!preview) return;

  function message(dialog, text) {
    let alert = dialog.querySelector('[data-import-message]');
    if (!alert) {
      alert = document.createElement('div');
      alert.className = 'alert alert-danger';
      alert.dataset.importMessage = '';
      alert.setAttribute('role', 'alert');
      (dialog.querySelector('.modal-body') || dialog).prepend(alert);
    }
    alert.textContent = text;
  }

  function render(html, wholePage = false) {
    const page = new DOMParser().parseFromString(html, 'text/html');
    const content = wholePage ? page.querySelector('#import-preview-modal') : page.body;
    if (!content || !content.querySelector('#import-preview-title')) throw new Error('Не удалось загрузить проверку импорта.');
    preview.replaceChildren(...Array.from(content.childNodes, node => document.importNode(node, true)));
  }

  document.addEventListener('click', async event => {
    const link = event.target.closest('a[data-import-preview]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    controller?.abort();
    controller = new AbortController();
    const version = ++generation;
    preview.querySelector('.modal-body')?.replaceChildren();
    A.modal.show(preview);
    preview.setAttribute('aria-busy', 'true');
    const loading = document.createElement('p');
    loading.textContent = 'Загрузка проверки…';
    loading.setAttribute('role', 'status');
    (preview.querySelector('.modal-body') || preview).append(loading);
    try {
      const response = await fetch(link.href, {
        credentials: 'same-origin', headers: { 'X-Import-Modal': '1' }, signal: controller.signal,
      });
      if (!response.ok || response.redirected) throw new Error('Не удалось открыть проверку. Обновите страницу и проверьте доступ.');
      const html = await response.text();
      if (version === generation && preview.open) render(html);
    } catch (error) {
      if (error.name !== 'AbortError' && version === generation) message(preview, error.message);
    } finally {
      if (version === generation) preview.removeAttribute('aria-busy');
    }
  });

  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const isUpload = upload?.contains(form);
    if (!isUpload && !form.matches('[data-import-confirm]')) return;
    event.preventDefault();
    const dialog = isUpload ? upload : preview;
    if (dialog.dataset.busy === 'true') return;
    const data = new FormData(form);
    if (event.submitter?.name) data.append(event.submitter.name, event.submitter.value);
    const buttons = Array.from(dialog.querySelectorAll('button'));
    const disabled = buttons.map(button => button.disabled);
    buttons.forEach(button => { button.disabled = true; });
    dialog.dataset.busy = 'true';
    dialog.setAttribute('aria-busy', 'true');
    dialog.querySelector('[data-import-message]')?.remove();
    try {
      const response = await fetch(new URL(form.getAttribute('action') || location.href, location.href), {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: isUpload ? { 'X-Import-Async': '1' } : { 'X-Import-Modal': '1' },
      });
      if (!response.ok) throw new Error('Не удалось обработать импорт. Проверьте доступ и соединение.');
      if (isUpload) {
        if ((response.headers.get('Content-Type') || '').includes('application/json')) {
          await response.json();
          dialog.dataset.busy = 'false';
          A.modal.close(upload);
          form.reset();
          await refreshStatus();
          return;
        }
        const html = await response.text();
        const page = new DOMParser().parseFromString(html, 'text/html');
        if (page.querySelector('#import-preview-modal [data-import-confirm]')) {
          render(html, true);
          const history = page.querySelector('[aria-label="Список импортов"]');
          const current = document.querySelector('[aria-label="Список импортов"]');
          if (history && current) current.replaceWith(document.importNode(history, true));
          dialog.dataset.busy = 'false';
          A.modal.close(upload);
          A.modal.show(preview);
        } else if (response.redirected) {
          location.assign(response.url);
        } else {
          const fields = page.querySelector('#import-upload-modal .modal-body');
          if (!fields) throw new Error('Не удалось загрузить сообщения проверки файла.');
          upload.querySelector('.modal-body').replaceChildren(...Array.from(fields.childNodes, node => document.importNode(node, true)));
        }
      } else if (response.redirected) {
        location.assign(response.url);
      } else {
        render(await response.text());
      }
    } catch (error) {
      message(dialog, error.message);
    } finally {
      dialog.dataset.busy = 'false';
      dialog.removeAttribute('aria-busy');
      buttons.forEach((button, index) => { button.disabled = disabled[index]; });
    }
  });

  preview.addEventListener('close', () => {
    if (preview.open) return;
    ++generation;
    controller?.abort();
    preview.removeAttribute('aria-busy');
  });
});
