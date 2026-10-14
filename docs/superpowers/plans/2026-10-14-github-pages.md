# OI Rating Pages Implementation Plan

> **For agentic workers:** Use inline execution for this small deployment task.

**Goal:** Archive the specified app in the home directory and publish a working public GitHub Pages mirror with the supplied backup.

**Architecture:** Keep the captured app and JSON as local originals. Adapt its storage and network boundary for static hosting without changing the rating algorithm.

**Tech Stack:** HTML, CSS, JavaScript, browser localStorage, Python Playwright, GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-10-14-github-pages-design.md`

## Global Constraints

- Publish the supplied JSON: 53 users and 108 contests.
- Keep original files and exclude archive, virtual environment, and screenshots from Git.
- Make all published data requests relative to the current repository URL.
- Never send edits to the source server or GitHub Pages.

## Review Focus

- Repository subpath loading: relative data URLs must load.
- Reload after local edits: edits must survive.
- Restore cancellation: edits must remain intact.
- Failed published-data fetch: preserve existing local data and display an error.
- Initial ratings must agree with the supplied backup.

### Task 1: Archive and static adaptation

- [x] Save the two directly referenced site responses and supplied backup with hashes.
- [x] Add `tests/smoke.py`; run against the original page and confirm it fails because no data loads on a static server.
- [x] Adapt `index.html` to load `data.json`, preserve browser edits, and restore public data only after confirmation.
- [x] Run browser smoke checks and inspect screenshots.
- [x] Document local serving, testing, and public-data update in `README.md`.

### Task 2: Publish and verify

- [ ] Review the final diff and archive hashes.
- [ ] Initialize a dedicated Git repository, commit verified files, create a public `tangyixiao/oi-rating` repository, and push main.
- [ ] Enable Pages from main root using the API.
- [ ] Wait for the Pages build and compare served HTML/JSON hashes; run smoke checks on the HTTPS site.
- [ ] Report the website, repository, local directory, and browser-only editing limitation.
