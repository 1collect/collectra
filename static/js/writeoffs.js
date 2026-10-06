(function (A) {
  A.initWriteoffs = function (root = document) {
    const form = root.querySelector('#writeoff-form');
    if (!form || form.dataset.initialized) return;
    form.dataset.initialized = 'true';
    const kind = form.querySelector('[name="kind"]');
    const syncFields = () => {
        const partial = kind.value === 'partial';
        const partialSection = form.querySelector('[data-partial-section]');
        if (partialSection) partialSection.hidden = !partial;
        form.querySelectorAll('[data-partial-writeoff]').forEach(container => {
            container.hidden = !partial;
            container.querySelectorAll('input, select').forEach(field => {
                field.disabled = !partial;
                field.required = partial && field.name === 'amount';
            });
        });
    };
    if (!kind) return;
    kind.addEventListener('change', syncFields);
    syncFields();
  };
  document.addEventListener('DOMContentLoaded', () => A.initWriteoffs());
})(window.Admin);
