/* Application boot. There is no build step, router or external runtime. */
(function (A) {
  'use strict';
  function profile() {
    const user = A.storage.get('profile', { name: 'Alex Morgan', email: 'alex.morgan@example.com', title: 'Workspace administrator' });
    A.$$('[data-profile-name]').forEach(node => { node.textContent = user.name || 'Alex Morgan'; });
    A.$$('[data-profile-email]').forEach(node => { node.textContent = user.email || 'alex.morgan@example.com'; });
    A.$$('[data-profile-initials]').forEach(node => { node.textContent = A.initials(user.name || 'Alex Morgan'); });
    const general = A.storage.get('general', { workspace: 'Acme Workspace' });
    A.$$('[data-workspace-name]').forEach(node => { node.textContent = general.workspace || 'Acme Workspace'; });
  }
  function settings() {
    A.$$('form[data-save-demo]').forEach(form => {
      const values = A.storage.get(form.dataset.saveDemo, {});
      A.$$('input,select,textarea', form).forEach(control => {
        if (!(control.name in values)) return;
        if (control.type === 'checkbox') control.checked = Boolean(values[control.name]);
        else control.value = values[control.name];
      });
    });
    A.$('[data-density-select]')?.addEventListener('change', event => {
      const value = event.target.value === 'comfortable' ? 'comfortable' : 'compact';
      document.documentElement.dataset.density = value;
      try { localStorage.setItem('circuit.density', value); } catch (_) {}
      A.notify('success', 'Density updated', 'Applied across the entire interface.');
    });
    const density = A.$('[data-density-select]'); if (density) density.value = document.documentElement.dataset.density || 'compact';
    A.$('[data-reset-demo]')?.addEventListener('click', async () => {
      if (await A.confirm({ title: 'Reset local demo data?', message: 'This restores the original employees, tasks and settings in this browser. Your theme and density preference will stay unchanged.', label: 'Reset demo', danger: true })) {
        A.data.reset(); profile(); location.reload();
      }
    });
    const security = A.$('form[data-security-demo]');
    if (security) security.addEventListener('submit', event => {
      event.preventDefault(); if (!A.forms.validate(security)) return;
      const password = security.elements.namedItem('new-password');
      const confirmation = security.elements.namedItem('confirm-password');
      if (password.value !== confirmation.value) { confirmation.setCustomValidity('The passwords do not match.'); confirmation.reportValidity(); return; }
      security.reset();
      A.notify('info', 'Validation complete', 'No password was changed or stored. Connect a secure backend to enable this action.');
    });
  }
  function authenticationDemo() {
    const form = A.$('[data-login-form]');
    if (form) form.addEventListener('submit', event => {
      event.preventDefault(); if (!A.forms.validate(form)) return;
      // This is explicitly a navigation demo. Never store or log credentials.
      form.elements.namedItem('password').value = '';
      location.href = A.pageHref('dashboard');
    });
    A.$('[data-forgot-form]')?.addEventListener('submit', event => {
      event.preventDefault(); if (!A.forms.validate(event.target)) return;
      A.modal.close(event.target.closest('dialog'));
      A.notify('info', 'Demo only', 'No email was sent. Add a backend password-reset endpoint to activate this flow.');
      event.target.reset();
    });
  }
  function boot() {
    A.renderIcons();
    A.theme.init(); A.initSidebar(); A.initDropdowns(); A.initModals(); A.initTabs();
    A.initTables(); A.initForms(); A.initComponents(); A.initCommandSearch();
    A.initTasks(); A.initDashboard(); settings(); authenticationDemo(); profile();
    document.addEventListener('demo:settings-changed', profile);
    window.addEventListener('storage', event => {
      if (event.key === 'circuit.users') A.emit('demo:users-changed');
      if (event.key === 'circuit.tasks') A.emit('demo:tasks-changed');
      if (event.key === 'circuit.logs') A.emit('demo:logs-changed');
      if (event.key === 'circuit.profile' || event.key === 'circuit.general') profile();
    });
    const persistence = A.$('[data-storage-status]');
    if (persistence) persistence.textContent = A.storage.available ? 'Local demo storage' : 'Temporary session storage';
    if (!A.storage.available) A.notify('warning', 'Storage unavailable', 'Changes may disappear on reload. Serve the folder over localhost for consistent storage.');
    document.documentElement.dataset.ready = 'true';
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})(window.Admin);
