const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
  function field(value) {
    const handlers = {};
    return { value, dataset: {}, addEventListener: (event, handler) => { handlers[event] = handler; },
      change() { handlers.change(); } };
  }
  const fields = { id_kind: field('payments'), id_contract_mode: field('unique'),
    id_dbz: field('DBZ-1'), id_count: field('10') };
  fields.id_count.dataset.minimumErrorRows = '55';
  const elements = Object.fromEntries(['contract-mode', 'dbz-label', 'dbz-help', 'count-help']
    .map(name => [`[data-${name}]`, {}]));
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../static/js/import-generator.js'), 'utf8'), {
    document: { getElementById: id => fields[id], querySelector: selector => elements[selector] },
  });
  return { fields, elements };
}

test('contracts show mode selection and make DBZ an optional prefix', () => {
  const { fields, elements } = setup();
  assert.equal(fields.id_dbz.required, true);
  assert.equal(elements['[data-contract-mode]'].hidden, true);
  fields.id_kind.value = 'contracts';
  fields.id_kind.change();
  assert.equal(elements['[data-contract-mode]'].hidden, false);
  assert.equal(fields.id_dbz.required, false);
  assert.equal(elements['[data-dbz-label]'].textContent, 'Префикс ДБЗ');
  assert.equal(fields.id_count.min, '1');
});

test('error mode increases count to fit every scenario but preserves larger counts', () => {
  const { fields } = setup();
  fields.id_kind.value = 'contracts';
  fields.id_contract_mode.value = 'errors';
  fields.id_contract_mode.change();
  assert.equal(fields.id_count.min, '55');
  assert.equal(fields.id_count.value, '55');
  fields.id_count.value = '1000';
  fields.id_contract_mode.change();
  assert.equal(fields.id_count.value, '1000');
});

test('switching back to financial generators restores required existing DBZ', () => {
  const { fields, elements } = setup();
  fields.id_kind.value = 'contracts';
  fields.id_contract_mode.value = 'errors';
  fields.id_kind.change();
  fields.id_kind.value = 'expenses';
  fields.id_kind.change();
  assert.equal(fields.id_dbz.required, true);
  assert.equal(elements['[data-contract-mode]'].hidden, true);
  assert.equal(elements['[data-dbz-label]'].textContent, 'ДБЗ');
  assert.equal(fields.id_count.min, '1');
});
