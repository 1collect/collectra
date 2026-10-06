const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

const flush = () => new Promise(setImmediate);

function setup({ restored = false, reducedMotion = false, group = 'payment' } = {}) {
  const events = {}, attributes = {}, classes = {}, animations = [];
  let cancellations = 0;
  const bounds = () => ({ top: 0, bottom: 100, left: 0, right: 100 });
  const content = {
    getBoundingClientRect: bounds,
    animate(frames, options) {
      let finish, reject;
      const finished = new Promise((resolve, fail) => { finish = resolve; reject = fail; });
      const animation = { frames, options, finished, finish, cancel() { cancellations++; reject(new Error('cancelled')); } };
      animations.push(animation);
      return animation;
    },
  };
  const cell = { setAttribute(name, value) { attributes[name] = value; } };
  const button = { setAttribute() {}, closest: () => table };
  const table = {
    rows: [{ getBoundingClientRect: bounds, querySelectorAll: () => [content] }],
    closest: () => ({ getBoundingClientRect: bounds }),
    classList: {
      toggle(name, value) { classes[name] = value; },
      add(name) { classes[name] = true; },
      contains(name) { return classes[name] === true; },
    },
    querySelector: () => button,
    querySelectorAll(selector) {
      if (selector === `[data-${group}-column]`) return [cell];
      return [];
    },
  };
  const document = {
    querySelectorAll: () => [table],
    addEventListener(name, callback) { (events[name] ||= []).push(callback); },
  };
  runInNewContext(readFileSync(resolve(__dirname, '../../static/js/debt-purchase-columns.js'), 'utf8'), {
    document, performance: { getEntriesByType: () => [] },
    window: { matchMedia: () => ({ matches: reducedMotion }), Admin: { storage: {
      get: key => key === ({ payment: 'debtPaymentsExpanded', purchase: 'debtPurchaseExpanded', accrued: 'debtAccruedExpanded' })[group] && restored,
      set() {}, remove() {},
    } } },
  });
  const click = () => events.click.forEach(callback => callback({ target: {
    closest: selector => selector === `[data-${group}-toggle]` ? button : null,
  } }));
  return { events, click, animations, attributes, classes, cancellations: () => cancellations };
}

test('payments expand and finish collapsing before their columns are hidden', async () => {
  const state = setup();
  state.click();
  assert.equal(state.classes['is-payment-expanded'], true);
  assert.equal(state.attributes['aria-hidden'], 'false');
  assert.equal(state.animations.length, 1);
  assert.equal(state.animations[0].options.duration, 220);
  state.click();
  assert.equal(state.classes['is-payment-expanded'], true);
  assert.equal(state.attributes['aria-hidden'], 'true');
  assert.equal(state.animations.length, 2);
  assert.equal(state.animations[1].frames[0].opacity, 1);
  assert.equal(state.animations[1].frames[1].opacity, 0);
  state.animations[1].finish();
  await flush();
  assert.equal(state.classes['is-payment-expanded'], false);
  assert.equal(state.cancellations(), 2);
});

test('restoring expanded payments does not replay the animation', () => {
  const state = setup({ restored: true });
  state.events.DOMContentLoaded[0]();
  state.events['balances:updated'][0]();
  assert.equal(state.classes['is-payment-expanded'], true);
  assert.equal(state.animations.length, 0);
});

test('payment animation respects reduced motion preferences', () => {
  const state = setup({ reducedMotion: true });
  state.click();
  assert.equal(state.classes['is-payment-expanded'], true);
  assert.equal(state.animations.length, 0);
  state.click();
  assert.equal(state.classes['is-payment-expanded'], false);
});

for (const group of ['purchase', 'accrued']) {
  test(`${group} also animates collapse before hiding columns`, async () => {
    const state = setup({ group });
    state.click();
    state.animations[0].finish();
    await flush();
    state.click();
    assert.equal(state.classes[`is-${group}-expanded`], true);
    assert.equal(state.animations[1].frames[1].opacity, 0);
    state.animations[1].finish();
    await flush();
    assert.equal(state.classes[`is-${group}-expanded`], false);
  });
}

test('rapid reopen cancels collapse and cannot be hidden by its stale completion', async () => {
  const state = setup();
  state.click();
  state.click();
  const closing = state.animations[1];
  state.click();
  closing.finish();
  state.animations[2].finish();
  await flush();
  assert.equal(state.classes['is-payment-expanded'], true);
  assert.equal(state.attributes['aria-hidden'], 'false');
});

test('restoring during collapse cancels animation and applies saved closed state immediately', async () => {
  const state = setup();
  state.click();
  state.click();
  state.events['balances:updated'][0]();
  await flush();
  assert.equal(state.classes['is-payment-expanded'], false);
});
