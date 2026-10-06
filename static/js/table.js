/* Reusable client-side table: sorting, filters, selection, columns and CSV.
 * Pass a different getRows callback / columns array to reuse it for other data.
 * This demo's mutations are handled by the separate Admin.users controller.
 */
(function (A) {
  'use strict';
  const escape = A.escape;
  const defaultColumns = [
    { key: 'id', label: 'ID', render: row => '<span class="font-mono text-muted">' + row.id + '</span>' },
    { key: 'name', label: 'Employee', render: row => '<div class="person-cell">' + A.avatar(row.name, row.id, 'avatar-sm') + '<div><strong>' + escape(row.name) + '</strong><small>' + escape(row.role) + '</small></div></div>' },
    { key: 'email', label: 'Email', render: row => '<span class="text-secondary">' + escape(row.email) + '</span>' },
    { key: 'department', label: 'Department', render: row => escape(row.department) },
    { key: 'status', label: 'Status', render: row => A.statusBadge(row.status) },
    { key: 'created', label: 'Created', render: row => '<span class="text-secondary">' + escape(A.formatDate(row.created)) + '</span>' }
  ];
  const tables = new Map();
  class DataTable {
    constructor(element, options = {}) {
      this.element = element;
      this.id = A.uid('table');
      this.columns = options.columns || defaultColumns;
      this.getRows = options.getRows || A.data.users;
      this.page = 1;
      this.pageSize = Number(element.dataset.tableSize) || 10;
      this.sort = { key: 'id', direction: 'asc' };
      this.selected = new Set();
      this.hiddenColumns = new Set((element.dataset.hideColumns || '').split(',').filter(Boolean));
      const query = new URLSearchParams(location.search);
      this.filters = { q: query.get('q') || '', status: query.get('status') || '', department: query.get('department') || '', from: '', to: '' };
      this.renderShell(); this.bind(); this.refresh(); tables.set(this.id, this);
      document.addEventListener('demo:users-changed', () => this.refresh());
    }
    renderShell() {
      const icon = A.icon;
      const minimal = this.element.dataset.tableTools === 'minimal';
      this.element.innerHTML = `
        <div class="table-toolbar" ${minimal ? 'hidden' : ''}>
          <div class="input-icon">${icon('search')}<input type="search" class="form-control" data-search aria-label="Search employees" placeholder="Search employees..." value="${escape(this.filters.q)}"></div>
          <select class="form-control" data-status aria-label="Filter by status"><option value="">All statuses</option><option value="active">Active</option><option value="pending">Pending</option><option value="inactive">Inactive</option><option value="blocked">Blocked</option></select>
          <button class="btn" data-filter-toggle aria-expanded="false" aria-controls="${this.id}-filters">${icon('filter')}<span data-filter-label>Filters</span></button>
          <span class="toolbar-spacer"></span>
          <button class="btn btn-icon" data-refresh aria-label="Refresh table" title="Refresh local data">${icon('refresh')}</button>
          <div class="dropdown"><button class="btn btn-icon" data-dropdown data-align="end" aria-expanded="false" aria-controls="${this.id}-columns" aria-label="Choose visible columns" title="Columns">${icon('columns')}</button>
            <div class="dropdown-menu column-menu" id="${this.id}-columns" data-table-owner="${this.id}" hidden><div class="dropdown-heading">Visible columns</div>${this.columns.map(column => `<label class="check"><input type="checkbox" data-column="${column.key}" ${this.hiddenColumns.has(column.key) ? '' : 'checked'} ${column.key === 'name' ? 'disabled' : ''}>${column.label}</label>`).join('')}</div>
          </div>
          <button class="btn" data-export>${icon('download')} Export</button>
          <button class="btn btn-primary" data-user-add>${icon('plus')} Add employee</button>
        </div>
        <div class="table-advanced" id="${this.id}-filters" hidden>
          <label class="form-field"><span class="form-label">Department</span><select class="form-control" data-department><option value="">All departments</option>${A.data.departments.map(value => `<option>${value}</option>`).join('')}</select></label>
          <label class="form-field"><span class="form-label">Created from</span><input class="form-control" type="date" data-date-from aria-label="Created from"></label>
          <label class="form-field"><span class="form-label">Created to</span><input class="form-control" type="date" data-date-to aria-label="Created to"></label>
          <button class="btn btn-primary" data-apply>Apply filters</button><button class="btn" data-reset>Reset all</button>
        </div>
        <div class="selection-bar" hidden><strong data-selected-count></strong><span class="text-xs">selected across pages</span><button class="btn btn-sm" data-bulk="active">Activate</button><button class="btn btn-sm" data-bulk="inactive">Deactivate</button><button class="btn btn-sm btn-outline-danger" data-bulk="delete">Delete</button><button class="btn btn-sm btn-ghost ml-auto" data-clear-selection>Clear</button></div>
        <div class="table-container" tabindex="0" role="region" aria-label="Employee directory table"><table class="table table-bordered table-compact"><caption class="sr-only">Employee directory. Sort using column headers; select rows using checkboxes.</caption><thead></thead><tbody></tbody></table></div>
        <div class="table-footer"><div class="flex items-center gap-3"><label class="rows-control">Rows per page <select class="form-control" data-page-size>${[5, 10, 25, 50].map(size => `<option ${size === this.pageSize ? 'selected' : ''}>${size}</option>`).join('')}</select></label><span class="table-result-info" role="status" aria-live="polite"></span></div><nav class="pagination" aria-label="Employee table pages"></nav></div>`;
      A.$('[data-status]', this.element).value = this.filters.status;
      A.$('[data-department]', this.element).value = this.filters.department;
    }
    bind() {
      let debounce;
      this.element.addEventListener('input', event => {
        if (!event.target.matches('[data-search]')) return;
        clearTimeout(debounce);
        debounce = setTimeout(() => { this.filters.q = event.target.value; this.page = 1; this.render(); }, 140);
      });
      this.element.addEventListener('change', event => {
        const target = event.target;
        if (target.matches('[data-status]')) { this.filters.status = target.value; this.page = 1; this.render(); }
        if (target.matches('[data-page-size]')) { this.pageSize = Number(target.value); this.page = 1; this.render(); }
        if (target.matches('[data-select-row]')) {
          const id = Number(target.dataset.selectRow);
          if (target.checked) this.selected.add(id); else this.selected.delete(id);
          this.syncSelection();
        }
        if (target.matches('[data-select-all]')) {
          this.visibleRows.forEach(row => target.checked ? this.selected.add(row.id) : this.selected.delete(row.id));
          this.syncSelection();
        }
      });
      this.element.addEventListener('click', async event => {
        const target = event.target.closest('button');
        if (!target) return;
        if (target.hasAttribute('data-sort')) {
          const key = target.dataset.sort;
          this.sort = { key, direction: this.sort.key === key && this.sort.direction === 'asc' ? 'desc' : 'asc' }; this.render();
        }
        if (target.hasAttribute('data-page')) { this.page = Number(target.dataset.page); this.render(); }
        if (target.hasAttribute('data-filter-toggle')) {
          const filters = A.$('.table-advanced', this.element); filters.hidden = !filters.hidden;
          target.setAttribute('aria-expanded', String(!filters.hidden));
        }
        if (target.hasAttribute('data-apply')) {
          const from = A.$('[data-date-from]', this.element).value;
          const to = A.$('[data-date-to]', this.element).value;
          if (from && to && from > to) { A.notify('error', 'Invalid range', 'The start date must be before the end date.'); return; }
          this.filters.department = A.$('[data-department]', this.element).value;
          this.filters.from = from; this.filters.to = to; this.page = 1; this.render();
        }
        if (target.hasAttribute('data-reset')) this.resetFilters();
        if (target.hasAttribute('data-refresh')) { this.refresh(); A.notify('info', 'Table refreshed', 'Showing the latest browser-local demo data.'); }
        if (target.hasAttribute('data-export')) this.export();
        if (target.hasAttribute('data-clear-selection')) { this.selected.clear(); this.syncSelection(); }
        if (target.hasAttribute('data-row-action')) {
          const id = Number(target.dataset.id);
          if (target.dataset.rowAction === 'view') A.users.view(id);
          if (target.dataset.rowAction === 'edit') A.users.edit(id);
          if (target.dataset.rowAction === 'delete') A.users.remove([id]);
        }
        if (target.hasAttribute('data-bulk')) {
          if (target.dataset.bulk === 'delete') A.users.remove([...this.selected]);
          else {
            const next = target.dataset.bulk;
            A.data.saveUsers(this.getRows().map(row => this.selected.has(row.id) ? { ...row, status: next } : row), 'Changed employee status', this.selected.size + ' employees');
            A.notify('success', 'Status updated', this.selected.size + ' employees changed to ' + next + '.');
          }
        }
      });
    }
    refresh() {
      this.rows = this.getRows();
      const existing = new Set(this.rows.map(row => row.id));
      this.selected.forEach(id => { if (!existing.has(id)) this.selected.delete(id); });
      this.render();
    }
    resetFilters() {
      this.filters = { q: '', status: '', department: '', from: '', to: '' };
      ['[data-search]', '[data-status]', '[data-department]', '[data-date-from]', '[data-date-to]'].forEach(selector => { A.$(selector, this.element).value = ''; });
      this.page = 1; this.render();
    }
    filtered() {
      const { q, status, department, from, to } = this.filters;
      const query = q.trim().toLocaleLowerCase();
      const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });
      return this.rows.filter(row => (!query || [row.name, row.email, row.id, row.role].join(' ').toLocaleLowerCase().includes(query)) && (!status || row.status === status) && (!department || row.department === department) && (!from || row.created >= from) && (!to || row.created <= to))
        .sort((left, right) => collator.compare(String(left[this.sort.key]), String(right[this.sort.key])) * (this.sort.direction === 'asc' ? 1 : -1));
    }
    render() {
      const filtered = this.filtered();
      const totalPages = Math.max(1, Math.ceil(filtered.length / this.pageSize));
      this.page = Math.min(this.page, totalPages);
      const start = (this.page - 1) * this.pageSize;
      this.visibleRows = filtered.slice(start, start + this.pageSize);
      const columns = this.columns.filter(column => !this.hiddenColumns.has(column.key));
      const activeCount = ['department', 'from', 'to'].filter(key => this.filters[key]).length;
      A.$('[data-filter-label]', this.element).textContent = 'Filters' + (activeCount ? ' (' + activeCount + ')' : '');
      A.$('[data-filter-toggle]', this.element).classList.toggle('btn-outline-primary', activeCount > 0);
      A.$('thead', this.element).innerHTML = `<tr><th scope="col" class="check-cell"><input type="checkbox" data-select-all aria-label="Select all rows on this page" ${!this.visibleRows.length ? 'disabled' : ''}></th>${columns.map(column => `<th scope="col" aria-sort="${this.sort.key === column.key ? (this.sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}"><button class="sort-button" data-sort="${column.key}">${column.label}${A.icon('sort')}</button></th>`).join('')}<th scope="col" class="text-right">Actions</th></tr>`;
      A.$('tbody', this.element).innerHTML = this.visibleRows.length ? this.visibleRows.map(row => `<tr data-row-id="${row.id}"><td class="check-cell"><input type="checkbox" data-select-row="${row.id}" aria-label="Select ${escape(row.name)}"></td>${columns.map(column => `<td>${column.render ? column.render(row) : escape(row[column.key])}</td>`).join('')}<td><div class="row-actions">${[['view','eye','View'],['edit','edit','Edit'],['delete','trash','Delete']].map(([action, icon, label]) => `<button class="btn btn-sm btn-icon btn-ghost ${action === 'delete' ? 'text-danger' : ''}" data-row-action="${action}" data-id="${row.id}" title="${label}" aria-label="${label} ${escape(row.name)}">${A.icon(icon)}</button>`).join('')}</div></td></tr>`).join('') : `<tr><td colspan="${columns.length + 2}"><div class="empty-state">${A.icon('search')}<h3>No employees found</h3><p>Try a different search or clear the current filters.</p><button class="btn btn-sm" data-reset>Reset filters</button></div></td></tr>`;
      A.$('.table-result-info', this.element).textContent = (filtered.length ? start + 1 : 0) + '\u2013' + Math.min(start + this.pageSize, filtered.length) + ' of ' + filtered.length;
      const buttons = [];
      buttons.push(`<button class="page-btn" data-page="${this.page - 1}" ${this.page === 1 ? 'disabled' : ''} aria-label="Previous page">${A.icon('chevron-left')}</button>`);
      for (let page = 1; page <= totalPages; page++) {
        if (page === 1 || page === totalPages || Math.abs(page - this.page) <= 1) buttons.push(`<button class="page-btn" data-page="${page}" ${page === this.page ? 'aria-current="page"' : ''} aria-label="Page ${page}">${page}</button>`);
        else if (page === 2 || page === totalPages - 1) buttons.push('<span class="page-ellipsis" aria-hidden="true">...</span>');
      }
      buttons.push(`<button class="page-btn" data-page="${this.page + 1}" ${this.page === totalPages ? 'disabled' : ''} aria-label="Next page">${A.icon('chevron-right')}</button>`);
      A.$('.pagination', this.element).innerHTML = buttons.join('');
      this.syncSelection();
    }
    syncSelection() {
      const count = this.selected.size;
      A.$('.selection-bar', this.element).hidden = !count;
      A.$('[data-selected-count]', this.element).textContent = count;
      A.$$('[data-select-row]', this.element).forEach(checkbox => {
        checkbox.checked = this.selected.has(Number(checkbox.dataset.selectRow));
        checkbox.closest('tr').classList.toggle('is-selected', checkbox.checked);
      });
      const selectedVisible = this.visibleRows.filter(row => this.selected.has(row.id)).length;
      const all = A.$('[data-select-all]', this.element);
      all.checked = this.visibleRows.length > 0 && selectedVisible === this.visibleRows.length;
      all.indeterminate = selectedVisible > 0 && selectedVisible < this.visibleRows.length;
    }
    export() {
      const columns = this.columns.filter(column => !this.hiddenColumns.has(column.key));
      A.downloadCSV('employees.csv', columns.map(column => column.label), this.filtered().map(row => columns.map(column => row[column.key])));
      A.data.log('Exported employees', this.filtered().length + ' rows');
    }
  }
  A.DataTable = DataTable;
  A.tables = tables;
  A.initTables = function () {
    A.$$('[data-datatable]').forEach(element => new DataTable(element));
    document.addEventListener('change', event => {
      if (!event.target.matches('[data-column]')) return;
      const menu = event.target.closest('[data-table-owner]');
      if (!menu) return;
      const table = tables.get(menu.dataset.tableOwner);
      if (!table) return;
      if (event.target.checked) table.hiddenColumns.delete(event.target.dataset.column); else table.hiddenColumns.add(event.target.dataset.column);
      table.render();
    });
  };
})(window.Admin);
