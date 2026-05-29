---
name: languages-purescript
description: PureScript conventions inside the basecontainer base image.
type: guide
---

# PureScript

The base image installs the **latest upstream `purs`** for the target arch,
plus `purs-tidy` and `spago` via npm (see [node.md](node.md)). The resolver
maps the arch to the upstream asset name:

* `amd64` → `linux64.tar.gz`
* `arm64` → `linux-arm64.tar.gz`

PureScript projects use `spago` for builds and `purs-tidy` for formatting —
both shipped globally, both runnable from the container.
