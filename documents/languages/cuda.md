---
name: languages-cuda
description: CUDA conventions for the cuda-flavored basecontainer base image.
type: guide
---

# CUDA

The `basecontainer-cuda-<arch>` tags are built `FROM` the latest
`nvidia/cuda:*-cudnn-devel-ubuntu24.04` image that has a manifest for the
target arch. Resolution lives in
[`hostbootstrap/base_image.py`](../../hostbootstrap/base_image.py):

1. Query Docker Hub for `nvidia/cuda` tags matching
   `*-cudnn-devel-ubuntu24.04`.
2. Sort by semver descending.
3. Pick the first tag whose `images` array carries the target arch.

The selected tag becomes `--build-arg BASE_IMAGE=nvidia/cuda:…` at build
time.

## Ldconfig

The Dockerfile checks for `/usr/local/cuda/lib64`; when present it adds the
path to `/etc/ld.so.conf.d/cuda.conf` and runs `ldconfig`. This is a runtime
filesystem check, not version-resolution logic, so it stays in the Dockerfile.

## CUDA drift

Dynamic resolution always pulls the latest `cudnn-devel-ubuntu24.04` tag. A
project pinned to an older CUDA must override the resolved base explicitly
when invoking `hostbootstrap base build` — see §14.5 of the plan.

## arm64

`basecontainer-cuda-arm64` is supported by the naming scheme but built only
on demand; GPU projects today are amd64 in practice.
