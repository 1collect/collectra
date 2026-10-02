(() => {
    const form = document.getElementById('writeoff-form');
    if (!form) return;
    const kind = form.querySelector('[name="kind"]');
    const syncFields = () => {
        const partial = kind.value === 'partial';
        form.querySelectorAll('[data-partial-writeoff]').forEach(container => {
            container.hidden = !partial;
            container.querySelectorAll('input, select').forEach(field => {
                field.disabled = !partial;
                field.required = partial && field.name === 'amount';
            });
        });
    };
    kind.addEventListener('change', syncFields);
    syncFields();
})();
