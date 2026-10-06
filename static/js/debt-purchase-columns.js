/* Reveal purchase components as columns to the right of the loaded total. */
(function () {
  if (performance.getEntriesByType('navigation')[0]?.type === 'reload') {
    window.Admin.storage.remove('debtPurchaseExpanded');
  }
  let expanded = window.Admin.storage.get('debtPurchaseExpanded', false) === true;

  function animateVisibleContent(table) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const viewport = table.closest('.table-container').getBoundingClientRect();
    // Offscreen rows never need animation, even when the page contains 100 rows.
    const visibleRows = Array.from(table.rows).filter(row => {
      const bounds = row.getBoundingClientRect();
      return bounds.bottom > viewport.top && bounds.top < viewport.bottom;
    });
    const visibleContent = visibleRows.flatMap(row =>
      Array.from(row.querySelectorAll('.purchase-column-content')).filter(content => {
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
    table.querySelectorAll('.purchase-column-content').forEach(content => {
      content.getAnimations().forEach(animation => animation.cancel());
    });
    table.classList.toggle('is-purchase-expanded', expanded);
    table.querySelectorAll('[data-purchase-column]').forEach(cell => {
      cell.setAttribute('aria-hidden', String(!expanded));
    });
    const button = table.querySelector('[data-purchase-toggle]');
    button.setAttribute('aria-expanded', String(expanded));
    button.setAttribute('aria-label', (expanded ? 'Скрыть' : 'Показать') + ' состав общей суммы задолженности (выкуп)');
    if (expanded && !restoring) animateVisibleContent(table);
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
})();
