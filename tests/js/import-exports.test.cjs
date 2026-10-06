const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

const flush = () => new Promise(setImmediate);
function setup(replies, saved = []) {
  const events = {}, timers = [], notices = [], calls = [], downloads = [];
  const links = [];
  let observe;
  let storage = JSON.stringify(saved);
  const document = {
    body: { dataset: { userId: '7' }, append() {} },
    addEventListener(name, callback) { events[name] = callback; },
    querySelectorAll: () => links,
    createElement() { return { click() { downloads.push(this.href); }, remove() {} }; },
  };
  const window = { Admin: { notify(type, title, message, duration) {
    const notice = { type, title, message, duration, removed: false };
    notices.push(notice);
    const remove = () => { notice.removed = true; };
    remove.update = (title, message) => Object.assign(notice, { title, message });
    return remove;
  } } };
  const sessionStorage = {
    getItem() { return storage; }, setItem(key, value) { storage = value; },
  };
  const fetch = async (url, options) => {
    calls.push({ url, options });
    const reply = replies.shift();
    if (reply instanceof Error) throw reply;
    assert.ok(reply, 'unexpected request');
    return { ok: true, status: 200, headers: { get: () => 'application/json' },
      json: async () => reply, ...reply.response };
  };
  runInNewContext(readFileSync(resolve(__dirname, '../../static/js/import-exports.js'), 'utf8'),
    { window, document, sessionStorage, fetch, URL, TypeError,
      MutationObserver: class { constructor(callback) { observe = callback; } observe() {} },
      location: { origin: 'https://payments.test' }, setTimeout: callback => timers.push(callback) });
  const link = { href: 'https://payments.test/imports/1/download/?with_errors=1', attributes: {},
    getAttribute(name) { return this.attributes[name]; },
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; } };
  links.push(link);
  const click = (options = {}) => events.click({ button: 0, preventDefault() {}, target: { closest: () => link }, ...options });
  return { events, timers, notices, calls, downloads, click, link, links, observe: () => observe(), storage: () => JSON.parse(storage) };
}

test('download shows an inline progress alert and stays disabled until the file is ready', async () => {
  const state = setup([
    { job_id: 'job', status_url: '/imports/exports/job/status/' },
    { status: 'processing', progress: 42, stage: 'Запись строк' },
    { status: 'completed', progress: 100, download_url: '/imports/exports/job/file/' },
  ]);
  await state.click();
  await flush();
  assert.equal(state.calls[0].options.headers['X-Import-Export'], '1');
  assert.equal(state.notices[0].message, 'Запись строк — 42%');
  assert.equal(state.link.attributes['aria-disabled'], 'true');
  assert.equal(state.link.attributes['aria-busy'], 'true');
  await state.click({ ctrlKey: true });
  await state.click();
  assert.equal(state.calls.length, 2);
  assert.equal(state.storage().length, 1);
  state.timers.shift()();
  await flush();
  assert.deepEqual(state.downloads, ['https://payments.test/imports/exports/job/file/']);
  assert.deepEqual(state.storage(), []);
  assert.equal(state.notices.length, 1);
  assert.equal(state.notices[0].removed, true);
  assert.equal(state.link.attributes['aria-disabled'], undefined);
  assert.equal(state.link.attributes['aria-busy'], undefined);
});

test('navigation restores monitoring of the same background job', async () => {
  const state = setup([{ status: 'processing', progress: 95, stage: 'Упаковка XLSX' }],
    [{ id: 'saved', url: '/imports/exports/saved/status/', sourceURL: '/imports/1/download/?with_errors=1' }]);
  state.events.DOMContentLoaded();
  await flush();
  assert.equal(state.calls.length, 1);
  assert.equal(state.notices[0].message, 'Упаковка XLSX — 95%');
  assert.equal(state.link.attributes['aria-disabled'], 'true');
  assert.equal(state.storage()[0].id, 'saved');
});

test('temporary network failure retries without losing the job', async () => {
  const state = setup([new TypeError('network unavailable'),
    { status: 'processing', progress: 51, stage: 'Запись строк' }],
    [{ id: 'saved', url: '/imports/exports/saved/status/' }]);
  state.events.DOMContentLoaded();
  await flush();
  assert.equal(state.storage().length, 1);
  state.timers.shift()();
  await flush();
  assert.equal(state.notices[0].message, 'Запись строк — 51%');
});

test('worker error stops monitoring, shows an error and re-enables downloading', async () => {
  const state = setup([{ status: 'failed', error: 'Не удалось подготовить файл.' }],
    [{ id: 'saved', url: '/imports/exports/saved/status/', sourceURL: '/imports/1/download/?with_errors=1' }]);
  state.events.DOMContentLoaded();
  await flush();
  assert.deepEqual(state.storage(), []);
  assert.equal(state.notices.at(-1).type, 'error');
  assert.equal(state.downloads.length, 0);
  assert.equal(state.timers.length, 0);
  assert.equal(state.notices[0].removed, true);
  assert.equal(state.link.attributes['aria-disabled'], undefined);
});

test('queueing failure only shows the actual error and restores the download button', async () => {
  const state = setup([{ error: 'Нет доступа.', response: { ok: false, status: 403 } }]);
  await state.click();
  await flush();
  assert.equal(state.link.attributes['aria-disabled'], undefined);
  assert.equal(state.notices.length, 1);
  assert.equal(state.notices.at(-1).type, 'error');
  assert.deepEqual(state.storage(), []);
});

test('cached file downloads immediately without any alert or status polling', async () => {
  const state = setup([{ job_id: 'cached', status: 'completed',
    status_url: '/imports/exports/cached/status/', download_url: '/imports/exports/cached/file/' }]);
  await state.click();
  await flush();
  assert.deepEqual(state.downloads, ['https://payments.test/imports/exports/cached/file/']);
  assert.equal(state.notices.length, 0);
  assert.equal(state.calls.length, 1);
  assert.equal(state.timers.length, 0);
  assert.deepEqual(state.storage(), []);
  assert.equal(state.link.attributes['aria-disabled'], undefined);
});

test('a replacement modal download button also stays disabled while preparation continues', async () => {
  const state = setup([
    { job_id: 'job', status_url: '/imports/exports/job/status/' },
    { status: 'processing', progress: 42, stage: 'Запись строк' },
  ]);
  await state.click();
  await flush();
  const replacement = { ...state.link, attributes: {} };
  state.links.splice(0, 1, replacement);
  state.observe();
  assert.equal(replacement.attributes['aria-disabled'], 'true');
  assert.equal(replacement.attributes['aria-busy'], 'true');
});
