(function (A) {
  'use strict';
  A.initSidebar = function () {
    const sidebar = A.$('.sidebar');
    if (!sidebar) return;
    const media = window.matchMedia('(max-width: 800px)');
    const toggle = A.$('[data-sidebar-toggle]');
    let returnFocus = null;
    const setMobile = open => {
      if (open) returnFocus = document.activeElement;
      document.body.classList.toggle('sidebar-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      sidebar.inert = media.matches && !open;
      A.$('.shell-main').inert = media.matches && open;
      if (open) A.$('a, button', sidebar).focus();
      else if (returnFocus) { returnFocus.focus(); returnFocus = null; }
    };
    const sync = () => {
      if (!media.matches) {
        document.body.classList.remove('sidebar-open');
        sidebar.inert = false; A.$('.shell-main').inert = false;
        toggle.setAttribute('aria-expanded', String(!document.documentElement.classList.contains('sidebar-collapsed')));
      } else setMobile(false);
    };
    toggle.addEventListener('click', () => {
      if (media.matches) setMobile(!document.body.classList.contains('sidebar-open'));
      else {
        const collapsed = document.documentElement.classList.toggle('sidebar-collapsed');
        toggle.setAttribute('aria-expanded', String(!collapsed));
        try { localStorage.setItem('circuit.sidebar', collapsed ? 'collapsed' : 'expanded'); } catch (_) {}
      }
    });
    A.$('[data-sidebar-close]').addEventListener('click', () => setMobile(false));
    A.$$('[data-submenu-toggle]').forEach(button => button.addEventListener('click', () => {
      if (!media.matches && document.documentElement.classList.contains('sidebar-collapsed')) {
        document.documentElement.classList.remove('sidebar-collapsed');
        try { localStorage.setItem('circuit.sidebar', 'expanded'); } catch (_) {}
      }
      const content = document.getElementById(button.getAttribute('aria-controls'));
      const open = button.getAttribute('aria-expanded') !== 'true';
      button.setAttribute('aria-expanded', String(open)); content.hidden = !open;
    }));
    document.addEventListener('keydown', event => {
      if (!document.body.classList.contains('sidebar-open')) return;
      if (event.key === 'Escape') { event.preventDefault(); setMobile(false); }
      if (event.key === 'Tab') {
        const focusable = A.$$('a,button', sidebar).filter(el => el.offsetParent !== null && !el.disabled);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    media.addEventListener('change', sync); sync();
  };
})(window.Admin);
