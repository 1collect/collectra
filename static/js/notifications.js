/* Feedback stays in the page flow: no floating UI, timers or popovers. */
(function (A) {
  'use strict';
  const tones = { success: ['success', 'Готово'], error: ['danger', 'Ошибка'], warning: ['warning', 'Внимание'], info: ['info', 'Информация'] };
  let region;

  function syncHost() {
    if (!region) return;
    const dialog = Array.from(document.querySelectorAll('dialog[open]')).at(-1);
    const host = dialog?.querySelector('.modal-body') || dialog || document.getElementById('main-content') || document.body;
    if (region.parentElement !== host) host.prepend(region);
  }
  document.addEventListener('modal:shown', syncHost);
  document.addEventListener('close', event => {
    if (event.target instanceof HTMLDialogElement) syncHost();
  }, true);

  A.notify = function (type = 'info', title, message = '') {
    if (!region) {
      region = document.createElement('div');
      region.className = 'feedback-region';
      region.setAttribute('aria-label', 'Сообщения');
    }
    syncHost();
    const [tone, fallback] = tones[type] || tones.info;
    const notice = document.createElement('div');
    notice.className = `alert alert-${tone} feedback-message`;
    notice.setAttribute('role', type === 'error' ? 'alert' : 'status');
    notice.setAttribute('aria-atomic', 'true');
    const content = document.createElement('div');
    const heading = document.createElement('strong');
    const text = document.createElement('p');
    heading.textContent = title || fallback;
    text.textContent = message;
    content.append(heading, text);
    const remove = () => notice.remove();
    remove.update = (title, message) => {
      syncHost();
      heading.textContent = title;
      text.textContent = message;
    };
    notice.append(content);
    region.append(notice);
    return remove;
  };
  A.notify.syncHost = syncHost;
})(window.Admin);
