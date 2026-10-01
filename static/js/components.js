/* Behavior for the UI Kit's small, reusable data-attribute components. */
(function (A) {
  'use strict';
  A.initComponents = function () {
    A.$$('table').forEach(table => {
      const master = A.$('[data-static-select-all]', table);
      if (!master) return;
      const rows = A.$$('[data-static-select]', table);
      const sync = () => {
        const count = rows.filter(input => input.checked).length;
        master.checked = count === rows.length && rows.length > 0;
        master.indeterminate = count > 0 && count < rows.length;
        rows.forEach(input => input.closest('tr').classList.toggle('is-selected', input.checked));
      };
      master.addEventListener('change', () => { rows.forEach(input => { input.checked = master.checked; }); sync(); });
      rows.forEach(input => input.addEventListener('change', sync)); sync();
    });
    document.addEventListener('click', async event => {
      const target = event.target.closest('button, [data-chip-remove]');
      if (!target) return;
      if (target.hasAttribute('data-code-toggle')) {
        const code = document.getElementById(target.getAttribute('aria-controls'));
        code.hidden = !code.hidden; target.setAttribute('aria-expanded', String(!code.hidden));
        target.classList.toggle('text-primary', !code.hidden);
      }
      if (target.hasAttribute('data-copy-code')) {
        const code = target.closest('.code-example').querySelector('code'); A.copyText(code.textContent);
      }
      if (target.hasAttribute('data-copy-text')) A.copyText(target.dataset.copyText);
      if (target.hasAttribute('data-alert-close')) target.closest('.alert').remove();
      if (target.hasAttribute('data-toast')) A.toast(target.dataset.toast, target.dataset.toastTitle || 'Component preview', target.dataset.toastMessage || 'This is a local notification example.');
      if (target.hasAttribute('data-tree-toggle')) {
        const expanded = target.getAttribute('aria-expanded') !== 'true';
        target.setAttribute('aria-expanded', String(expanded)); document.getElementById(target.getAttribute('aria-controls')).hidden = !expanded;
      }
      if (target.hasAttribute('data-chip-remove')) target.closest('.chip').remove();
      if (target.hasAttribute('data-select-tag')) target.setAttribute('aria-pressed', String(target.getAttribute('aria-pressed') !== 'true'));
      const group = target.closest('[data-toggle-group]');
      if (group) A.$$('button', group).forEach(button => button.setAttribute('aria-pressed', String(button === target)));
      if (target.hasAttribute('data-demo-confirm')) {
        const confirmed = await A.confirm({ title: 'Delete this demo item?', message: 'This preview demonstrates confirmation. No employee records will be changed.', label: 'Delete item', danger: true });
        if (confirmed) A.toast('success', 'Confirmed', 'The confirmation flow is complete. Demo data was not changed.');
      }
      if (target.hasAttribute('data-loading-action')) {
        const original = target.innerHTML; target.disabled = true;
        target.innerHTML = '<span class="spinner spinner-sm" aria-hidden="true"></span> Working...';
        target.setAttribute('aria-busy', 'true');
        setTimeout(() => { target.innerHTML = original; target.disabled = false; target.removeAttribute('aria-busy'); A.toast('success', 'Simulation complete', 'The button returned to its default state.'); }, 800);
      }
      if (target.hasAttribute('data-retry')) {
        const state = target.closest('[data-error-state]');
        state.innerHTML = '<div class="empty-state">' + A.icon('check-circle') + '<h3>Demo data loaded</h3><p>The simulated retry succeeded.</p><button class="btn btn-sm" data-error-reset>Show error again</button></div>';
      }
      if (target.hasAttribute('data-error-reset')) {
        target.closest('[data-error-state]').innerHTML = '<div class="empty-state">' + A.icon('warning') + '<h3>Unable to load data</h3><p>A simulated connection error.</p><button class="btn btn-sm" data-retry>Retry</button></div>';
      }
      if (target.hasAttribute('data-demo-page')) {
        const pagination = target.closest('[data-pagination-demo]');
        const number = Number(target.dataset.demoPage);
        A.$$('[data-demo-page]', pagination).forEach(button => {
          if (Number(button.dataset.demoPage) === number) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
        });
        A.$('[data-page-output]', pagination).textContent = 'Page ' + number + ' of 5 - showing demo items ' + ((number - 1) * 5 + 1) + '-' + number * 5;
      }
      if (target.hasAttribute('data-step-next') || target.hasAttribute('data-step-prev')) {
        const stepper = target.closest('[data-stepper]');
        let index = Number(stepper.dataset.stepIndex || 0);
        index = Math.max(0, Math.min(2, index + (target.hasAttribute('data-step-next') ? 1 : -1)));
        stepper.dataset.stepIndex = index;
        A.$$('.stepper li', stepper).forEach((step, i) => { step.classList.toggle('is-active', i === index); step.classList.toggle('is-complete', i < index); if (i === index) step.setAttribute('aria-current', 'step'); else step.removeAttribute('aria-current'); });
        A.$$('[data-step-content]', stepper).forEach((panel, i) => { panel.hidden = i !== index; });
        A.$('[data-step-prev]', stepper).disabled = index === 0;
        A.$('[data-step-next]', stepper).disabled = index === 2;
      }
      if (target.hasAttribute('data-icon-copy')) A.copyText('<span data-icon="' + target.dataset.iconCopy + '"></span>');
      if (target.hasAttribute('data-mark-notifications')) {
        A.storage.set('notifications-read', true);
        A.$$('.notification-button').forEach(button => button.classList.add('is-read'));
        A.$$('[data-unread-badge]').forEach(badge => { badge.hidden = true; });
        target.textContent = 'All read'; target.disabled = true;
        A.toast('success', 'Notifications cleared', 'All demonstration notifications are marked as read.');
      }
    });
    A.$$('[data-range-output]').forEach(input => {
      const update = () => { document.getElementById(input.dataset.rangeOutput).textContent = input.value + '%'; };
      input.addEventListener('input', update); update();
    });
    const finder = A.$('[data-component-search]');
    if (finder) {
      const applySearch = () => {
        const query = finder.value.trim().toLowerCase();
        let count = 0;
        A.$$('.component-panel').forEach(panel => {
          const show = (panel.dataset.search + ' ' + panel.querySelector('h2').textContent).toLowerCase().includes(query);
          panel.hidden = !show; if (show) count++;
        });
        A.$$('.kit-section-label').forEach(label => { label.hidden = !A.$$('.component-panel[data-group="' + label.dataset.group + '"]').some(panel => !panel.hidden); });
        A.$('[data-component-visible]').textContent = count;
        A.$('#component-no-results').hidden = count > 0;
      };
      finder.addEventListener('input', applySearch);
      A.$$('.kit-nav-links a').forEach(link => link.addEventListener('click', () => {
        if (finder.value) { finder.value = ''; applySearch(); }
        A.$$('.kit-nav-links a').forEach(item => item.classList.toggle('active', item === link));
      }));
      applySearch();
    }
    const iconSearch = A.$('[data-icon-search]');
    if (iconSearch) iconSearch.addEventListener('input', () => {
      const query = iconSearch.value.trim().toLowerCase(); let count = 0;
      A.$$('[data-icon-copy]').forEach(cell => { cell.hidden = !cell.dataset.iconCopy.includes(query); if (!cell.hidden) count++; });
      const output = A.$('[data-icon-count]'); if (output) output.textContent = count + ' icons';
    });
    if (A.storage.get('notifications-read', false)) {
      A.$$('.notification-button').forEach(button => button.classList.add('is-read'));
      A.$$('[data-unread-badge]').forEach(badge => { badge.hidden = true; });
    }
  };
})(window.Admin);
