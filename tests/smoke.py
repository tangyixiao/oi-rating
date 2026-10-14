"""End-to-end checks for the published snapshot and browser-only edits."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765/oi-rating/')
    parser.add_argument('--artifacts', default='artifacts')
    parser.add_argument('--browser-executable', default=None)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artifacts = Path(args.artifacts).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    backup = json.loads((root / 'data.json').read_text())
    errors, writes, intranet = [], [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.browser_executable)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: writes.append(r.url) if r.method not in ('GET', 'HEAD') else None)
        page.on('request', lambda r: intranet.append(r.url) if '10.176.20.37' in r.url else None)
        page.goto(args.url, wait_until='networkidle')
        expect(page.locator('#ratingTable tbody tr')).to_have_count(53, timeout=10000)
        expect(page.locator('#contestList .contest-item')).to_have_count(108)
        ratings = page.evaluate('state.users.map(u => [u.id, u.rating, u.maxRating, u.matches])')
        assert sorted(ratings) == sorted([[u['id'], u['rating'], u['maxRating'], u['matches']] for u in backup['users']]), 'Recalculated ratings differ from backup'
        for tab in ('rating', 'contests', 'players', 'analysis', 'import', 'settings'):
            page.locator(f'.tab[data-tab="{tab}"]').click()
            expect(page.locator(f'#panel-{tab}')).to_be_visible()
        page.locator('.tab[data-tab="analysis"]').click()
        page.locator('#anRoster').select_option('all')
        expect(page.locator('#analysisTable tbody tr')).to_have_count(53)
        page.locator('#anSearch').fill(backup['users'][0]['name'])
        assert page.locator('#analysisTable tbody tr').count() >= 1
        page.locator('.tab[data-tab="rating"]').click()
        page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)

        page.locator('.tab[data-tab="settings"]').click()
        page.locator('#sMin').fill('-123')
        page.locator('#btnSaveSettings').click()
        page.reload(wait_until='networkidle')
        page.locator('.tab[data-tab="settings"]').click()
        expect(page.locator('#sMin')).to_have_value('-123')
        page.once('dialog', lambda d: d.dismiss())
        with page.expect_event('dialog'):
            page.locator('#btnCloudPull').click()
        expect(page.locator('#sMin')).to_have_value('-123')
        page.once('dialog', lambda d: d.accept())
        with page.expect_event('dialog'):
            page.locator('#btnCloudPull').click()
        expect(page.locator('#sMin')).to_have_value(str(backup['settings']['minRating']))
        with page.expect_download() as item:
            page.locator('#btnExport').click()
        target = artifacts / 'export.json'
        item.value.save_as(str(target))
        exported = json.loads(target.read_text())
        assert len(exported['users']) == 53 and len(exported['contests']) == 108
        page.locator('#sMin').fill('-222')
        page.locator('#btnSaveSettings').click()
        page.once('dialog', lambda d: d.accept())
        page.locator('#jsonInput').set_input_files(str(root / 'data.json'))
        expect(page.locator('#sMin')).to_have_value(str(backup['settings']['minRating']))
        expect(page.locator('#toast')).to_have_text('导入成功')
        expect(page.locator('#ratingTable tbody tr')).to_have_count(53)
        page.reload(wait_until='networkidle')
        expect(page.locator('#ratingTable tbody tr')).to_have_count(53)

        page.locator('.tab[data-tab="settings"]').click()
        held = []
        edited_during_fetch = [False]
        confirmations = []

        def handle_restore_dialog(dialog):
            confirmations.append(edited_during_fetch[0])
            if edited_during_fetch[0]:
                dialog.dismiss()
            else:
                dialog.accept()

        page.route('**/data.json', lambda route: held.append(route))
        page.on('dialog', handle_restore_dialog)
        with page.expect_request('**/data.json'):
            page.locator('#btnCloudPull').click()
        page.locator('#sMin').fill('-333')
        page.locator('#btnSaveSettings').click()
        edited_during_fetch[0] = True
        assert held, 'Restore request was not held'
        with page.expect_event('dialog'):
            held[0].fulfill(status=200, content_type='application/json', body=json.dumps(backup))
        expect(page.locator('#sMin')).to_have_value('-333')
        assert confirmations[-1] is True, 'Edits made while loading were not confirmed before overwriting'
        page.remove_listener('dialog', handle_restore_dialog)
        page.unroute('**/data.json')
        page.once('dialog', lambda d: d.accept())
        page.locator('#btnCloudPull').click()
        expect(page.locator('#sMin')).to_have_value(str(backup['settings']['minRating']))

        held_boot = []
        other_tab = context.new_page()
        other_tab.route('**/data.json', lambda route: held_boot.append(route))
        other_tab.goto(args.url, wait_until='domcontentloaded')
        page.locator('#sMin').fill('-444')
        page.locator('#btnSaveSettings').click()
        assert held_boot, 'Startup request was not held'
        held_boot[0].fulfill(status=200, content_type='application/json', body=json.dumps(backup))
        other_tab.wait_for_load_state('networkidle')
        expect(other_tab.locator('#sMin')).to_have_value('-444')
        assert other_tab.evaluate('JSON.parse(localStorage.getItem(STORAGE_KEY)).settings.minRating') == -444, 'Startup overwrote edits saved in another tab'
        other_tab.close()
        page.once('dialog', lambda d: d.accept())
        page.locator('#btnCloudPull').click()
        expect(page.locator('#sMin')).to_have_value(str(backup['settings']['minRating']))

        page.route('**/data.json', lambda route: route.abort())
        page.reload(wait_until='networkidle')
        expect(page.locator('#ratingTable tbody tr')).to_have_count(53)
        expect(page.locator('#toast')).to_contain_text('已保留本机数据')
        page.unroute('**/data.json')

        mobile = context.new_page()
        mobile.set_viewport_size({'width': 390, 'height': 844})
        mobile.on('pageerror', lambda e: errors.append(str(e)))
        mobile.goto(args.url, wait_until='networkidle')
        expect(mobile.locator('#ratingTable tbody tr')).to_have_count(53)
        mobile.locator('.tab[data-tab="rating"]').click()
        mobile.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page overflows the mobile viewport'
        assert not errors, errors
        assert not writes, writes
        assert not intranet, intranet
        print(json.dumps({'status': 'passed', 'users': 53, 'contests': 108, 'checks': ['ratings_match_backup', 'six_tabs', 'analysis_filter', 'local_edit_reload', 'restore_cancel', 'restore_confirm', 'json_export', 'json_import', 'restore_protects_edits_during_fetch', 'startup_protects_edits_from_another_tab', 'failed_fetch_preserves_local_data', 'mobile_layout', 'no_js_errors', 'no_network_writes', 'no_intranet_requests'], 'url': args.url}, ensure_ascii=False))
        browser.close()


if __name__ == '__main__':
    main()
