/* Reveal purchase components as columns to the right of the loaded total. */
(function () {
  if (performance.getEntriesByType('navigation')[0]?.type === 'reload') {
    window.Admin.storage.remove('debtPurchaseExpanded');
    window.Admin.storage.remove('debtAccruedExpanded');
    window.Admin.storage.remove('debtPaymentsExpanded');
  }
  let expanded = window.Admin.storage.get('debtPurchaseExpanded', false) === true;
  let accruedExpanded = window.Admin.storage.get('debtAccruedExpanded', false) === true;
  let paymentsExpanded = window.Admin.storage.get('debtPaymentsExpanded', false) === true;

  const transitions = new WeakMap();

  function visibleContent(table, selector) {
    const viewport = table.closest('.table-container').getBoundingClientRect();
    // Offscreen rows never need animation, even when the page contains 100 rows.
    const visibleRows = Array.from(table.rows).filter(row => {
      const bounds = row.getBoundingClientRect();
      return bounds.bottom > viewport.top && bounds.top < viewport.bottom;
    });
    return visibleRows.flatMap(row =>
      Array.from(row.querySelectorAll(selector)).filter(content => {
        const bounds = content.getBoundingClientRect();
        return bounds.right > viewport.left && bounds.left < viewport.right;
      })
    );
  }

  function applyGroup(table, group, open, label, restoring = false) {
    let pending = transitions.get(table);
    if (!pending) { pending = new Map(); transitions.set(table, pending); }
    const previous = pending.get(group);
    previous?.animations.forEach(animation => animation.cancel());
    pending.delete(group);
    const className = `is-${group}-expanded`;
    const wasOpen = table.classList.contains(className);
    table.querySelectorAll(`[data-${group}-column]`).forEach(cell => {
      cell.setAttribute('aria-hidden', String(!open));
    });
    const button = table.querySelector(`[data-${group}-toggle]`);
    if (button) {
      button.setAttribute('aria-expanded', String(open));
      button.setAttribute('aria-label', (open ? 'Скрыть' : 'Показать') + ' состав ' + label);
    }
    if (restoring || window.matchMedia('(prefers-reduced-motion: reduce)').matches || (!open && !wasOpen)) {
      table.classList.toggle(className, open);
      return;
    }
    // Keep closing columns visible until their exit animation finishes.
    table.classList.add(className);
    const frames = [
      { opacity: 0, transform: 'translateX(-14px)' },
      { opacity: 1, transform: 'translateX(0)' }
    ];
    const animations = visibleContent(table, `.${group}-column-content`).map(content =>
      content.animate(open ? frames : [...frames].reverse(), {
        duration: 220, easing: open ? 'ease-out' : 'ease-in', fill: 'both'
      })
    );
    const transition = { animations };
    pending.set(group, transition);
    const complete = () => {
      // An earlier closing animation must not hide a reopened group.
      if (pending.get(group) !== transition) return;
      table.classList.toggle(className, open);
      pending.delete(group);
      animations.forEach(animation => animation.cancel());
    };
    if (!animations.length) complete();
    else Promise.all(animations.map(animation => animation.finished)).then(complete, () => {});
  }

  function apply(table, restoring = false) {
    applyGroup(table, 'purchase', expanded, 'общей суммы задолженности (выкуп)', restoring);
    applyGroup(table, 'accrued', accruedExpanded, 'общей суммы задолженности', restoring);
    applyGroup(table, 'payment', paymentsExpanded, 'суммы платежей', restoring);
  }

  function restore() {
    document.querySelectorAll('[data-purchase-breakdown]').forEach(table => apply(table, true));
  }
  document.addEventListener('DOMContentLoaded', restore);
  document.addEventListener('balances:updated', restore);
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-purchase-toggle]');
    if (!button) return;
    expanded = !expanded;
    window.Admin.storage.set('debtPurchaseExpanded', expanded);
    applyGroup(button.closest('[data-purchase-breakdown]'), 'purchase', expanded, 'общей суммы задолженности (выкуп)');
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-accrued-toggle]');
    if (!button) return;
    accruedExpanded = !accruedExpanded;
    window.Admin.storage.set('debtAccruedExpanded', accruedExpanded);
    applyGroup(button.closest('[data-purchase-breakdown]'), 'accrued', accruedExpanded, 'общей суммы задолженности');
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-payment-toggle]');
    if (!button) return;
    paymentsExpanded = !paymentsExpanded;
    window.Admin.storage.set('debtPaymentsExpanded', paymentsExpanded);
    applyGroup(button.closest('[data-purchase-breakdown]'), 'payment', paymentsExpanded, 'суммы платежей');
  });
})();
