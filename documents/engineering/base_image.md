---
name: engineering-base-image
description: The four basecontainer base tags and their contents.
type: reference
---

# Base image

Four single-arch, prebuilt tags carry the shared toolchain:

```
docker.io/tuee22/hostbootstrap:basecontainer-cpu-amd64
docker.io/tuee22/hostbootstrap:basecontainer-cpu-arm64
docker.io/tuee22/hostbootstrap:basecontainer-cuda-amd64
docker.io/tuee22/hostbootstrap:basecontainer-cuda-arm64
```

There are no manifest lists. The CLI knows the substrate and pulls the one
correct arch tag.

## Substrate → tag

| Substrate | Tag |
|---|---|
| `apple-silicon` | `basecontainer-cpu-arm64` |
| `linux-cpu` (amd64) | `basecontainer-cpu-amd64` |
| `linux-cpu` (arm64) | `basecontainer-cpu-arm64` |
| `linux-gpu` (amd64) | `basecontainer-cuda-amd64` |
| `linux-gpu` (arm64) | `basecontainer-cuda-arm64` (built on demand) |

## What ships in the image

* **Haskell** — GHC 9.12.4, Cabal 3.16.1.0, prebuilt fourmolu/hlint, a warm
  Cabal store from [`support/haskell-deps/`](../../support/haskell-deps/).
* **Go** — first-class toolchain installed at `/opt/go`; `GOPATH`, `GOCACHE`,
  `GOMODCACHE`, `GOTOOLCHAIN`, and `PATH` set alongside other languages.
* **nvkind** — built once in the final image (`CGO_ENABLED=1 go install
  …/nvkind@latest`) and copied to `/usr/local/bin/nvkind`.
* **Node** — latest upstream Node, with npm, esbuild, TypeScript, Playwright
  (Chromium/Firefox/WebKit), Spago, purs-tidy.
* **PureScript** — latest `purs`.
* **Python** — Ubuntu 24.04 default Python with Poetry as the only global
  package, plus the build-essentials toolchain.
* **Kube tooling** — Docker CLI/compose (no buildx), kind, kubectl, helm,
  skopeo, MinIO `mc`, AWS CLI v2, Pulumi.
* **C/C++/LLVM** — build-essential, the latest available `llvm-N` family
  (LLVM 19 on Ubuntu 24.04), BOLT, LLD; CMake, Ninja, Make.
* **Rust** — `rustup` stable with `llvm-tools-preview` and `rustfmt`.
* **CUDA (cuda flavor only)** — built on top of the latest
  `nvidia/cuda:*-cudnn-devel-ubuntu24.04` with a manifest for the target arch.

See [`docker/basecontainer.Dockerfile`](../../docker/basecontainer.Dockerfile)
for the exact instructions. The Dockerfile is **logic-free**: every dynamic
value (versions, URLs, arch strings, the CUDA base image) arrives as a
`--build-arg`, resolved on the host by
[`hostbootstrap/base_image.py`](../../hostbootstrap/base_image.py).

## Dockerfile rules

The Dockerfile is deliberately constrained so a build is reproducible,
host-native, and free of shell indirection. These rules also apply to downstream
project Dockerfiles:

* **No `/bin/bash`.** The default POSIX `/bin/sh` is used; there is **no `SHELL`
  directive**. Anything needing bash-only syntax does not belong in a layer.
* **No pipes.** A `RUN` step never pipes one command into another — split it into
  discrete steps (or a copied script) so each command's exit status is checked.
* **No `docker-buildx`** and **no `--jobs=1`.** A build is single-arch and
  host-native; buildx exists only to assemble cross-arch manifest lists, which
  are forbidden (see [build_release.md](build_release.md)).

> **WRONG**
>
> ```sh
> docker buildx build --platform linux/amd64,linux/arm64 \
>   --build-arg BASE_IMAGE=… -f docker/basecontainer.Dockerfile .
> ```
>
> `buildx --platform` emits a manifest list and pulls in emulation to build an
> arch the host cannot run natively — exactly the cross-arch artifact the design
> rejects.
>
> **RIGHT**
>
> ```sh
> hostbootstrap base build --flavor cpu --arch amd64
> ```
>
> Plain `docker build` under the hood, single-arch, host-native, with every
> version/URL computed on the host.

### The one CUDA exception

There is exactly **one** permitted conditional in the Dockerfile: an
`if [ -d /usr/local/cuda/lib64 ]` block that, when the directory exists, adds it
to `/etc/ld.so.conf.d/cuda.conf` and runs `ldconfig`. A single Dockerfile serves
both the `cpu` and `cuda` bases via the `BASE_IMAGE` arg, and only the cuda base
ships that directory. This is a **build-time filesystem check**, not
version-resolution logic and not a runtime probe — it needs no GPU, driver, or
CUDA runtime, so the cuda image still builds on a host with no CUDA hardware.
See [`languages/cuda.md`](../languages/cuda.md).
