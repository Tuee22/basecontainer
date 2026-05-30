---
name: testing
description: How hostbootstrap is tested — the layered suite, the test-all entrypoint, and how to run it.
type: guide
---

# Testing

hostbootstrap orchestrates `docker`, `cabal`, `systemctl`/`launchctl`, and HTTP
version lookups by shelling out — so the test strategy is built around one fact:
the code separates **pure functions that build command-argument lists and
resolve values** from the thin effectful async runners. That separation is what
makes the suite fast and hermetic — almost everything worth testing is a pure
function that returns data, so the default run touches no network, no Docker, and
no `sudo`. The full suite runs in well under a second.

## Running the suite

There is exactly one entry point, [`test-all`](../../hostbootstrap/test_all.py):

> **WRONG**
>
> ```sh
> poetry run pytest
> ```
>
> Refused by `tests/conftest.py` — it aborts unless the `HOSTBOOTSTRAP_TEST_ALL`
> sentinel is set. This keeps one supported command with one configuration, so
> the marker/skip behaviour below can't be bypassed by accident.
>
> **RIGHT**
>
> ```sh
> poetry run test-all            # full suite
> poetry run test-all -k spec    # extra args forward to pytest
> ```

`test-all` sets the sentinel and invokes pytest over `tests/`.
[`check-code`](../../hostbootstrap/check_code.py) (ruff → black → mypy) stays a
separate command; run both in CI.

## The layers

The suite is a thin pyramid weighted to pure unit + Dhall contract tests.

**Pure unit tests** — the bulk. The builders/resolvers return data, so no mocking
is needed: [`docker_ops`](../../hostbootstrap/docker_ops.py) command tuples,
[`base_image`](../../hostbootstrap/base_image.py) tag/URL builders and the JSON
narrowers, [`units`](../../hostbootstrap/units.py) systemd/launchd text,
[`substrate`](../../hostbootstrap/substrate.py) detection, and the
[`models`](../../hostbootstrap/models) path/mount/command helpers. HTTP-backed
resolvers and the [`dhall_tool`](../../hostbootstrap/dhall_tool.py) downloader are
tested with `monkeypatch` over `httpx` (an in-memory `tar.bz2`, a checksum
mismatch) — never the real network.

**Dhall contract tests** (`tests/test_spec_dhall.py`, marked `dhall`) — the
highest-value, project-specific layer. They drive [`spec.load`](../../hostbootstrap/spec.py)
through the real `dhall-to-json` against fixtures in `tests/fixtures/dhall/`:
five `valid/` archetypes load to the expected dataclasses, and four `invalid/`
ones (`daemon` on a `Container`, a `HostDaemon` missing its `daemon`, `mounts` on
a `HostBinary`, a bad `flavor`) must raise `SpecError`. This is the executable
form of the [schema](schema.md) promise — *illegal states are unrepresentable*.
It also double-checks the shipped [`dhall/package.dhall`](../../dhall/package.dhall)
against the parser. Parsing logic itself is additionally tested against crafted
JSON (`tests/test_spec.py`) with no Dhall at all.

**Integration / smoke** — thin and gated. CLI smoke uses Click's `CliRunner`
(command tree, `push` is gone, clean errors); model dispatch is tested by
recording `process.run`/`run_checked` (a fixture in `conftest.py`) and asserting
the exact `docker`/`cabal` argv — no daemon required. A real-docker end-to-end
build/run is reserved for the `docker` marker (CI with a daemon).

## Markers and skipping

Configured in `pyproject.toml` under `[tool.pytest.ini_options]`:

* `dhall` — needs a provisioned `dhall-to-json`; the `require_dhall` fixture
  **skips** (does not fail) when it can't be obtained (offline CI). Locally it is
  fetched and cached once (see [prerequisites](prerequisites.md)).
* `docker` — needs a running Docker daemon; **skips** when absent.
* `slow` — long-running.

`test-all` runs the whole tree; anything whose requirement is missing skips
cleanly, so a default developer run is hermetic and green.

## What is deliberately not auto-tested

Creating real systemd/launchd units needs root, and `doctor`'s host mutation is
environment-specific — both are out of scope for the automated suite. Their
*logic* is covered by the `units` string tests and the recorded-dispatch tests;
exercising the real units belongs in a manual or CI-on-a-VM run.
