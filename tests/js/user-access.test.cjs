const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
  function input(value, extraSelected = false) {
    const handlers = {};
    return { value, checked: false, disabled: false,
      dataset: { extraSelected: String(extraSelected) },
      addEventListener: (event, handler) => { handlers[event] = handler; },
      change() { handlers.change(); } };
  }
  const roles = [input('1'), input('2')];
  const permissions = [input('10'), input('20'), input('30', true)];
  const panel = { hidden: false };
  const form = {
    querySelector: () => panel,
    querySelectorAll: selector => selector.includes('"roles"') ? roles : permissions,
  };
  const events = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../static/js/user-access.js'), 'utf8'), {
    document: {
      querySelector: () => form,
      getElementById: () => ({ textContent: JSON.stringify({ 1: ['10'], 2: ['10', '20'] }) }),
    },
    window: { addEventListener: (event, handler) => { events[event] = handler; } },
  });
  return { roles, permissions, panel, events };
}

test('extra permissions stay hidden and disabled until a role is selected', () => {
  const { roles, permissions, panel } = setup();
  assert.equal(panel.hidden, true);
  assert.ok(permissions.every(input => input.disabled));
  roles[0].checked = true;
  roles[0].change();
  assert.equal(panel.hidden, false);
  assert.equal(permissions[0].checked, true);
  assert.equal(permissions[0].disabled, true);
  assert.equal(permissions[1].disabled, false);
  assert.equal(permissions[2].checked, true);
});

test('role union is locked and removing a role does not turn inherited rights into extras', () => {
  const { roles, permissions } = setup();
  roles.forEach(input => { input.checked = true; input.change(); });
  assert.ok(permissions.slice(0, 2).every(input => input.checked && input.disabled));
  roles[1].checked = false;
  roles[1].change();
  assert.equal(permissions[0].disabled, true);
  assert.equal(permissions[1].checked, false);
  assert.equal(permissions[1].disabled, false);
});

test('explicit extras survive role switches and can be deselected when not inherited', () => {
  const { roles, permissions, panel, events } = setup();
  roles[0].checked = true;
  roles[0].change();
  permissions[1].checked = true;
  permissions[1].change();
  roles[1].checked = true;
  roles[1].change();
  assert.equal(permissions[1].disabled, true);
  roles[1].checked = false;
  roles[1].change();
  assert.equal(permissions[1].checked, true);
  permissions[1].checked = false;
  permissions[1].change();
  events.pageshow();
  assert.equal(permissions[1].checked, false);
  roles[0].checked = false;
  roles[0].change();
  assert.equal(panel.hidden, true);
  assert.ok(permissions.every(input => input.disabled));
});
