/* Disclosure is delegated so live balance updates preserve interaction. */
document.addEventListener('click', event => {
  const row = event.target.closest('[data-operation-row]');
  if (!row || (event.target.closest('a, input, select') && !event.target.closest('[data-operation-toggle]'))) return;
  const button = row.querySelector('[data-operation-toggle]');
  const details = document.getElementById(button.getAttribute('aria-controls'));
  details.hidden = !details.hidden;
  button.setAttribute('aria-expanded', String(!details.hidden));
  button.textContent = details.hidden ? 'Подробнее' : 'Свернуть';
});
document.addEventListener('change', event => {
  if (event.target.matches('[data-contract-page-size]')) event.target.form.requestSubmit();
});
