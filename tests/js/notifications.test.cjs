const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

function setup() {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.events = {}; }
    append(...children) { children.forEach(child => { child.remove(); child.parentElement = this; this.children.push(child); }); }
    prepend(child) { child.remove(); child.parentElement = this; this.children.unshift(child); }
    remove() {
      if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this);
      this.parentElement = null;
    }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, callback) { this.events[name] = callback; }
  }
  class Dialog extends Element {
    constructor() { super('dialog'); this.body = new Element('div'); this.append(this.body); this.open = false; }
    querySelector() { return this.body; }
  }
  const main = new Element('main'), dialog = new Dialog(), events = {};
  const document = {
    body: main,
    getElementById: () => main,
    createElement: tag => new Element(tag),
    querySelectorAll: () => dialog.open ? [dialog] : [],
    addEventListener(name, callback) { events[name] = callback; },
  };
  const window = { Admin: {} };
  runInNewContext(readFileSync(resolve(__dirname, '../../static/js/notifications.js'), 'utf8'), {
    document, window, HTMLDialogElement: Dialog,
  });
  return { main, dialog, events, A: window.Admin };
}

test('feedback is an inline alert, uses safe text and has no toaster API', () => {
  const { main, A } = setup();
  A.notify('error', 'Ошибка', '<script>unsafe()</script>');
  assert.equal(A.toast, undefined);
  const region = main.children[0], notice = region.children[0];
  assert.equal(region.className, 'feedback-region');
  assert.equal(notice.className, 'alert alert-danger feedback-message');
  assert.equal(notice.attributes.role, 'alert');
  assert.equal(notice.children.length, 1);
  assert.equal(notice.children.some(child => child.tag === 'button'), false);
  assert.equal(notice.children[0].children[1].textContent, '<script>unsafe()</script>');
});

test('progress updates the same inline message and can be removed on completion', () => {
  const { main, A } = setup();
  const notice = A.notify('info', 'Подготовка отчёта', 'Ожидание — 0%', 0);
  notice.update('Подготовка отчёта', 'Запись строк — 45%');
  const region = main.children[0];
  assert.equal(region.children.length, 1);
  assert.equal(region.children[0].children[0].children[1].textContent, 'Запись строк — 45%');
  notice();
  assert.equal(region.children.length, 0);
});

test('feedback moves into the modal body and back to the page without floating overlays', () => {
  const { main, dialog, events, A } = setup();
  A.notify('warning', 'Нет связи', 'Повторяем запрос…');
  const region = main.children[0];
  dialog.open = true;
  events['modal:shown']();
  assert.equal(region.parentElement, dialog.body);
  dialog.open = false;
  events.close({ target: dialog });
  assert.equal(region.parentElement, main);
});
