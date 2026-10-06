const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

async function poll(fetchResult) {
  const notices = [], timers = [], tbody = { innerHTML: 'processing' };
  const table = {
    dataset: { importStatusUrl: '/imports/status/' },
    querySelector(selector) { return selector === 'tbody' ? tbody : {}; },
  };
  let start;
  const document = {
    getElementById() { return null; },
    querySelector(selector) { return selector === '[data-import-status-url]' ? table : null; },
    addEventListener(name, callback) { if (name === 'DOMContentLoaded') start = callback; },
  };
  runInNewContext(readFileSync(resolve(__dirname, '../../static/js/imports.js'), 'utf8'), {
    document, window: { Admin: { notify: (...args) => notices.push(args) } },
    performance: { getEntriesByType: () => [] },
    location: { href: 'https://payments.test/imports/', search: '' }, URL,
    fetch: fetchResult, setTimeout: callback => timers.push(callback), clearTimeout() {},
  });
  start();
  await new Promise(resolve => setImmediate(resolve));
  return { notices, timers, tbody };
}

test('failed import status updates the table without a redundant error alert', async () => {
  const result = await poll(async () => ({ ok: true, json: async () => ({
    html: '<tr data-import-status="failed">Ошибка</tr>', pending: false,
  }) }));
  assert.match(result.tbody.innerHTML, /failed/);
  assert.equal(result.notices.length, 0);
  assert.equal(result.timers.length, 0);
});

test('background status connection failures retry without accumulating alerts', async () => {
  const result = await poll(async () => { throw new Error('offline'); });
  assert.equal(result.notices.length, 0);
  assert.equal(result.timers.length, 1);
  assert.equal(result.tbody.innerHTML, 'processing');
});
