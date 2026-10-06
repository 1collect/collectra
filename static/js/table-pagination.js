document.addEventListener('change', event => {
  if (event.target.matches('[data-record-page-size]')) event.target.form.requestSubmit();
  const form = event.target.closest('[data-record-filters]');
  if (form?.checkValidity()) form.requestSubmit();
});

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('[data-record-filter-toggle]');
  const panel = toggle && document.getElementById(toggle.getAttribute('aria-controls'));
  if (!panel) return;
  const key = `${document.body.dataset.page}.filtersExpanded`;
  const setExpanded = expanded => {
    panel.classList.toggle('is-open', expanded);
    panel.inert = !expanded;
    toggle.setAttribute('aria-expanded', String(expanded));
  };
  if (toggle.getAttribute('aria-expanded') !== 'true') {
    setExpanded(window.Admin.storage.get(key, false));
  }
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') !== 'true';
    setExpanded(expanded);
    window.Admin.storage.set(key, expanded);
  });
});
