document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.querySelector('[data-auto-open]');
  if (dialog) {
    // A non-modal open dialog remains usable when JavaScript is unavailable.
    if (dialog.open) dialog.close();
    window.Admin.modal.show(dialog);
  }
  const confirmation = document.querySelector('[data-import-confirm]');
  confirmation?.addEventListener('submit', (event) => {
    if (confirmation.dataset.submitting) {
      event.preventDefault();
      return;
    }
    confirmation.dataset.submitting = 'true';
    confirmation.setAttribute('aria-busy', 'true');
    if (event.submitter) event.submitter.textContent = 'Обработка…';
  });
});
