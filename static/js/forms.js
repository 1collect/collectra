/* Form validation, file metadata previews, comboboxes and the demo user editor. */
(function (A) {
  'use strict';
  function validate(form) {
    let first = null;
    A.$$('input,select,textarea', form).forEach(control => {
      if (control.disabled || control.type === 'hidden') return;
      // Treat whitespace-only required text as empty without modifying passwords.
      control.setCustomValidity('');
      if (control.required && ['text', 'email', 'tel'].includes(control.type) && !control.value.trim()) control.setCustomValidity('Please complete this field.');
      const valid = control.checkValidity();
      control.setAttribute('aria-invalid', String(!valid));
      const field = control.closest('.form-field');
      const error = field && field.querySelector('.field-error');
      if (error) error.textContent = valid ? '' : control.validationMessage;
      if (!valid && !first) first = control;
    });
    if (first) { first.focus(); if (!first.closest('.form-field')?.querySelector('.field-error')) first.reportValidity(); }
    return !first;
  }
  A.forms = { validate };
  function payload(form, existing = {}) {
    const values = new FormData(form);
    return {
      id: existing.id || Math.max(1000, ...A.data.users().map(row => row.id)) + 1,
      name: String(values.get('name') || [values.get('firstName'), values.get('lastName')].filter(Boolean).join(' ')).trim(),
      email: String(values.get('email') || '').trim(),
      department: String(values.get('department') || 'IT'),
      role: String(values.get('role') || 'Employee').trim(),
      status: String(values.get('status') || 'active'),
      phone: String(values.get('phone') || '').trim(),
      created: String(values.get('created') || existing.created || new Date().toISOString().slice(0, 10)),
      comment: String(values.get('comment') || '').trim()
    };
  }
  function saveEmployee(form) {
    if (!validate(form)) return false;
    const id = Number(form.dataset.userId) || null;
    const users = A.data.users();
    const existing = users.find(row => row.id === id);
    const next = payload(form, existing);
    const duplicate = users.find(row => row.email.toLocaleLowerCase() === next.email.toLocaleLowerCase() && row.id !== id);
    if (duplicate) {
      const control = form.elements.namedItem('email');
      control.setCustomValidity('An employee with this email already exists.');
      control.setAttribute('aria-invalid', 'true');
      const error = control.closest('.form-field').querySelector('.field-error');
      if (error) error.textContent = control.validationMessage;
      control.focus(); return false;
    }
    A.data.saveUsers(existing ? users.map(row => row.id === id ? next : row) : [...users, next], existing ? 'Updated employee' : 'Created employee', 'USR-' + next.id);
    const dialog = form.closest('dialog'); if (dialog) A.modal.close(dialog, 'saved');
    A.toast('success', existing ? 'Employee updated' : 'Employee added', next.name + ' was saved in this browser.');
    if (!existing) form.reset();
    return true;
  }
  A.users = {
    edit(id) {
      const dialog = document.getElementById('employee-editor');
      const form = dialog.querySelector('form');
      const user = id ? A.data.users().find(row => row.id === Number(id)) : null;
      form.reset(); form.dataset.userId = user ? user.id : '';
      A.$$('.field-error', form).forEach(error => { error.textContent = ''; });
      A.$$('input,select,textarea', form).forEach(control => {
        control.setCustomValidity(''); control.removeAttribute('aria-invalid');
        if (user && control.name in user) control.value = user[control.name];
      });
      dialog.querySelector('h2').textContent = user ? 'Edit employee' : 'Add employee';
      if (!user) form.elements.namedItem('created').value = new Date().toISOString().slice(0, 10);
      A.modal.show(dialog);
    },
    view(id) {
      const user = A.data.users().find(row => row.id === Number(id));
      if (!user) return;
      const drawer = document.getElementById('employee-details');
      A.$('[data-detail-content]', drawer).innerHTML = `<div class="flex items-center gap-3 mb-4">${A.avatar(user.name, user.id, 'avatar-lg')}<div><h3>${A.escape(user.name)}</h3><p class="text-xs text-muted">${A.escape(user.role)} &middot; USR-${user.id}</p></div></div><dl class="detail-list"><dt>Status</dt><dd>${A.statusBadge(user.status)}</dd><dt>Email</dt><dd>${A.escape(user.email)}</dd><dt>Department</dt><dd>${A.escape(user.department)}</dd><dt>Phone</dt><dd>${A.escape(user.phone || 'Not provided')}</dd><dt>Created</dt><dd>${A.escape(A.formatDate(user.created))}</dd><dt>Comment</dt><dd>${A.escape(user.comment || 'No comment')}</dd></dl><hr><h3 class="mb-3">Recent activity</h3><ul class="timeline"><li><time>${A.escape(A.formatDate(user.created))}</time> Employee created<p>Local demonstration record.</p></li><li>Current status: ${A.escape(user.status)}<p>Changes in this demo are stored only in your browser.</p></li></ul>`;
      A.$('[data-details-edit]', drawer).dataset.id = user.id;
      A.modal.show(drawer);
    },
    async remove(ids) {
      const users = A.data.users();
      const chosen = users.filter(row => ids.includes(row.id));
      if (!chosen.length) return;
      const confirmed = await A.confirm({ title: chosen.length === 1 ? 'Delete employee?' : 'Delete ' + chosen.length + ' employees?', message: chosen.length === 1 ? chosen[0].name + ' will be removed from local demo data. You can restore the seed data in Settings.' : 'The selected local demo records will be removed. Restore the seed data in Settings when needed.', label: 'Delete', danger: true });
      if (!confirmed) return;
      A.data.saveUsers(A.data.users().filter(row => !ids.includes(row.id)), 'Deleted employees', chosen.length + ' records');
      A.toast('success', 'Employees deleted', chosen.length + ' local records removed.');
    }
  };
  function initCombobox(group) {
    const input = A.$('[role="combobox"]', group);
    const list = A.$('[role="listbox"]', group);
    const hidden = A.$('input[type="hidden"]', group);
    const options = group.dataset.options.split('|');
    let matches = options, active = -1, committed = input.value;
    const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); };
    const select = value => { input.value = value; committed = value; if (hidden) hidden.value = value; close(); input.focus(); };
    const render = () => {
      list.innerHTML = matches.length ? matches.map((value, index) => `<button type="button" class="combobox-option" role="option" tabindex="-1" id="${list.id}-${index}" aria-selected="${index === active}" data-option="${A.escape(value)}">${A.escape(value)}</button>`).join('') : '<div class="p-3 text-xs text-muted" role="option" aria-disabled="true">No results</div>';
      list.hidden = false; input.setAttribute('aria-expanded', 'true');
      if (active >= 0 && matches[active]) { input.setAttribute('aria-activedescendant', list.id + '-' + active); list.children[active]?.scrollIntoView({ block: 'nearest' }); }
      else input.removeAttribute('aria-activedescendant');
    };
    input.addEventListener('focus', () => { matches = options; active = -1; render(); });
    input.addEventListener('input', () => { matches = options.filter(value => value.toLowerCase().includes(input.value.toLowerCase())); active = -1; if (hidden) hidden.value = ''; render(); });
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { close(); input.value = committed; if (hidden) hidden.value = committed; }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); active = Math.max(0, Math.min(matches.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1))); render(); }
      if (event.key === 'Enter' && !list.hidden && matches[active]) { event.preventDefault(); select(matches[active]); }
    });
    list.addEventListener('mousedown', event => event.preventDefault());
    list.addEventListener('click', event => { const option = event.target.closest('[data-option]'); if (option) select(option.dataset.option); });
    document.addEventListener('click', event => { if (!group.contains(event.target)) close(); });
    input.addEventListener('blur', () => {
      setTimeout(() => { if (!group.contains(document.activeElement)) { close(); const match = options.find(value => value.toLowerCase() === input.value.toLowerCase()); input.value = match || committed; if (hidden) hidden.value = input.value; } }, 0);
    });
  }
  function initUpload(group) {
    const input = A.$('input[type="file"]', group);
    const list = A.$('.file-list', group);
    const zone = A.$('.dropzone', group);
    let files = [];
    function render() {
      list.innerHTML = files.map((file, index) => `<li>${A.icon('file')}<span>${A.escape(file.name)} <span class="text-muted">${(file.size / 1024).toFixed(1)} KB</span></span><button type="button" class="btn btn-icon btn-sm btn-ghost" data-remove-file="${index}" aria-label="Remove ${A.escape(file.name)}">${A.icon('x')}</button></li>`).join('');
    }
    function add(incoming) {
      Array.from(incoming).forEach(file => {
        if (file.size > 10 * 1024 * 1024) { A.toast('warning', 'File too large', file.name + ' exceeds the 10 MB demo limit.'); return; }
        if (!files.some(existing => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified)) files.push(file);
      });
      render(); input.value = '';
    }
    input.addEventListener('change', () => add(input.files));
    if (zone) {
      zone.addEventListener('dragover', event => { event.preventDefault(); zone.classList.add('is-over'); });
      zone.addEventListener('dragleave', () => zone.classList.remove('is-over'));
      zone.addEventListener('drop', event => { event.preventDefault(); zone.classList.remove('is-over'); add(event.dataTransfer.files); });
    }
    list.addEventListener('click', event => { const button = event.target.closest('[data-remove-file]'); if (button) { files.splice(Number(button.dataset.removeFile), 1); render(); } });
  }
  A.initForms = function () {
    A.$$('form').forEach(form => form.addEventListener('reset', () => {
      setTimeout(() => {
        A.$$('input,select,textarea', form).forEach(control => { control.setCustomValidity(''); control.removeAttribute('aria-invalid'); });
        A.$$('.field-error', form).forEach(error => { error.textContent = ''; });
        A.$$('[data-counter]', form).forEach(control => control.dispatchEvent(new Event('input', { bubbles: true })));
      }, 0);
    }));
    document.addEventListener('click', event => {
      const target = event.target.closest('button'); if (!target) return;
      if (target.hasAttribute('data-user-add')) A.users.edit();
      if (target.hasAttribute('data-details-edit')) { const id = target.dataset.id; A.modal.close(target.closest('dialog')); A.users.edit(id); }
      if (target.hasAttribute('data-password-toggle')) {
        const input = target.closest('.password-field').querySelector('input');
        const show = input.type === 'password'; input.type = show ? 'text' : 'password';
        target.innerHTML = A.icon(show ? 'eye-off' : 'eye'); target.setAttribute('aria-label', show ? 'Hide password' : 'Show password'); target.setAttribute('aria-pressed', String(show));
      }
    });
    document.addEventListener('input', event => {
      if (event.target.matches('input,textarea,select')) {
        event.target.setCustomValidity('');
        if (event.target.getAttribute('aria-invalid') === 'true' && event.target.checkValidity()) {
          event.target.setAttribute('aria-invalid', 'false');
          const error = event.target.closest('.form-field')?.querySelector('.field-error'); if (error) error.textContent = '';
        }
      }
    });
    A.$$('form[data-user-form]').forEach(form => form.addEventListener('submit', event => { event.preventDefault(); saveEmployee(form); }));
    A.$$('form[data-save-demo]').forEach(form => form.addEventListener('submit', event => {
      event.preventDefault(); if (!validate(form)) return;
      const key = form.dataset.saveDemo;
      const values = Object.fromEntries(new FormData(form).entries());
      A.$$('input[type="checkbox"]', form).forEach(control => { if (control.name) values[control.name] = control.checked; });
      A.storage.set(key, values); A.emit('demo:settings-changed');
      const dialog = form.closest('dialog'); if (dialog) A.modal.close(dialog, 'saved');
      A.toast('success', 'Changes saved', 'These settings are stored in this browser only.');
    }));
    A.$$('[data-counter]').forEach(textarea => {
      const counter = document.getElementById(textarea.dataset.counter);
      const update = () => { counter.textContent = textarea.value.length + ' / ' + textarea.maxLength; };
      textarea.addEventListener('input', update); update();
    });
    A.$$('[data-indeterminate]').forEach(input => { input.indeterminate = true; });
    A.$$('[data-combobox]').forEach(initCombobox);
    A.$$('[data-upload]').forEach(initUpload);
    A.$$('form[data-inline-search]').forEach(form => form.addEventListener('submit', event => {
      event.preventDefault();
      const query = String(new FormData(form).get('q') || '').trim().toLowerCase();
      const result = A.data.users().filter(row => row.name.toLowerCase().includes(query)).slice(0, 5);
      const output = document.getElementById(form.dataset.inlineSearch);
      output.textContent = result.length ? result.map(row => row.name).join(' | ') : 'No matching employees.';
    }));
  };
})(window.Admin);
