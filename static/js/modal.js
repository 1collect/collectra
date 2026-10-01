/* Native <dialog> supplies focus containment, top-layer rendering and Escape. */
(function (A) {
  'use strict';
  let pendingConfirmation = null;
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
    dialog.showModal();
  }
  function close(dialog, value = 'cancel') {
    if (dialog && dialog.open) {
      dialog.close(value);
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
        if (dialog.id === 'confirm-dialog') { event.preventDefault(); close(dialog); }
      });
      dialog.addEventListener('close', () => {
        A.dropdown.close();
        if (!dialog.open) settleConfirmation(dialog, dialog.returnValue);
      });
    });
  };
})(window.Admin);
