---
name: engineering-harbor
description: Downstream guidance for a project pushing its own arch-explicit Harbor image; hostbootstrap does not push project images.
type: guide
---

# Harbor (downstream guidance)

hostbootstrap **does not push your project image.** It builds the artifacts a
substrate needs — a container `FROM` the base tag, or a host binary (with an
optional container counterpart) — and then stops. Whether and how that artifact
reaches a registry is the **downstream project's** job, not the tool's. This
page is convention, not enforcement: hostbootstrap has no `push` command for
project images and no Harbor configuration of its own.

The split matters because the execution model decides who owns the push. See
[schema.md](schema.md) for the three models:

* **container** — the image is built locally and run. If the project wants it in
  Harbor, the project's own build/CI step pushes it.
* **host-binary** / **host-daemon** — the host binary (or its optional container
  counterpart) is responsible for any push, as part of its own lifecycle. The
  CLI only guarantees the build is current before handing off.

## Recommended convention: arch-explicit tags only

When a downstream project does push, push **arch-explicit single-arch tags** and
nothing else. The substrate is always known at push time, so the correct tag is
always nameable — there is never a reason to assemble a cross-arch manifest list.

`<project>-<substrate>-<arch>` is the recommended tag shape.

> **WRONG**
>
> ```sh
> docker buildx build --platform linux/amd64,linux/arm64 \
>   --tag harbor.example/app:latest --push .
> ```
>
> A multi-platform `buildx` push produces a manifest list — exactly the
> cross-arch indirection this convention avoids. It also pushes an arch you did
> not build on this host (via emulation), which the design forbids.
>
> **RIGHT**
>
> ```sh
> docker build --tag harbor.example/app-linux-cpu-amd64 .
> docker push harbor.example/app-linux-cpu-amd64
> ```
>
> Single-arch, host-native, with the substrate and arch named explicitly.

## No orphans

When the project pushes a new arch-explicit tag, it should delete any prior tag
*it owns* that now points at a superseded digest. Reclaiming the untagged digest
itself depends on the Harbor instance's GC policy. Keeping this discipline in the
project (rather than the tool) means the project owns its registry namespace
end-to-end.

## Base-image publication is separate

The four `basecontainer-<flavor>-<arch>` base tags are **not** project images and
are **not** covered here. hostbootstrap publishes those itself via
`hostbootstrap base push`; see [build_release.md](build_release.md) and
[base_image.md](base_image.md). A project never re-pushes the large base image —
it pulls the base from Docker Hub and pushes only its own thin layer(s).
