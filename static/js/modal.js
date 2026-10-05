/* Native <dialog> supplies focus containment, top-layer rendering and Escape. */
(function (A) {
  'use strict';
  let pendingConfirmation = null;
  let lockedScroll;
  function syncScrollLock() {
    if (!document.querySelector('dialog[open]')) { lockedScroll = null; return; }
    if (!lockedScroll) lockedScroll = { x: window.scrollX, y: window.scrollY };
    if (window.scrollX !== lockedScroll.x || window.scrollY !== lockedScroll.y) {
      window.scrollTo({ left: lockedScroll.x, top: lockedScroll.y, behavior: 'instant' });
    }
  }
  function blockBackgroundScroll(event) {
    if (!document.querySelector('dialog[open]')) return;
    const dialog = event.target instanceof Element ? event.target.closest('dialog[open]') : null;
    const point = event.touches?.[0] || event;
    const rect = dialog?.getBoundingClientRect();
    if (!rect || point.clientX < rect.left || point.clientX > rect.right || point.clientY < rect.top || point.clientY > rect.bottom) {
      event.preventDefault();
    }
  }
  document.addEventListener('wheel', blockBackgroundScroll, { passive: false });
  document.addEventListener('touchmove', blockBackgroundScroll, { passive: false });
  window.addEventListener('scroll', syncScrollLock);
  document.addEventListener('close', event => {
    if (event.target instanceof HTMLDialogElement) syncScrollLock();
  }, true);
  function settleConfirmation(dialog, value) {
    if (dialog.id !== 'confirm-dialog' || !pendingConfirmation) return;
    const resolve = pendingConfirmation;
    pendingConfirmation = null;
    resolve(value === 'confirm');
  }
  function show(id) {
    const dialog = typeof id === 'string' ? document.getElementById(id) : id;
    if (!dialog || dialog.open) return;
    A.dropdown.close();
    dialog.returnValue = 'cancel';
    if (!lockedScroll) lockedScroll = { x: window.scrollX, y: window.scrollY };
    dialog.showModal();
    syncScrollLock();
    A.emit('modal:shown', { dialog });
  }
  function close(dialog, value = 'cancel') {
    if (dialog && dialog.dataset.busy === 'true') return;
    if (dialog && dialog.open) {
      dialog.close(value);
      syncScrollLock();
      // Settle before the queued native close event. Reopening immediately is safe.
      settleConfirmation(dialog, value);
    }
  }
  A.modal = { show, close };
  A.confirm = function ({ title = 'Confirm action', message = 'Continue?', label = 'Confirm', danger = false } = {}) {
    const dialog = document.getElementById('confirm-dialog');
    if (dialog.open || pendingConfirmation) return Promise.resolve(false);
    dialog.querySelector('h2').textContent = title;
    dialog.querySelector('[data-confirm-message]').textContent = message;
    const action = dialog.querySelector('[data-confirm-yes]');
    action.textContent = label; action.className = 'btn ' + (danger ? 'btn-danger' : 'btn-primary');
    return new Promise(resolve => {
      pendingConfirmation = resolve;
      show(dialog);
    });
  };
  A.initModals = function () {
    document.addEventListener('click', event => {
      const opener = event.target.closest('[data-modal-open]');
      if (opener) { event.preventDefault(); show(opener.dataset.modalOpen); }
      if (event.target.closest('[data-modal-close]')) close(event.target.closest('dialog'));
      if (event.target.closest('[data-confirm-yes]')) close(event.target.closest('dialog'), 'confirm');
    });
    A.$$('dialog').forEach(dialog => {
      let pointerOutside = false;
      const outside = event => {
        const rect = dialog.getBoundingClientRect();
        return event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom);
      };
      dialog.addEventListener('pointerdown', event => { pointerOutside = outside(event); });
      dialog.addEventListener('click', event => { if (pointerOutside && outside(event)) close(dialog); pointerOutside = false; });
      dialog.addEventListener('cancel', event => {
        if (dialog.dataset.busy === 'true') { event.preventDefault(); return; }
        if (dialog.id === 'confirm-dialog') { event.preventDefault(); close(dialog); }
      });
      dialog.addEventListener('close', () => {
        A.dropdown.close();
        if (!dialog.open) settleConfirmation(dialog, dialog.returnValue);
      });
    });
  };
})(window.Admin);
