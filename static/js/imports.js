document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.querySelector('[data-auto-open]');
  if (dialog) window.Admin.modal.show(dialog);
});
