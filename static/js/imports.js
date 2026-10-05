document.addEventListener('DOMContentLoaded', () => {
  const A = window.Admin;
  const preview = document.getElementById('import-preview-modal');
  const upload = document.getElementById('import-upload-modal');
  const isReload = performance.getEntriesByType('navigation')[0]?.type === 'reload';
  if (isReload) {
    if (location.search) {
      location.replace(location.pathname);
      return;
    }
    [preview, upload].forEach(dialog => {
      if (dialog?.open) dialog.close();
    });
  }
  let controller;
  let generation = 0;
  const tableContainer = document.querySelector('[data-import-status-url]');
  document.querySelector('[data-import-page-size]')?.addEventListener('change', event => {
    event.target.form.requestSubmit();
  });
  let statusTimer;
  let statusRequest = false;
  let refreshQueued = false;
  let statusUnavailable = false;
  const knownStatuses = new Map(Array.from(tableContainer?.querySelectorAll('[data-import-id]') || [], row => [row.dataset.importId, row.dataset.importStatus]));
  document.addEventListener('click', async event => {
    const link = event.target.closest('[data-import-download]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (link.getAttribute('aria-busy') === 'true') return;
    const original = Array.from(link.childNodes, node => node.cloneNode(true));
    link.setAttribute('aria-busy', 'true');
    link.setAttribute('aria-disabled', 'true');
    link.textContent = 'Подготовка файла…';
    try {
      const response = await fetch(link.href, { credentials: 'same-origin' });
      if (!response.ok || response.redirected || !(response.headers.get('Content-Type') || '').includes('spreadsheetml')) {
        throw new Error('Не удалось скачать отчёт. Повторите попытку.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const download = document.createElement('a');
      const disposition = response.headers.get('Content-Disposition') || '';
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const plainName = disposition.match(/filename="([^"]+)"/i);
      let filename = link.dataset.downloadName || 'import-errors.xlsx';
      if (encodedName) {
        try { filename = decodeURIComponent(encodedName[1]); } catch (_) { /* Keep the fallback name. */ }
      } else if (plainName) filename = plainName[1];
      download.href = url;
      download.download = filename;
      document.body.append(download);
      download.click();
      download.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      A.toast('success', 'Отчёт готов', 'Файл с ошибками отправлен на скачивание.');
    } catch (error) {
      A.toast('error', 'Ошибка скачивания', error.message);
    } finally {
      link.removeAttribute('aria-busy');
      link.removeAttribute('aria-disabled');
      link.replaceChildren(...original);
    }
  });
  document.querySelectorAll('[data-import-notifications] [data-toast-type]').forEach(item => {
    A.toast(item.dataset.toastType, 'Импорт', item.textContent.trim());
  });
  document.querySelector('[data-import-notifications]')?.remove();

  async function refreshStatus() {
    if (!tableContainer) return;
    if (statusRequest) { refreshQueued = true; return; }
    clearTimeout(statusTimer);
    statusRequest = true;
    let pending = true;
    try {
      const statusURL = new URL(tableContainer.dataset.importStatusUrl, location.href);
      statusURL.search = location.search;
      const response = await fetch(statusURL, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error('Не удалось обновить статус');
      const result = await response.json();
      const tbody = tableContainer.querySelector('tbody');
      if (tbody.innerHTML !== result.html) tbody.innerHTML = result.html;
      tbody.querySelectorAll('[data-import-id]').forEach(row => {
        const previous = knownStatuses.get(row.dataset.importId);
        const status = row.dataset.importStatus;
        knownStatuses.set(row.dataset.importId, status);
        if (!row.hasAttribute('data-import-owned') || !['new', 'processing'].includes(previous)) return;
        if (status === 'failed') A.toast('error', 'Ошибка проверки', 'Откройте импорт для подробностей.');
      });
      statusUnavailable = false;
      const pagination = document.querySelector('[data-import-pagination]');
      if (pagination && pagination.innerHTML !== result.pagination_html) pagination.innerHTML = result.pagination_html;
      pending = result.pending;
    } catch (_) {
      if (!statusUnavailable) A.toast('warning', 'Нет связи', 'Повторяем запрос…');
      statusUnavailable = true;
      // Retry temporary connection failures without interrupting the import.
    } finally {
      statusRequest = false;
      if (pending || refreshQueued) statusTimer = setTimeout(refreshStatus, refreshQueued ? 0 : 1000);
      refreshQueued = false;
    }
  }
  if (tableContainer?.querySelector('[data-import-status="new"], [data-import-status="processing"]')) refreshStatus();
  const autoOpen = document.querySelector('[data-auto-open]');
  if (autoOpen && !isReload) {
    A.modal.show(autoOpen);
  }
  if (!preview) return;

  let confirmTimer;
  function startConfirmTimer() {
    clearInterval(confirmTimer);
    const button = preview.querySelector('[data-confirm-delay]');
    if (!button) return;
    const deadline = performance.now() + Number(button.dataset.confirmDelay) * 1000;
    button.dataset.confirmReady = 'false';
    button.disabled = true;
    function update() {
      const remaining = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
      button.textContent = remaining ? `Подтвердить импорт (${remaining} с)` : 'Подтвердить импорт';
      if (!remaining) {
        clearInterval(confirmTimer);
        button.dataset.confirmReady = 'true';
        button.disabled = preview.dataset.busy === 'true';
      }
    }
    update();
    confirmTimer = setInterval(update, 100);
  }
  startConfirmTimer();

  function message(dialog, text) {
    A.toast('error', 'Ошибка импорта', text);
  }

  function render(html, wholePage = false) {
    const page = new DOMParser().parseFromString(html, 'text/html');
    const content = wholePage ? page.querySelector('#import-preview-modal') : page.body;
    if (!content || !content.querySelector('#import-preview-title')) throw new Error('Не удалось загрузить проверку импорта.');
    preview.replaceChildren(...Array.from(content.childNodes, node => document.importNode(node, true)));
    A.toast.syncHost();
    startConfirmTimer();
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
      if (!response.ok || response.redirected) throw new Error('Не удалось открыть проверку.');
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
    if (!isUpload && event.submitter?.value !== 'cancel' && form.querySelector('[value="confirm"]')?.disabled) return;
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
      if (!response.ok) throw new Error('Не удалось выполнить запрос.');
      if (isUpload) {
        if ((response.headers.get('Content-Type') || '').includes('application/json')) {
          const result = await response.json();
          knownStatuses.set(String(result.import_id), 'new');
          dialog.dataset.busy = 'false';
          A.modal.close(upload);
          form.reset();
          const listingURL = new URL(location.href);
          listingURL.searchParams.delete('page');
          history.replaceState(null, '', listingURL);
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
          const error = fields.querySelector('.field-error, .errorlist');
          if (error) A.toast('error', 'Импорт не запущен', error.textContent.includes('уже запущен') ? 'Этот тип импорта уже занят.' : 'Проверьте поля формы.');
        }
      } else if ((response.headers.get('Content-Type') || '').includes('application/json')) {
        const result = await response.json();
        dialog.dataset.busy = 'false';
        A.modal.close(preview);
        A.toast(result.status === 'cancelled' ? 'info' : 'success', result.status === 'cancelled' ? 'Импорт отменён' : 'Импорт завершён', result.message);
        await refreshStatus();
      } else if (response.redirected) {
        location.assign(response.url);
      } else {
        render(await response.text());
        const error = preview.querySelector('.modal-body [role="alert"]');
        if (error) A.toast('error', 'Подтверждение недоступно', 'Проверьте ошибки в импорте.');
      }
    } catch (error) {
      message(dialog, error.message);
    } finally {
      dialog.dataset.busy = 'false';
      dialog.removeAttribute('aria-busy');
      buttons.forEach((button, index) => {
        button.disabled = button.hasAttribute('data-confirm-delay') ? button.dataset.confirmReady !== 'true' : disabled[index];
      });
    }
  });

  preview.addEventListener('close', () => {
    if (preview.open) return;
    clearInterval(confirmTimer);
    ++generation;
    controller?.abort();
    preview.removeAttribute('aria-busy');
  });
});
