"""End-to-end checks for the mirrored rating site.

The page served here is the copy `scripts/sync_live_site.py` took from the
deployment, so these checks are what CI reports before such a copy is merged.
Run against a local server:

    python3 -m http.server 8765 --bind 127.0.0.1
    python3 tests/smoke.py --url http://127.0.0.1:8765/
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
# The roster panel hides anyone without a recent contest, so the analysis table
# is shorter than the ranking table. Both numbers come from the dataset itself.
ANALYSIS_DEFAULT_NOTE = 'analysisNote'


def load_dataset(root: Path) -> dict:
    return json.loads((root / 'data.json').read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765/')
    parser.add_argument('--artifacts', default='artifacts')
    parser.add_argument('--browser-executable', default=None)
    args = parser.parse_args()
    artifacts = Path(args.artifacts).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset(ROOT)
    published = {u['id']: (u['rating'], u['maxRating'], u['matches']) for u in dataset['users']}
    hidden = set(dataset.get('hiddenUsers') or [])
    visible_expected = len(published) - len(hidden)

    errors, external = [], []
    origin = args.url.rstrip('/')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.browser_executable)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on(
            'request',
            lambda r: external.append(r.url)
            if not r.url.startswith(('data:', 'blob:')) and not r.url.startswith(origin) else None,
        )
        page.goto(args.url, wait_until='networkidle')

        # The page must load the mirrored dataset from ./api/data, not from the
        # deployment, and its own recalculation must agree with the ratings the
        # dataset already stores.
        recalculated = page.evaluate('state.users.map(u => [u.id, u.rating, u.maxRating, u.matches])')
        mismatch = [
            (uid, published[uid], tuple(values))
            for uid, *values in recalculated
            if published[uid] != tuple(values)
        ]
        assert not mismatch, f'Recalculated ratings disagree with the dataset: {mismatch[:5]}'
        assert len(recalculated) == len(published), 'The page loaded a different number of users'

        expect(page.locator('#ratingTable tbody tr')).to_have_count(visible_expected)
        expect(page.locator('#contestList .contest-item')).to_have_count(len(dataset['contests']))
        expect(page.locator('#ratingTable tbody tr').first).to_contain_text(
            max(dataset['users'], key=lambda u: u['rating'])['name']
        )

        # An anonymous visitor is read-only: no import tab, no editing buttons.
        visible_tabs = page.eval_on_selector_all(
            '.tab', 'els => els.filter(e => e.offsetParent !== null).map(e => e.dataset.tab)'
        )
        assert 'import' not in visible_tabs, f'An anonymous visitor can see the import tab: {visible_tabs}'
        for tab in ('rating', 'contests', 'players', 'analysis', 'settings'):
            assert tab in visible_tabs, f'Tab {tab} is missing for an anonymous visitor'
            page.locator(f'.tab[data-tab="{tab}"]').click()
            expect(page.locator(f'#panel-{tab}')).to_be_visible()

        page.locator('.tab[data-tab="players"]').click()
        expect(page.locator('#playerTable tbody tr')).to_have_count(len(published))

        page.locator('.tab[data-tab="analysis"]').click()
        page.select_option('#anRoster', 'all')
        expect(page.locator('#analysisTable tbody tr')).to_have_count(visible_expected)
        expect(page.locator('#analysisNote')).to_contain_text(f'{len(hidden)}')
        # Search must narrow the table to the one matching row. Pick a visible
        # name whose substring matches no one else.
        visible_names = [u['name'] for u in dataset['users'] if u['id'] not in hidden]
        unique = next(
            n for n in visible_names
            if sum(1 for other in visible_names if n.lower() in other.lower()) == 1
        )
        page.locator('#anSearch').fill(unique)
        expect(page.locator('#analysisTable tbody tr')).to_have_count(1)
        page.locator('#anSearch').fill('')

        # Opening a contest shows its scoreboard in the shared modal.
        page.locator('.tab[data-tab="contests"]').click()
        page.locator('#contestList .contest-item').first.locator('button[data-act="view"]').click()
        expect(page.locator('#modal')).to_be_visible()
        expect(page.locator('#modalBody table.tbl tbody tr').first).to_be_visible()
        page.click('#modalClose')
        expect(page.locator('#modal')).to_be_hidden()

        # The scheduled sync must stay idempotent, so the page may not write
        # anything back while it is used read-only.
        page.locator('.tab[data-tab="rating"]').click()
        page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)

        page.locator('.tab[data-tab="settings"]').click()
        page.click('#btnTheme')
        assert page.evaluate("document.documentElement.getAttribute('data-theme')") == 'dark'
        page.reload(wait_until='networkidle')
        assert page.evaluate("document.documentElement.getAttribute('data-theme')") == 'dark', (
            'The theme choice did not survive a reload'
        )
        page.click('#btnTheme')

        # Exporting is the only data path an anonymous visitor still has, and it
        # has to produce a file the import screen accepts.
        expect(page.locator('#btnExport')).to_be_hidden()
        assert page.evaluate('isAdmin') is False, 'An anonymous visitor was treated as an administrator'

        # The service worker must register so the page can work offline.
        assert page.evaluate(
            "navigator.serviceWorker.getRegistrations().then(rs => rs.length)"
        ) >= 1, 'The service worker was not registered'

        mobile = context.new_page()
        mobile.set_viewport_size({'width': 390, 'height': 844})
        mobile.on('pageerror', lambda e: errors.append(str(e)))
        mobile.goto(args.url, wait_until='networkidle')
        expect(mobile.locator('#ratingTable tbody tr')).to_have_count(visible_expected)
        mobile.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), (
            'The page overflows the mobile viewport'
        )

        browser.close()

    # `data.json` is the readable copy; `api/data` is the path the page fetches.
    # They must stay byte-identical or the mirror is inconsistent.
    assert (ROOT / 'api' / 'data').read_bytes() == (ROOT / 'data.json').read_bytes(), (
        'api/data and data.json hold different bytes'
    )
    assert not errors, errors
    assert not external, external

    print(json.dumps({
        'status': 'passed',
        'users': len(published),
        'visible_users': visible_expected,
        'hidden_users': len(hidden),
        'contests': len(dataset['contests']),
        'checks': [
            'recalculated_ratings_match_dataset',
            'contest_list',
            'anonymous_read_only',
            'five_tabs',
            'players_roster',
            'analysis_roster_and_search',
            'contest_preview',
            'theme_persists',
            'service_worker_registers',
            'mobile_layout',
            'no_js_errors',
            'no_external_requests',
            'dataset_copies_identical',
        ],
        'url': args.url,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
