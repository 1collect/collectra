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
      A.notify('error', 'Не удалось выполнить действие', text);
    }

    function notifyValidationErrors() {
      if (body.querySelector('.field-error, .errorlist, [aria-invalid="true"]')) {
        A.notify('error', 'Проверьте форму', 'Исправьте отмеченные поля и попробуйте ещё раз.');
      }
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
      if (A.initRefundSelect) A.initRefundSelect(body);
      if (A.initPaymentAllocation) A.initPaymentAllocation(body);
      if (dialog.open) focusForm();
    }

    function focusForm() {
      if (!body.querySelector('[data-no-auto-focus]')) {
        const field = body.querySelector('[aria-invalid="true"]:not([disabled]):not([hidden])')
          || body.querySelector('[autofocus]:not([hidden]), input:not([type="hidden"]):not([disabled]):not([hidden]), select:not([disabled]):not([hidden]), textarea:not([disabled]):not([hidden])');
        if (field) field.focus();
      }
    }

    function render(html, url) {
      const page = new DOMParser().parseFromString(html, 'text/html');
      const sourceDialog = page.querySelector('#record-form-modal');
      const content = sourceDialog?.querySelector('[data-form-body]');
      if (!content || !content.querySelector('form[method="post"]')) {
        throw new Error('Не удалось загрузить форму. Обновите страницу и попробуйте снова.');
      }
      dialog.classList.toggle('modal-form-compact', sourceDialog.classList.contains('modal-form-compact'));
      sourceURL = url;
      body.replaceChildren(...Array.from(content.childNodes, node => document.importNode(node, true)));
      prepare();
    }

    async function openForm(url, label, compact = false, trigger = null) {
      if (dialog.dataset.busy === 'true') return;
      if (controller) controller.abort();
      controller = new AbortController();
      const version = ++generation;
      sourceURL = url;
      dialog.classList.toggle('modal-form-compact', compact);
      title.textContent = label || 'Добавление и редактирование';
      body.replaceChildren();
      trigger?.setAttribute('aria-busy', 'true');
      try {
        const response = await fetch(url, { credentials: 'same-origin', signal: controller.signal });
        if (version !== generation) return;
        if (response.redirected) { location.assign(response.url); return; }
        if (!response.ok) throw new Error(response.status === 403 ? 'Недостаточно прав для этой операции.' : 'Не удалось загрузить форму. Попробуйте снова.');
        const html = await response.text();
        if (version === generation) {
          render(html, url);
          A.modal.show(dialog);
          focusForm();
        }
      } catch (error) {
        if (error.name !== 'AbortError' && version === generation) {
          A.modal.show(dialog);
          message(error.message);
        }
      } finally {
        trigger?.removeAttribute('aria-busy');
      }
    }

    document.addEventListener('click', event => {
      const cancel = event.target.closest('[data-form-cancel]');
      if (cancel && dialog.contains(cancel)) { event.preventDefault(); A.modal.close(dialog); return; }
      const link = event.target.closest('a[data-form-modal]');
      if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      if (link.getAttribute('aria-busy') === 'true') return;
      openForm(link.href, link.textContent.trim(), link.hasAttribute('data-form-modal-compact'), link);
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
          notifyValidationErrors();
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

    if (directPage) { prepare(); A.modal.show(dialog); focusForm(); notifyValidationErrors(); }
  });
})(window.Admin);
