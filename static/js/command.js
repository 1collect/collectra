(function (A) {
  'use strict';
  A.initCommandSearch = function () {
    const dialog = document.getElementById('command-dialog');
    if (!dialog) return;
    const input = A.$('[data-command-input]', dialog);
    const output = A.$('[data-command-results]', dialog);
    const pages = [
      ['dashboard', 'Dashboard', 'grid'], ['analytics', 'Analytics', 'chart'],
      ['users', 'All users', 'users'], ['employees', 'Employees', 'briefcase'],
      ['departments', 'Departments', 'building'], ['tasks', 'Tasks', 'check-square'],
      ['reports', 'Reports', 'file'], ['ui-elements', 'UI Elements', 'layers'],
      ['forms', 'Forms', 'form'], ['tables', 'Tables', 'table'], ['icons', 'Icons', 'grid'],
      ['roles', 'Roles', 'shield'], ['permissions', 'Permissions', 'lock'],
      ['settings', 'Settings', 'settings'], ['logs', 'Activity logs', 'activity']
    ];
    const render = () => {
      const query = input.value.trim().toLowerCase();
      const entries = pages.map(([slug, title, icon]) => ({ title, icon, type: 'Page', href: A.pageHref(slug) }));
      if (query) {
        (A.componentIndex || []).forEach(item => entries.push({ title: item.title, icon: 'code', type: 'Component', href: A.pageHref('ui-elements') + '#' + item.id }));
        A.data.users().forEach(user => entries.push({ title: user.name + ' - ' + user.department, icon: 'user', type: 'Employee', href: A.pageHref('users') + '?q=' + encodeURIComponent(user.email) }));
      }
      const matches = entries.filter(entry => entry.title.toLowerCase().includes(query)).slice(0, 12);
      output.innerHTML = matches.length ? matches.map(entry => `<a class="command-result" href="${A.escape(entry.href)}">${A.icon(entry.icon)}<span>${A.escape(entry.title)}</span><span class="badge">${entry.type}</span></a>`).join('') : '<div class="empty-state"><h3>No results</h3><p>Try a page, component or employee name.</p></div>';
    };
    function open() { input.value = ''; render(); A.modal.show(dialog); input.focus(); }
    document.addEventListener('click', event => { if (event.target.closest('[data-command-open]')) open(); });
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); if (dialog.open) A.modal.close(dialog); else if (!document.querySelector('dialog[open]')) open(); }
    });
    input.addEventListener('input', render);
    dialog.addEventListener('keydown', event => {
      // A search input can consume Escape to clear text before native dialog dismissal.
      if (event.key === 'Escape') { event.preventDefault(); A.modal.close(dialog); return; }
      const links = A.$$('a', output); if (!links.length) return;
      const index = links.indexOf(document.activeElement);
      if (event.key === 'ArrowDown') { event.preventDefault(); links[(index + 1) % links.length].focus(); }
      if (event.key === 'ArrowUp') { event.preventDefault(); if (index <= 0) input.focus(); else links[index - 1].focus(); }
      if (event.key === 'Enter' && document.activeElement === input) { event.preventDefault(); links[0].click(); }
    });
    render();
  };
})(window.Admin);
