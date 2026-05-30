---
name: documents-index
description: Index of the hostbootstrap SSoT documentation tree.
type: index
---

# Documents

This directory is the single source of truth for hostbootstrap's design,
toolchain, and engineering practices. The repository
[`README.md`](../README.md) is a concise adoption guide; the deep technical
material lives here.

* [documentation_standards.md](documentation_standards.md) — authoritative doc
  conventions for this repository.

## Engineering references

* [engineering/schema.md](engineering/schema.md) — the `hostbootstrap.dhall`
  project-config schema, its three execution models, and how illegal states
  are rejected.
* [engineering/base_image.md](engineering/base_image.md) — the four
  `basecontainer-<flavor>-<arch>` tags and what they contain.
* [engineering/build_release.md](engineering/build_release.md) — base-image
  build, publish, and `--build-base` semantics.
* [engineering/prerequisites.md](engineering/prerequisites.md) — substrate
  prereqs absorbed by `hostbootstrap doctor`.
* [engineering/testing.md](engineering/testing.md) — the layered test suite, the
  `test-all` entrypoint, and how to run it.
* [engineering/harbor.md](engineering/harbor.md) — downstream guidance for a
  project pushing its own arch-explicit image (hostbootstrap does not push
  project images).
* [engineering/gitignore_guardrails.md](engineering/gitignore_guardrails.md) —
  what must stay out of version control.

## Per-language guidance

* [languages/haskell.md](languages/haskell.md)
* [languages/python.md](languages/python.md)
* [languages/node.md](languages/node.md)
* [languages/purescript.md](languages/purescript.md)
* [languages/playwright.md](languages/playwright.md)
* [languages/rust.md](languages/rust.md)
* [languages/cpp.md](languages/cpp.md)
* [languages/cuda.md](languages/cuda.md)
* [languages/go.md](languages/go.md)
* [languages/cluster_tooling.md](languages/cluster_tooling.md)
