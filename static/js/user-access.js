(() => {
  const form = document.querySelector('[data-user-access-form]');
  if (!form) return;
  const rolePermissions = JSON.parse(document.getElementById('role-permissions-data').textContent);
  const panel = form.querySelector('[data-extra-permissions]');
  const roles = [...form.querySelectorAll('input[name="roles"]')];
  const permissions = [...form.querySelectorAll('input[name="user_permissions"]')];
  const extras = new Set(permissions.filter(input => input.dataset.extraSelected === 'true')
    .map(input => input.value));

  function updatePermissions() {
    const selectedRoles = roles.filter(input => input.checked);
    const inherited = new Set(selectedRoles.flatMap(input => rolePermissions[input.value] || []));
    panel.hidden = selectedRoles.length === 0;
    permissions.forEach(input => {
      const fromRole = inherited.has(input.value);
      input.checked = fromRole || extras.has(input.value);
      input.disabled = fromRole || panel.hidden;
    });
  }

  roles.forEach(input => input.addEventListener('change', updatePermissions));
  permissions.forEach(input => input.addEventListener('change', () => {
    if (input.disabled) return;
    if (input.checked) extras.add(input.value);
    else extras.delete(input.value);
  }));
  window.addEventListener('pageshow', updatePermissions);
  updatePermissions();
})();
