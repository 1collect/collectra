const recordFilterTimers = new WeakMap();

function submitRecordFilters(form) {
  clearTimeout(recordFilterTimers.get(form));
  if (form.checkValidity()) form.requestSubmit();
}

document.addEventListener('input', event => {
  if (!event.target.matches('[data-record-filters] input[name="q"]') || event.isComposing) return;
  const form = event.target.form;
  clearTimeout(recordFilterTimers.get(form));
  recordFilterTimers.set(form, setTimeout(() => submitRecordFilters(form), 600));
});

document.addEventListener('keydown', event => {
  if (event.key !== 'Enter' || event.isComposing || !event.target.matches('[data-record-filters] input[name="q"]')) return;
  event.preventDefault();
  submitRecordFilters(event.target.form);
});

document.addEventListener('submit', event => {
  if (event.target.matches('[data-record-filters]')) clearTimeout(recordFilterTimers.get(event.target));
});

document.addEventListener('change', event => {
  if (event.target.matches('[data-record-page-size]')) event.target.form.requestSubmit();
  const form = event.target.closest('[data-record-filters]');
  if (form) submitRecordFilters(form);
});

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('[data-record-filter-toggle]');
  const panel = toggle && document.getElementById(toggle.getAttribute('aria-controls'));
  if (!panel) return;
  const key = `${document.body.dataset.page}.filtersExpanded`;
  const isReload = performance.getEntriesByType('navigation')[0]?.type === 'reload';
  if (isReload) {
    window.Admin.storage.remove(key);
    if (location.search) {
      location.replace(location.pathname);
      return;
    }
  }
  const setExpanded = expanded => {
    panel.classList.toggle('is-open', expanded);
    panel.inert = !expanded;
    toggle.setAttribute('aria-expanded', String(expanded));
  };
  if (isReload) {
    setExpanded(false);
  } else if (toggle.getAttribute('aria-expanded') !== 'true') {
    setExpanded(window.Admin.storage.get(key, false));
  }
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') !== 'true';
    setExpanded(expanded);
    window.Admin.storage.set(key, expanded);
  });
});
