---
name: engineering-harbor
description: Arch-explicit Harbor push semantics; no orphans.
type: reference
---

# Harbor

Custom project images are pushed to Harbor with **arch-explicit tags only**.
Manifest lists are forbidden — the substrate is always known, so the right
tag is always nameable.

## Tag scheme

`<project>-<substrate>-<arch>` (the project binary owns the actual push; the
CLI ensures the build is up to date first; see §9.7).

## No orphans

When a project pushes a new arch-explicit tag, hostbootstrap deletes any
prior tag *it owns* that pointed at a now-superseded digest. Reclaiming the
untagged digest itself depends on the Harbor instance's GC policy (§14 risk).

## Never re-push the base

Project pushes carry only the project layer(s). The large base image is
**never** re-pushed by a project — it lives at
`docker.io/tuee22/hostbootstrap:…` and downstream projects pull from there.
