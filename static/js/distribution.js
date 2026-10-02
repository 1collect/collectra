(() => {
    const mode = document.querySelector('[name="mode"]');
    if (!mode) return;
    const form = mode.form;
    const fields = [...form.querySelectorAll('.form-field')].filter(row => !row.contains(mode));
    function update() {
        const manual = mode.value === 'manual';
        fields.forEach(row => {
            row.hidden = !manual;
            row.querySelectorAll('input, textarea').forEach(input => {
                input.disabled = !manual;
                if (input.name === 'comment') input.required = manual;
            });
        });
    }
    mode.addEventListener('change', update);
    update();
})();
