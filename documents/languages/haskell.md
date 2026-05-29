---
name: languages-haskell
description: Haskell conventions inside the basecontainer base image.
type: guide
---

# Haskell

The base image ships a **single GHC** — 9.12.4 — with Cabal 3.16.1.0 and a
warm Cabal store. The plan retires the previous dual-GHC arrangement
(formatter-only GHC plus project GHC) because `fourmolu`/`hlint`'s
`ghc-lib-parser` targets 9.12, so one compiler now serves both formatting and
project builds.

## Warm store

[`support/haskell-deps/`](../../support/haskell-deps/) declares the shared
dependency set. The base image runs `cabal update && cabal build all
--only-dependencies && cabal build all` during build, so the warm store
contains compiled artifacts for the closure downstream projects use most. Cold
project builds skip recompiling that closure.

## fourmolu / hlint

Both are prebuilt into the base image at `/usr/local/bin/fourmolu` and
`/usr/local/bin/hlint`. They are **container-only**: never installed, built,
or run on the host.

**Invoking them is the project's Dockerfile's responsibility** — the base
ships the binaries; each project decides when to call them (a build-time
`RUN`, a container entrypoint subcommand, …). hostbootstrap does not invoke
fourmolu/hlint.

## Project standardisation

All downstream projects standardise on GHC 9.12 as part of migrating to
hostbootstrap (§13 risk: projects on 9.14.1 refactor to 9.12).
