const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

function setup(values) {
  const inputs = values.map(value => ({
    value, placeholder: '0', validity: { badInput: false }, events: {}, selected: 0,
    getAttribute() { return this.placeholder; },
    setAttribute(name, value) { this.placeholder = value; },
    addEventListener(name, callback) { this.events[name] = callback; },
    select() { this.selected += 1; },
  }));
  const total = { textContent: '' };
  const form = { dataset: {}, querySelectorAll: () => inputs, querySelector: () => total };
  const document = { activeElement: null, addEventListener() {} };
  const window = { Admin: {} };
  runInNewContext(readFileSync(resolve(__dirname, '../../static/js/distribution.js'), 'utf8'), { window, document });
  const root = { querySelectorAll: () => [form] };
  window.Admin.initPaymentAllocation(root);
  return { inputs, total, document, root, window };
}

test('zero disappears on focus and returns when left empty', () => {
  const { inputs, total } = setup(['0.00']);
  inputs[0].events.focus();
  assert.equal(inputs[0].value, '');
  assert.equal(inputs[0].placeholder, '');
  assert.equal(total.textContent, '0,00');
  inputs[0].events.blur();
  assert.equal(inputs[0].value, '0');
  assert.equal(inputs[0].placeholder, '0');
});

test('nonzero amount is selected on focus and first mouseup', () => {
  const { inputs, document } = setup(['123.45']);
  const input = inputs[0];
  input.events.mousedown();
  document.activeElement = input;
  input.events.focus();
  let prevented = false;
  input.events.mouseup({ preventDefault() { prevented = true; } });
  assert.equal(input.selected, 2);
  assert.equal(prevented, true);
  assert.equal(input.value, '123.45');
  input.events.mousedown();
  input.events.mouseup({ preventDefault() { assert.fail('Repeated click should position the caret'); } });
});

test('edited values update the displayed total exactly', () => {
  const { inputs, total } = setup(['0.1', '0.2']);
  assert.equal(total.textContent, '0,30');
  inputs[0].value = '1234.56';
  inputs[0].events.input();
  assert.equal(total.textContent.replace(/\s/g, ''), '1234,76');
});

test('invalid numeric input is not replaced on blur', () => {
  const { inputs } = setup(['']);
  inputs[0].validity.badInput = true;
  inputs[0].events.blur();
  assert.equal(inputs[0].value, '');
});

test('initialization is idempotent', () => {
  const { inputs, window, root } = setup(['5']);
  const originalFocus = inputs[0].events.focus;
  window.Admin.initPaymentAllocation(root);
  assert.equal(inputs[0].events.focus, originalFocus);
});

test('totals stay exact beyond JavaScript Number integer precision', () => {
  const { total } = setup(['900719925474099.91', '0.09']);
  assert.equal(total.textContent.replace(/\s/g, ''), '900719925474100,00');
});

test('comma decimals and empty categories are supported', () => {
  const { inputs, total } = setup(['1,23', '', '0']);
  assert.equal(total.textContent, '1,23');
  inputs[0].value = '';
  inputs[0].events.input();
  assert.equal(total.textContent, '0,00');
});

test('zero entered with comma clears on focus too', () => {
  const { inputs } = setup(['0,00']);
  inputs[0].events.focus();
  assert.equal(inputs[0].value, '');
});
