(() => {
  const workspace = document.querySelector('[data-import-workspace]');
  if (!workspace) return;

  let controller;

  const updateSelection = selectedId => {
    workspace.querySelectorAll('[data-import-link]').forEach(link => {
      const selected = link.dataset.importId === selectedId;
      link.classList.toggle('is-active', selected);
      if (selected) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  };

  const loadDetail = async (url, pushState) => {
    if (controller) controller.abort();
    controller = new AbortController();
    workspace.classList.add('is-loading');
    workspace.querySelector('[data-import-detail]')?.setAttribute('aria-busy', 'true');

    try {
      const response = await fetch(url, {
        headers: {'X-Requested-With': 'XMLHttpRequest'},
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const html = await response.text();
      const nextDocument = new DOMParser().parseFromString(html, 'text/html');
      const nextDetail = nextDocument.querySelector('[data-import-detail]');
      const currentDetail = workspace.querySelector('[data-import-detail]');
      if (!nextDetail || !currentDetail) throw new Error('Import detail is missing');

      currentDetail.replaceWith(document.importNode(nextDetail, true));
      updateSelection(nextDetail.dataset.importId || '');
      document.title = nextDocument.title;
      if (pushState) history.pushState({importWorkspace: true}, '', response.url);
    } catch (error) {
      if (error.name !== 'AbortError') window.location.assign(url);
    } finally {
      workspace.classList.remove('is-loading');
    }
  };

  workspace.addEventListener('click', event => {
    const link = event.target.closest('[data-import-link], [data-import-page-link]');
    if (!link || event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    loadDetail(link.href, true);
  });

  window.addEventListener('popstate', () => loadDetail(window.location.href, false));

  document.addEventListener('DOMContentLoaded', () => {
    const dialog = document.querySelector('[data-auto-open]');
    if (dialog) window.Admin.modal.show(dialog);
  });
})();
