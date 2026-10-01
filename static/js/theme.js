/* Runs in <head> to prevent a light-theme flash. Safe when storage is blocked. */
(function (A) {
  'use strict';
  const root = document.documentElement;
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'light';
  try { preference = localStorage.getItem('circuit.theme') || 'light'; } catch (_) { /* Private-mode fallback. */ }
  if (!['light', 'dark', 'system'].includes(preference)) preference = 'light';
  function apply() {
    root.dataset.theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    document.querySelectorAll('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === preference)));
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-label', 'Switch to ' + (root.dataset.theme === 'dark' ? 'light' : 'dark') + ' theme');
      if (A.icon) button.innerHTML = A.icon(root.dataset.theme === 'dark' ? 'sun' : 'moon');
    });
  }
  A.theme = {
    get preference() { return preference; },
    set(value) {
      if (!['light', 'dark', 'system'].includes(value)) return;
      preference = value;
      try { localStorage.setItem('circuit.theme', value); } catch (_) { /* In-memory theme still works. */ }
      apply();
    },
    init() {
      apply();
      document.addEventListener('click', event => {
        if (event.target.closest('[data-theme-toggle]')) A.theme.set(root.dataset.theme === 'dark' ? 'light' : 'dark');
        const choice = event.target.closest('[data-theme-choice]');
        if (choice) A.theme.set(choice.dataset.themeChoice);
      });
    }
  };
  apply();
  media.addEventListener('change', () => { if (preference === 'system') apply(); });
  try {
    if (localStorage.getItem('circuit.sidebar') === 'collapsed') root.classList.add('sidebar-collapsed');
    root.dataset.density = localStorage.getItem('circuit.density') === 'comfortable' ? 'comfortable' : 'compact';
  } catch (_) { root.dataset.density = 'compact'; }
})(window.Admin = window.Admin || {});
