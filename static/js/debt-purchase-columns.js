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

  function animateVisibleContent(table) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const viewport = table.closest('.table-container').getBoundingClientRect();
    // Offscreen rows never need animation, even when the page contains 100 rows.
    const visibleRows = Array.from(table.rows).filter(row => {
      const bounds = row.getBoundingClientRect();
      return bounds.bottom > viewport.top && bounds.top < viewport.bottom;
    });
    const visibleContent = visibleRows.flatMap(row =>
      Array.from(row.querySelectorAll('.purchase-column-content, .accrued-column-content, .payment-column-content')).filter(content => {
        const bounds = content.getBoundingClientRect();
        return bounds.right > viewport.left && bounds.left < viewport.right;
      })
    );
    visibleContent.forEach(content => content.animate([
      { opacity: 0, transform: 'translateX(-14px)' },
      { opacity: 1, transform: 'translateX(0)' }
    ], { duration: 220, easing: 'ease-out' }));
  }

  function apply(table, restoring = false) {
    table.querySelectorAll('.purchase-column-content, .accrued-column-content').forEach(content => {
      content.getAnimations().forEach(animation => animation.cancel());
    });
    table.classList.toggle('is-purchase-expanded', expanded);
    table.classList.toggle('is-accrued-expanded', accruedExpanded);
    table.classList.toggle('is-payment-expanded', paymentsExpanded);
    table.querySelectorAll('[data-purchase-column]').forEach(cell => {
      cell.setAttribute('aria-hidden', String(!expanded));
    });
    const button = table.querySelector('[data-purchase-toggle]');
    button.setAttribute('aria-expanded', String(expanded));
    button.setAttribute('aria-label', (expanded ? 'Скрыть' : 'Показать') + ' состав общей суммы задолженности (выкуп)');
    const accruedButton = table.querySelector('[data-accrued-toggle]');
    if (accruedButton) {
      accruedButton.setAttribute('aria-expanded', String(accruedExpanded));
      accruedButton.setAttribute('aria-label', (accruedExpanded ? 'Скрыть' : 'Показать') + ' состав общей суммы задолженности');
    }
    const paymentButton = table.querySelector('[data-payment-toggle]');
    if (paymentButton) {
      paymentButton.setAttribute('aria-expanded', String(paymentsExpanded));
      paymentButton.setAttribute('aria-label', (paymentsExpanded ? 'Скрыть' : 'Показать') + ' состав суммы платежей');
    }
    if ((expanded || accruedExpanded) && !restoring) animateVisibleContent(table);
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
    apply(button.closest('[data-purchase-breakdown]'));
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-accrued-toggle]');
    if (!button) return;
    accruedExpanded = !accruedExpanded;
    window.Admin.storage.set('debtAccruedExpanded', accruedExpanded);
    apply(button.closest('[data-purchase-breakdown]'));
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-payment-toggle]');
    if (!button) return;
    paymentsExpanded = !paymentsExpanded;
    window.Admin.storage.set('debtPaymentsExpanded', paymentsExpanded);
    apply(button.closest('[data-purchase-breakdown]'));
  });
})();
