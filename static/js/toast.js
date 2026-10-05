/* Shared notifications with safe text and dismissal paused on hover or focus. */
(function (A) {
  'use strict';
  const tones = { success: ['success', 'Готово'], error: ['danger', 'Ошибка'], warning: ['warning', 'Внимание'], info: ['info', 'Информация'] };
  let container;
  const removers = new Map();
  function syncHost() {
    if (!container) return;
    const host = Array.from(document.querySelectorAll('dialog[open]')).at(-1) || document.body;
    if (container.parentElement !== host) {
      if (container.showPopover && container.matches(':popover-open')) container.hidePopover();
      host.append(container);
      if (container.children.length && container.showPopover) container.showPopover();
    }
  }
  document.addEventListener('modal:shown', syncHost);
  document.addEventListener('close', event => { if (event.target instanceof HTMLDialogElement) syncHost(); }, true);
  A.toast = function (type = 'info', title, message = '', duration = 3000) {
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      container.setAttribute('aria-label', 'Уведомления');
      if ('showPopover' in container) container.setAttribute('popover', 'manual');
      document.body.append(container);
    }
    syncHost();
    const [tone, fallback] = tones[type] || tones.info;
    const toast = document.createElement('div'); toast.className = 'toast';
    toast.dataset.toastType = type;
    toast.style.setProperty('--toast-tone', `var(--${tone})`);
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.setAttribute('aria-atomic', 'true');
    const content = document.createElement('div');
    const heading = document.createElement('strong'); heading.textContent = title || fallback;
    const text = document.createElement('p'); text.textContent = message;
    content.append(heading, text);
    const close = document.createElement('button'); close.type = 'button';
    close.className = 'btn btn-icon btn-sm btn-ghost';
    close.setAttribute('aria-label', 'Закрыть уведомление');
    close.innerHTML = '<svg aria-hidden="true" class="icon" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"></path></svg>';
    toast.append(content, close);
    let progress;
    if (duration > 0) {
      progress = document.createElement('span');
      progress.className = 'toast__progress';
      progress.setAttribute('aria-hidden', 'true');
      toast.append(progress);
    }
    while (container.children.length >= 4) removers.get(container.firstElementChild)();
    container.append(toast);
    // Native popovers render above dialogs without changing focus.
    if (container.showPopover) {
      if (container.matches(':popover-open')) container.hidePopover();
      container.showPopover();
    }
    const countdown = progress?.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }], {
      duration, easing: 'linear', fill: 'forwards',
    });
    countdown?.pause();
    const stop = () => countdown?.pause();
    const remove = () => {
      countdown?.cancel(); toast.remove(); removers.delete(toast);
      if (!container.children.length && container.showPopover && container.matches(':popover-open')) container.hidePopover();
    };
    const start = () => {
      stop();
      if (toast.isConnected && !toast.matches(':hover') && !toast.contains(document.activeElement)) countdown?.play();
    };
    if (countdown) countdown.onfinish = remove;
    removers.set(toast, remove);
    close.addEventListener('click', remove);
    toast.addEventListener('mouseenter', stop); toast.addEventListener('mouseleave', start);
    toast.addEventListener('focusin', stop); toast.addEventListener('focusout', () => setTimeout(start, 0)); start();
    return remove;
  };
  A.toast.syncHost = syncHost;
})(window.Admin);
