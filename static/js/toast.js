/* Pauses dismissal while the message has keyboard focus or pointer hover. */
(function (A) {
  'use strict';
  const tones = { success: ['check-circle', 'Success'], error: ['x-circle', 'Error'], warning: ['warning', 'Warning'], info: ['info', 'Information'] };
  A.toast = function (type = 'info', title, message = '', duration = 5500) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const [icon, fallback] = tones[type] || tones.info;
    const toast = document.createElement('div'); toast.className = 'toast';
    toast.style.setProperty('--toast-tone', 'var(--' + (type === 'error' ? 'danger' : (tones[type] ? type : 'info')) + ')');
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.innerHTML = A.icon(icon) + '<div><strong>' + A.escape(title || fallback) + '</strong><p>' + A.escape(message) + '</p></div><button class="btn btn-icon btn-sm btn-ghost" aria-label="Dismiss notification">' + A.icon('x') + '</button>';
    while (container.children.length >= 4) container.firstElementChild.remove();
    container.append(toast);
    let timer;
    const stop = () => clearTimeout(timer);
    const start = () => { stop(); timer = setTimeout(() => toast.remove(), duration); };
    toast.querySelector('button').addEventListener('click', () => { stop(); toast.remove(); });
    toast.addEventListener('mouseenter', stop); toast.addEventListener('mouseleave', start);
    toast.addEventListener('focusin', stop); toast.addEventListener('focusout', start); start();
  };
})(window.Admin);
