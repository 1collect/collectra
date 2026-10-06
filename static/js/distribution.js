(function (A) {
  A.initDistribution = function (root = document) {
    const mode = root.querySelector('[name="mode"]');
    if (!mode || mode.dataset.initialized) return;
    mode.dataset.initialized = 'true';
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
  };
  A.initPaymentAllocation = function (root = document) {
    root.querySelectorAll('[data-payment-allocation-form]').forEach(form => {
      if (form.dataset.allocationInitialized) return;
      form.dataset.allocationInitialized = 'true';
      const inputs = [...form.querySelectorAll('[data-payment-allocation]')];
      const cents = value => {
        const match = String(value).trim().replace(',', '.').match(/^(\d*)(?:\.(\d{0,2}))?$/);
        return match ? BigInt(match[1] || '0') * 100n + BigInt((match[2] || '').padEnd(2, '0')) : 0n;
      };
      const money = value => `${(value / 100n).toLocaleString('ru-RU')},${String(value % 100n).padStart(2, '0')}`;
      function update() {
        let total = 0n;
        inputs.forEach(input => {
          const amount = cents(input.value);
          total += amount;
        });
        form.querySelector('[data-payment-total]').textContent = money(total);
      }
      inputs.forEach(input => {
        const placeholder = input.getAttribute('placeholder') || '';
        let selectOnMouseUp = false;
        input.addEventListener('mousedown', () => {
          selectOnMouseUp = document.activeElement !== input;
        });
        input.addEventListener('focus', () => {
          input.setAttribute('placeholder', '');
          if (input.value.trim() !== '' && Number(input.value.replace(',', '.')) === 0) {
            input.value = '';
            update();
          } else {
            input.select();
          }
        });
        input.addEventListener('mouseup', event => {
          if (selectOnMouseUp && input.value !== '') {
            event.preventDefault();
            input.select();
          }
          selectOnMouseUp = false;
        });
        input.addEventListener('blur', () => {
          input.setAttribute('placeholder', placeholder);
          if (input.value === '' && !input.validity.badInput) input.value = '0';
          selectOnMouseUp = false;
          update();
        });
        input.addEventListener('input', update);
      });
      update();
    });
  };
  document.addEventListener('DOMContentLoaded', () => {
    A.initDistribution();
    A.initPaymentAllocation();
  });
})(window.Admin);
