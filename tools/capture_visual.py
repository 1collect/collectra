"""Capture real Django pages. Requires playwright in the local environment."""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('stage')
parser.add_argument('--quick', action='store_true')
args = parser.parse_args()
out = Path('artifacts') / args.stage
out.mkdir(parents=True, exist_ok=True)
routes = {
    'users': '/users/', 'roles': '/users/roles/', 'groups': '/users/groups/',
    'permissions': '/users/permissions/', 'user-edit': '/users/1/edit/',
    'role-form': '/users/roles/new/', 'group-form': '/users/groups/new/',
    'contracts': '/imports/contracts/', 'payments': '/imports/payments/',
    'expenses': '/imports/expenses/', 'counterparties': '/imports/counterparties/',
    'counterparty-form': '/imports/counterparties/new/',
    'counterparty-delete': '/imports/counterparties/1/delete/',
    'refunds': '/imports/refunds/', 'refund-form': '/imports/refunds/new/',
    'imports': '/imports/', 'import-detail': '/imports/2/items/',
    'payment-edit': '/imports/payments/1/edit/', 'expense-edit': '/imports/expenses/1/edit/',
    'history': '/imports/payments/1/history/', 'empty-contracts': '/imports/contracts/?q=not-found',
    'empty-payments': '/imports/payments/?q=not-found',
    'counterparty-edit': '/imports/counterparties/1/edit/',
    'role-edit': '/users/roles/1/edit/', 'group-edit': '/users/groups/1/edit/',
    'empty-history': '/imports/payments/2/history/',
}
if args.quick:
    routes = {key: routes[key] for key in ['users', 'contracts', 'payments', 'imports', 'import-detail', 'refund-form', 'role-form', 'groups']}
sizes = {'wide': (1920, 1080), 'laptop': (1366, 900), 'narrow': (900, 900), 'mobile': (390, 844)}
results = []
with sync_playwright() as p:
    cached = sorted((Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright').glob('chromium-*/chrome-win64/chrome.exe'))
    browser = p.chromium.launch(**({'executable_path': str(cached[-1])} if cached else {}))
    context = browser.new_context(reduced_motion='reduce')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    base = 'http://127.0.0.1:8765'
    page.goto(base + '/login/')
    page.locator('[name=username]').fill('visual-review')
    page.locator('[name=password]').fill('visual-review-local')
    page.locator('main button[type=submit]').click()
    page.wait_for_url('**/users/')
    def capture(name):
        page.wait_for_timeout(220)
        page.screenshot(path=str(out / (name + '-viewport.png')))
        page.screenshot(path=str(out / (name + '.png')), full_page=not name.startswith('profile-menu'))
        metrics = page.evaluate('''() => ({width: innerWidth, scroll: document.documentElement.scrollWidth,
          smallText: [...document.querySelectorAll('main *')].filter(e => e.checkVisibility() && e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 12).length,
          title: document.title})''')
        results.append({'name': name, **metrics})
    for size, (width, height) in sizes.items():
        page.set_viewport_size({'width': width, 'height': height})
        for name, route in routes.items():
            response = page.goto(base + route)
            page.wait_for_timeout(120)
            if response.status >= 400:
                raise RuntimeError(f'{route}: HTTP {response.status}')
            capture(name + '-' + size)
        for name, route in [('contracts-scroll', '/imports/contracts/'), ('imports-scroll', '/imports/')]:
            page.goto(base + route)
            page.locator('.table-container').evaluate('(el) => {el.scrollLeft = el.scrollWidth}')
            capture(name + '-' + size)
        page.goto(base + '/imports/2/items/')
        page.locator('.master-detail__scroll').evaluate('(el) => {el.scrollLeft = el.scrollWidth; el.scrollTop = el.querySelector("tbody tr:nth-child(10)").offsetTop - 60}')
        capture('import-detail-scroll-' + size)
        page.goto(base + '/imports/')
        page.locator('[data-modal-open]').click()
        capture('upload-modal-' + size)
        page.locator('[data-modal-close]').first.click()
        page.wait_for_timeout(120)
        page.locator('[data-dropdown]').click()
        page.locator('#profile-menu').wait_for(state='visible')
        capture('profile-menu-' + size)
        page.keyboard.press('Escape')
        if size == 'mobile':
            page.locator('[data-sidebar-toggle]').click()
            capture('navigation-mobile')
            page.locator('[data-sidebar-close]').click(position={'x': 350, 'y': 100})
        page.goto(base + '/imports/new/')
        page.locator('#import-upload-modal form').evaluate('(form) => {form.noValidate = true}')
        page.locator('#import-upload-modal button[type=submit]').click()
        page.wait_for_load_state()
        capture('upload-errors-' + size)
        page.goto(base + '/imports/refunds/new/')
        page.locator('main button[type=submit]').click()
        capture('refund-errors-' + size)
    context.close()
    page = browser.new_page(reduced_motion='reduce')
    page.set_viewport_size({'width': 1366, 'height': 900})
    page.goto(base + '/login/')
    capture('login')
    page.locator('[name=username]').focus()
    capture('login-focus')
    page.locator('main button[type=submit]').hover()
    capture('login-hover')
    page.locator('main button[type=submit]').click()
    capture('login-errors')
    page.set_viewport_size({'width': 390, 'height': 844})
    capture('login-errors-mobile')
    for username, route, name in [('visual-no-access', '/dashboard/', 'forbidden'), ('visual-upload-only', '/imports/new/', 'standalone-upload')]:
        review_context = browser.new_context(reduced_motion='reduce')
        page = review_context.new_page()
        page.goto(base + '/login/')
        page.locator('[name=username]').fill(username)
        page.locator('[name=password]').fill('visual-review-local')
        page.locator('main button[type=submit]').click()
        page.wait_for_load_state()
        for size in ['laptop', 'mobile']:
            width, height = sizes[size]
            page.set_viewport_size({'width': width, 'height': height})
            page.goto(base + route)
            capture(name + '-' + size)
        review_context.close()
    browser.close()
(out / 'metrics.json').write_text(json.dumps({'pages': results, 'jsErrors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'screenshots': len(results), 'overflow': [r['name'] for r in results if r['scroll'] > r['width']], 'jsErrors': errors}))

