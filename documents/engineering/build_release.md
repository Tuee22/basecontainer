---
name: engineering-build-release
description: How base images are built and published.
type: reference
---

# Build & release

`docker build` only — **no buildx, no emulation**. A build can only ever
produce the host-native arch. Multi-platform manifest lists are forbidden by
design (see [base_image.md](base_image.md)).

## Building

```sh
hostbootstrap base build --flavor cpu --arch amd64
hostbootstrap base build --flavor cuda --arch amd64
```

The CLI:

1. Detects the host substrate.
2. Resolves every dynamic value (versions, URLs, the CUDA base image).
3. Invokes `docker build --build-arg …` against
   `docker/basecontainer.Dockerfile`.

Re-invocations are idempotent — Docker's own layer cache makes incremental
re-builds fast.

## Publishing

```sh
hostbootstrap base push --flavor cpu --arch amd64
```

Pushes the arch-explicit tag to
`docker.io/tuee22/hostbootstrap:basecontainer-<flavor>-<arch>`. The CLI never
re-pushes the large base image when a downstream project pushes its custom
image (see [harbor.md](harbor.md)).

## `--build-base` for downstream projects

A downstream project's `hostbootstrap build` invocation can pass
`--build-base` to fetch `docker/basecontainer.Dockerfile` from the
hostbootstrap GitHub repo and build the base locally, tagging it with the
identical name. The default behaviour is to **pull** the base from Docker
Hub.

## Loss of provenance

Plain `docker build` does not emit the SBOM/attestation manifests buildx
produced under the old `build-and-push.sh`. This is an accepted trade-off
(see §14 of the plan).
