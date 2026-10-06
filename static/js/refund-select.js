(function (A) {
  'use strict';

  A.initRefundSelect = function (root = document) {
    root.querySelectorAll('select[data-searchable-select]').forEach(select => {
      if (select.dataset.initialized) return;
      select.dataset.initialized = 'true';
      const wrapper = document.createElement('div');
      wrapper.className = 'searchable-select';
      const input = document.createElement('input');
      input.type = 'search';
      input.className = 'form-control';
      input.placeholder = select.options[0]?.textContent || 'Выберите ДБЗ';
      input.autocomplete = 'off';
      const menu = document.createElement('div');
      menu.className = 'searchable-select__menu';
      menu.hidden = true;
      const options = Array.from(select.options).filter(option => option.value).map(option => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'searchable-select__option';
        item.textContent = option.textContent;
        item.dataset.searchText = option.textContent.toLowerCase();
        item.addEventListener('click', () => {
          select.value = option.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          input.value = option.textContent;
          menu.hidden = true;
        });
        menu.append(item);
        return { item, option };
      });
      const filter = () => {
        const query = input.value.trim().toLowerCase();
        menu.hidden = false;
        options.forEach(({ item }) => { item.hidden = query && !item.dataset.searchText.includes(query); });
      };
      input.addEventListener('focus', filter);
      input.addEventListener('input', filter);
      document.addEventListener('click', event => {
        if (!wrapper.contains(event.target)) menu.hidden = true;
      });
      const selected = select.options[select.selectedIndex];
      if (selected && selected.value) input.value = selected.textContent;
      select.hidden = true;
      select.parentNode.insertBefore(wrapper, select);
      wrapper.append(input, menu);
    });

    root.querySelectorAll('select[data-multi-select]').forEach(select => {
      if (select.dataset.initialized) return;
      select.dataset.initialized = 'true';

      const wrapper = document.createElement('div');
      wrapper.className = 'multi-select';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'form-control multi-select__trigger';
      button.setAttribute('aria-haspopup', 'listbox');
      button.setAttribute('aria-expanded', 'false');
      const menu = document.createElement('div');
      menu.className = 'multi-select__menu';
      menu.hidden = true;

      const update = () => {
        const selected = Array.from(select.options).filter(option => option.selected);
        button.textContent = selected.length ? `${selected.length} выбрано` : 'Выберите платежи';
        button.classList.toggle('is-empty', !selected.length);
      };
      Array.from(select.options).forEach((option, index) => {
        const label = document.createElement('label');
        label.className = 'multi-select__option';
        label.dataset.optionValue = option.value;
        label.dataset.debtId = option.dataset.debtId || '';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = option.selected;
        checkbox.value = option.value;
        checkbox.addEventListener('change', () => {
          option.selected = checkbox.checked;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          update();
        });
        label.append(checkbox, document.createTextNode(option.textContent));
        menu.append(label);
      });
      button.addEventListener('click', () => {
        menu.hidden = !menu.hidden;
        button.setAttribute('aria-expanded', String(!menu.hidden));
      });
      document.addEventListener('click', event => {
        if (!wrapper.contains(event.target)) {
          menu.hidden = true;
          button.setAttribute('aria-expanded', 'false');
        }
      });
      select.hidden = true;
      select.parentNode.insertBefore(wrapper, select);
      wrapper.append(button, menu);
      update();

      const debtSelect = root.querySelector('select[name="debt"]');
      const filterPayments = () => {
        const debtId = debtSelect?.value || '';
        Array.from(select.options).forEach(option => {
          const visible = !debtId || option.dataset.debtId === debtId;
          option.hidden = !visible;
          if (!visible) option.selected = false;
          const item = menu.querySelector(`[data-option-value="${CSS.escape(option.value)}"]`);
          if (item) {
            item.hidden = !visible;
            item.querySelector('input').checked = option.selected;
          }
        });
        update();
      };
      debtSelect?.addEventListener('change', filterPayments);
      filterPayments();
    });
  };

  document.addEventListener('DOMContentLoaded', () => A.initRefundSelect());
})(window.Admin = window.Admin || {});
