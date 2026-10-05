/* Existing Django forms retain their permissions, CSRF and validation. */
(function (A) {
  'use strict';
  document.addEventListener('DOMContentLoaded', () => {
    const dialog = document.getElementById('record-form-modal');
    if (!dialog) return;
    const body = dialog.querySelector('[data-form-body]');
    const title = dialog.querySelector('[data-form-title]');
    const directPage = dialog.hasAttribute('data-form-auto-open');
    let sourceURL = location.href;
    let controller = null;
    let generation = 0;

    function message(text) {
      let alert = body.querySelector('[data-form-message]');
      if (!alert) {
        alert = document.createElement('div');
        alert.className = 'alert alert-danger mb-3';
        alert.dataset.formMessage = '';
        alert.setAttribute('role', 'alert');
        body.prepend(alert);
      }
      alert.textContent = text;
    }

    function prepare() {
      const heading = body.querySelector('.page-header h1, h1');
      if (heading) title.textContent = heading.textContent.trim();
      body.querySelectorAll('.page-header').forEach(header => {
        header.querySelectorAll('p').forEach(note => header.before(note));
        header.remove();
      });
      body.querySelectorAll('script').forEach(script => script.remove());
      body.querySelectorAll('form').forEach(form => {
        form.action = new URL(form.getAttribute('action') || sourceURL, sourceURL).href;
      });
      body.querySelectorAll('a').forEach(link => {
        if (/^(Отмена|Назад|К договорам)$/.test(link.textContent.trim())) {
          link.dataset.formCancel = '';
        }
      });
      if (body.querySelector('[name="mode"]')) A.initDistribution(body);
      if (body.querySelector('#writeoff-form')) A.initWriteoffs(body);
      const field = body.querySelector('[aria-invalid="true"]:not([disabled])')
        || body.querySelector('[autofocus], input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])');
      if (field) field.focus();
    }

    function render(html, url) {
      const page = new DOMParser().parseFromString(html, 'text/html');
      const content = page.querySelector('#record-form-modal [data-form-body]');
      if (!content || !content.querySelector('form[method="post"]')) {
        throw new Error('Не удалось загрузить форму. Обновите страницу и попробуйте снова.');
      }
      sourceURL = url;
      body.replaceChildren(...Array.from(content.childNodes, node => document.importNode(node, true)));
      prepare();
    }

    async function openForm(url, label) {
      if (dialog.dataset.busy === 'true') return;
      if (controller) controller.abort();
      controller = new AbortController();
      const version = ++generation;
      sourceURL = url;
      title.textContent = label || 'Добавление и редактирование';
      const loading = document.createElement('p');
      loading.setAttribute('role', 'status');
      loading.textContent = 'Загрузка формы…';
      body.replaceChildren(loading);
      A.modal.show(dialog);
      try {
        const response = await fetch(url, { credentials: 'same-origin', signal: controller.signal });
        if (version !== generation) return;
        if (response.redirected) { location.assign(response.url); return; }
        if (!response.ok) throw new Error(response.status === 403 ? 'Недостаточно прав для этой операции.' : 'Не удалось загрузить форму. Попробуйте снова.');
        const html = await response.text();
        if (version === generation && dialog.open) render(html, url);
      } catch (error) {
        if (error.name !== 'AbortError' && version === generation) message(error.message);
      }
    }

    document.addEventListener('click', event => {
      const cancel = event.target.closest('[data-form-cancel]');
      if (cancel && dialog.contains(cancel)) { event.preventDefault(); A.modal.close(dialog); return; }
      const link = event.target.closest('a[data-form-modal]');
      if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      openForm(link.href, link.textContent.trim());
    });

    dialog.addEventListener('submit', async event => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== 'post') return;
      event.preventDefault();
      if (dialog.dataset.busy === 'true') return;
      const data = new FormData(form);
      if (event.submitter && event.submitter.name) data.append(event.submitter.name, event.submitter.value);
      const controls = Array.from(dialog.querySelectorAll('button[type="submit"], button[data-modal-close]'));
      const states = controls.map(button => button.disabled);
      controls.forEach(button => { button.disabled = true; });
      dialog.dataset.busy = 'true';
      dialog.setAttribute('aria-busy', 'true');
      body.querySelector('[data-form-message]')?.remove();
      try {
        const response = await fetch(form.action, {
          method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Form-Modal': '1' },
        });
        if (response.redirected) { location.assign(response.url); return; }
        if (!response.ok) throw new Error(response.status === 403 ? 'Недостаточно прав или срок формы истёк. Обновите страницу.' : 'Не удалось сохранить. Проверьте соединение перед повторной отправкой.');
        if ((response.headers.get('Content-Type') || '').includes('application/json')) {
          const result = await response.json();
          const target = new URL(result.redirect_url, location.origin);
          if (!result.redirect_url || target.origin !== location.origin) throw new Error('Не удалось завершить сохранение. Обновите страницу.');
          location.assign(target.href);
        } else {
          render(await response.text(), form.action);
        }
      } catch (error) {
        message(error.message);
      } finally {
        dialog.dataset.busy = 'false';
        dialog.removeAttribute('aria-busy');
        controls.forEach((button, index) => { button.disabled = states[index]; });
      }
    });

    dialog.addEventListener('close', () => {
      if (dialog.open) return;
      ++generation;
      if (controller) controller.abort();
      if (directPage) location.replace(dialog.dataset.returnUrl);
      else body.replaceChildren();
    });

    if (directPage) { A.modal.show(dialog); prepare(); }
  });
})(window.Admin);
