document.addEventListener('DOMContentLoaded', function () {
  window.Admin.initSidebar();
  window.Admin.initDropdowns();
  window.Admin.initModals();
  document.documentElement.dataset.ready = 'true';
});
