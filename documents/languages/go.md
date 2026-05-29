---
name: languages-go
description: Go conventions inside the basecontainer base image.
type: guide
---

# Go

Go is first-class in the base image. The latest stable Go toolchain is
installed at `/opt/go` (resolved via `https://go.dev/dl/?mode=json`). The
image sets the conventional environment variables alongside the other
languages':

```
GOROOT=/opt/go
GOPATH=/opt/cache/go
GOCACHE=/opt/cache/go/build
GOMODCACHE=/opt/cache/go/mod
GOTOOLCHAIN=local
PATH=…/opt/go/bin:/opt/cache/go/bin:…
```

## nvkind

The base image builds `nvkind` natively in the final image, in a **single
stage** with `CGO_ENABLED=1`. Native gcc is present in the same stage, so
the old `nvkind-builder` multi-stage + cross-compile path is gone (§4).

```Dockerfile
RUN CGO_ENABLED=1 /opt/go/bin/go install github.com/NVIDIA/nvkind/cmd/nvkind@latest \
 && install -m 0755 /opt/cache/go/bin/nvkind /usr/local/bin/nvkind
```

A build can only ever produce the host-native arch — there is no cross-arch
build for Go, which keeps this stage simple.
