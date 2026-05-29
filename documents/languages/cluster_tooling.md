---
name: languages-cluster-tooling
description: Kubernetes/cluster CLIs shipped in the basecontainer base image.
type: guide
---

# Cluster tooling

The base image carries the CLIs every project needs to drive a local Kind
cluster + Harbor registry:

| CLI | Source |
|---|---|
| `docker`, `docker buildx`, `docker compose` | apt (`docker.io`, `docker-buildx`, `docker-compose-v2`) |
| `kind` | latest GitHub release |
| `kubectl` | `dl.k8s.io/release/stable.txt` |
| `helm` | latest GitHub release |
| `skopeo` | apt |
| `mc` (MinIO client) | `dl.min.io` |
| `aws` (v2) | `awscli.amazonaws.com` |
| `pulumi` | latest GitHub release |
| `nvkind` | `github.com/NVIDIA/nvkind` (built in-place; see [go.md](go.md)) |

All versions are resolved on the host by `hostbootstrap/base_image.py` and
passed as `--build-arg` to the Dockerfile.

## Loopback NodePorts

Multi-substrate projects' in-cluster services (e.g. MinIO, Pulsar) are
reachable from the Apple-silicon host-native binary **only over loopback
NodePorts (`127.0.0.0/8`)**. This is a deliberate security boundary: cluster
services must never be reachable off-host (§9.7).
