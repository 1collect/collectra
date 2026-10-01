/* Shared helpers. All user-controlled text is escaped before HTML insertion. */
(function (A) {
  'use strict';
  A.$ = (selector, root = document) => root.querySelector(selector);
  A.$$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  A.escape = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  A.initials = name => String(name).trim().split(/\s+/).slice(0, 2).map(part => part[0] || '').join('').toUpperCase();
  A.avatar = (name, index = 0, size = '') => '<span class="avatar ' + size + ' tone-' + (Number(index) % 4) + '" aria-hidden="true">' + A.escape(A.initials(name)) + '</span>';
  A.formatDate = value => {
    const date = new Date(value.length === 10 ? value + 'T12:00:00' : value);
    return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(date);
  };
  let sequence = 0;
  A.uid = prefix => (prefix || 'component') + '-' + (++sequence);
  A.emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));
  const memory = new Map();
  A.storage = {
    available: true,
    get(key, fallback) {
      if (memory.has(key)) return memory.get(key);
      try {
        const raw = localStorage.getItem('circuit.' + key);
        if (raw !== null) return JSON.parse(raw);
      } catch (_) { A.storage.available = false; }
      return memory.has(key) ? memory.get(key) : fallback;
    },
    set(key, value) {
      try { localStorage.setItem('circuit.' + key, JSON.stringify(value)); memory.delete(key); return true; }
      catch (_) { memory.set(key, value); A.storage.available = false; return false; }
    },
    remove(key) {
      memory.delete(key);
      try { localStorage.removeItem('circuit.' + key); } catch (_) { A.storage.available = false; }
    }
  };
  A.copyText = async function (text) {
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
      else {
        const textarea = document.createElement('textarea');
        textarea.value = text; textarea.style.cssText = 'position:fixed;left:-9999px;top:0;';
        (document.querySelector('dialog[open]') || document.body).append(textarea);
        const previous = document.activeElement;
        textarea.select();
        const copied = document.execCommand('copy');
        textarea.remove(); if (previous) previous.focus();
        if (!copied) throw new Error('Clipboard is unavailable');
      }
      A.toast('success', 'Copied', 'The example is on your clipboard.');
      return true;
    } catch (_) {
      A.toast('warning', 'Clipboard unavailable', 'Select the visible code and copy it manually.');
      return false;
    }
  };
  A.downloadCSV = function (filename, headers, rows) {
    const cell = value => {
      let text = String(value == null ? '' : value);
      // Prevent spreadsheet formulas from executing when an exported CSV is opened.
      if (/^[\s\u0000-\u001f]*[=+@-]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    };
    const content = '\uFEFF' + [headers, ...rows].map(row => row.map(cell).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a'); link.href = url; link.download = filename;
    document.body.append(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 5000);
    A.toast('success', 'Export ready', rows.length + ' rows exported as CSV.');
  };
  A.pageHref = function (slug) {
    const base = document.body.dataset.base || './';
    return slug === 'dashboard' ? base + 'index.html' : base + 'pages/' + slug + '.html';
  };
  A.statusBadge = status => {
    const values = { active: ['success', 'Active'], pending: ['warning', 'Pending'], inactive: ['neutral', 'Inactive'], blocked: ['danger', 'Blocked'] };
    const [tone, label] = values[status] || ['neutral', status];
    return '<span class="badge badge-' + tone + '"><span class="status-dot"></span>' + A.escape(label) + '</span>';
  };
})(window.Admin = window.Admin || {});
