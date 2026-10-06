/* Selection and disclosure stay available after live balance updates. */
function filterBorrowerContracts() {
  const form = document.querySelector('[data-contract-selection]');
  if (!form) return;
  const query = form.querySelector('[data-contract-search]').value.trim().toLocaleLowerCase('ru-RU');
  let visible = 0;
  form.querySelectorAll('[data-contract-option]').forEach(option => {
    option.hidden = !option.dataset.contractOption.toLocaleLowerCase('ru-RU').includes(query);
    if (!option.hidden) visible++;
  });
  form.querySelector('[data-contract-search-empty]').hidden = visible > 0;
  form.querySelector('[data-contract-select-all]').disabled = visible === 0;
}
document.addEventListener('DOMContentLoaded', filterBorrowerContracts);
document.addEventListener('balances:updated', filterBorrowerContracts);
document.addEventListener('input', event => {
  if (event.target.matches('[data-contract-search]')) filterBorrowerContracts();
});
document.addEventListener('click', event => {
  const navigation = event.target.closest('.borrower-columns a[href^="?"]');
  if (navigation) {
    const target = new URL(navigation.href);
    const query = document.querySelector('[data-contract-search]')?.value || '';
    if (query) target.searchParams.set('contract_search', query);
    else target.searchParams.delete('contract_search');
    navigation.href = target.href;
  }
  const selectionAction = event.target.closest('[data-contract-select-all], [data-contract-clear]');
  if (selectionAction) {
    const form = selectionAction.closest('form');
    const clear = selectionAction.hasAttribute('data-contract-clear');
    form.querySelectorAll('[data-contract-option]').forEach(option => {
      if (clear || !option.hidden) option.querySelector('input').checked = !clear;
    });
    form.requestSubmit();
    return;
  }
  const row = event.target.closest('[data-operation-row]');
  if (!row || (event.target.closest('a, input, select') && !event.target.closest('[data-operation-toggle]'))) return;
  const button = row.querySelector('[data-operation-toggle]');
  const details = document.getElementById(button.getAttribute('aria-controls'));
  details.hidden = !details.hidden;
  button.setAttribute('aria-expanded', String(!details.hidden));
  button.textContent = details.hidden ? 'Подробнее' : 'Свернуть';
});
document.addEventListener('change', event => {
  if (event.target.matches('[data-contract-page-size]')) {
    const form = event.target.form;
    const searchValue = document.querySelector('[data-contract-search]')?.value || '';
    let search = form.querySelector('[name="contract_search"]');
    if (!search) { search = document.createElement('input'); search.type = 'hidden'; search.name = 'contract_search'; form.append(search); }
    search.value = searchValue;
    form.requestSubmit();
  }
  if (event.target.matches('[data-contract-selection] input[type="checkbox"]')) event.target.form.requestSubmit();
});
