---
name: languages-playwright
description: Playwright conventions inside the basecontainer base image.
type: guide
---

# Playwright

The base image installs Playwright globally and runs
`playwright install --with-deps chromium firefox webkit`, so the three
browser engines plus their apt-side runtime dependencies are present in the
image.

Browsers live at `/ms-playwright` (`PLAYWRIGHT_BROWSERS_PATH`). Tests that
expect that path automatically pick them up.

`/root/.npm` is removed after install to keep the image lean.
