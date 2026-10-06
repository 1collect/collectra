(function (A) {
  'use strict';

  A.initRefundSelect = function (root = document) {
    root.querySelectorAll('select[data-multi-select]').forEach(select => {
      if (select.dataset.initialized) return;
      select.dataset.initialized = 'true';
      const debt = select.form.querySelector('select[name="debt"]');
      const wrapper = document.createElement('div');
      wrapper.className = 'multi-select';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'form-control multi-select__trigger';
      button.id = select.id + '-trigger';
      button.setAttribute('aria-expanded', 'false');
      const label = select.form.querySelector(`label[for="${select.id}"]`);
      if (label) label.htmlFor = button.id;
      const menu = document.createElement('div');
      menu.className = 'multi-select__menu';
      menu.hidden = true;
      const rows = Array.from(select.options).map(option => {
        const row = document.createElement('label');
        row.className = 'multi-select__option';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = option.selected;
        row.append(checkbox, document.createTextNode(option.textContent));
        checkbox.addEventListener('change', () => {
          option.selected = checkbox.checked;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          update();
        });
        menu.append(row);
        return { option, row, checkbox };
      });
      function update() {
        const selected = rows.filter(({ option }) => option.selected);
        button.textContent = selected.length === 1 ? selected[0].option.textContent : selected.length ? `Выбрано платежей: ${selected.length}` : 'Выберите платежи';
      }
      function close() {
        menu.hidden = true;
        button.setAttribute('aria-expanded', 'false');
      }
      function sync() {
        rows.forEach(({ option, row, checkbox }) => {
          row.hidden = !debt.value || option.dataset.debtId !== debt.value;
          if (row.hidden) option.selected = false;
          checkbox.checked = option.selected;
        });
        update();
        const available = rows.some(({ row }) => !row.hidden);
        button.disabled = !debt.value || !available;
        if (!debt.value) button.textContent = 'Сначала выберите ДБЗ';
        else if (!available) button.textContent = 'Нет доступных платежей';
        close();
      }
      button.addEventListener('click', () => {
        menu.hidden = !menu.hidden;
        button.setAttribute('aria-expanded', String(!menu.hidden));
      });
      wrapper.addEventListener('keydown', event => {
        if (event.key === 'Escape') { close(); button.focus(); }
      });
      document.addEventListener('click', event => {
        if (!wrapper.contains(event.target)) close();
      });
      select.hidden = true;
      select.parentNode.insertBefore(wrapper, select);
      wrapper.append(button, menu);
      debt.addEventListener('change', sync);
      sync();
    });
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
      const label = root.querySelector(`label[for="${select.id}"]`);
      input.id = select.id + '-search';
      if (label) label.htmlFor = input.id;
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
      input.addEventListener('input', () => {
        if (select.value) {
          select.value = '';
          select.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      input.addEventListener('keydown', event => {
        if (event.key === 'Escape') menu.hidden = true;
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          filter();
          options.find(({ item }) => !item.hidden)?.item.focus();
        }
      });
      document.addEventListener('click', event => {
        if (!wrapper.contains(event.target)) menu.hidden = true;
      });
      const selected = select.options[select.selectedIndex];
      if (selected && selected.value) input.value = selected.textContent;
      select.hidden = true;
      select.parentNode.insertBefore(wrapper, select);
      wrapper.append(input, menu);
    });

  };

  document.addEventListener('DOMContentLoaded', () => A.initRefundSelect());
})(window.Admin = window.Admin || {});
