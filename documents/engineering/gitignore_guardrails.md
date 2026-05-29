---
name: engineering-gitignore
description: What stays out of version control.
type: reference
---

# .gitignore guardrails

Every project that adopts hostbootstrap must keep these out of git:

* `.venv/`, `__pycache__/`, `*.pyc` — Python build state.
* `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/` — Python tool caches.
* `dist-newstyle/`, `.cabal-sandbox/`, `cabal.project.freeze` — Haskell build
  state. (`cabal.project.freeze` is intentionally excluded; the warm store
  pins compatible versions.)
* `node_modules/`, `dist/`, `output/`, `.spago/`, `playwright-report/`,
  `test-results/`, `*.tsbuildinfo` — JS / TS / PureScript / Playwright.
* `target/`, `Cargo.lock` (libraries only) — Rust.
* `*.lock`, `poetry.lock`, `package-lock.json`, `yarn.lock`,
  `pnpm-lock.yaml`, `spago.lock`, `npm-shrinkwrap.json` — package manager
  lockfiles.
* `.build/` — host-binary output. Only host-binary projects have this; it
  must never be bind-mounted into an outer container (§9.3 invariant).
* `.data/` — host persistent state. The CLI bind-mounts this while the
  cluster is running; it must **never** be deleted by `cluster down` or
  `cluster delete`.

The repo's [`.gitignore`](../../.gitignore) covers all of the above for
hostbootstrap itself; downstream projects mirror the same pattern.
