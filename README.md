# hostbootstrap

A small host-installed Python CLI and a tiny family of prebuilt base
container images. Together they replace per-project bootstrap shells and
redundant multi-language Dockerfiles with one shared toolchain pulled from
Docker Hub and one declarative `hostbootstrap.yaml` per project.

> **Adopting hostbootstrap**: install the CLI on the host, write a
> `hostbootstrap.yaml`, inherit your project Dockerfile `FROM` the base tag the
> CLI selects. Everything else — substrate detection, prereqs, build, push,
> cluster lifecycle — is the CLI's job.

The authoritative design document is
[`HOSTBOOTSTRAP_REFACTOR_PLAN.md`](HOSTBOOTSTRAP_REFACTOR_PLAN.md). Detailed
language/engineering notes live under [`documents/`](documents/README.md).

---

## What you get

* **Four prebuilt base images** on Docker Hub —
  `docker.io/tuee22/hostbootstrap:basecontainer-{cpu,cuda}-{amd64,arm64}` —
  carrying the shared toolchain (GHC 9.12, Cabal, Go, Node + PureScript +
  Playwright, Python + Poetry, kube tools, LLVM/C++, Rust, optional CUDA, with
  fourmolu/hlint and a warm Haskell store baked in).
* **One CLI** (`hostbootstrap`) that detects your substrate, validates host
  prerequisites, drives `docker build` / `docker run`, manages cluster
  lifecycle, and (where applicable) installs a system-level service unit for
  host daemons.

Single-arch tags only — never manifest lists. The CLI always knows the
substrate, so it references the one correct arch tag directly.

---

## Installing the CLI

```bash
python -m pip install \
  "git+https://github.com/tuee22/hostbootstrap.git#egg=hostbootstrap"
```

Install into **host Python**, not into any project virtualenv. Projects that
maintain their own `.venv` (e.g. ML adapters) must keep `hostbootstrap` out of
that venv — see §10 of the plan.

To develop hostbootstrap itself, the repo uses Poetry with an in-project
`.venv` (`poetry.toml` sets `virtualenvs.in-project = true`):

```bash
poetry install
poetry run check-code
```

---

## The three model archetypes

Every project picks **one model per substrate** in its `hostbootstrap.yaml`.

### Outer-container

The project's CLI runs inside a custom container `FROM` the base image.
`hostbootstrap run …` forwards the Docker socket and applies the yaml's
`mounts` (no `compose.yaml`). Persistent services use
`--restart unless-stopped`; one-shot `run` commands use `--rm`.

```yaml
project: example
base: { flavor: cpu }
container:
  dockerfile: docker/example.Dockerfile
  harbor: { repo: harbor.example/example }
mounts:
  - { host: ./.data, container: /opt/example/.data }
  - { host: /var/run/docker.sock, container: /var/run/docker.sock }
substrates:
  linux-cpu: { model: outer-container }
  linux-gpu: { model: outer-container, gpu: true }
```

### Host-binary

The project produces a binary that runs **on the host**. On Apple silicon the
binary is built with host `cabal` (GHC via brew → ghcup). On Linux the binary
is built **inside the base container** and extracted to the host's `.build/`
directory — keeping the toolchain off the Linux host. The host `.build/`
exists only for host-binary projects and is never bind-mounted into an outer
container.

```yaml
project: example
base: { flavor: cpu }
container:
  dockerfile: docker/example.Dockerfile
  harbor: { repo: harbor.example/example }
substrates:
  linux-cpu: { model: host-binary }
  apple-silicon:
    model: host-binary
    host: { ghc: true }
```

### Multi-substrate

A containerized daemon `FROM` the base ships to Harbor on Linux; on Apple
silicon a containerized counterpart is **still** built and uploaded (so
quality checks and the in-cluster sibling exist) and **also** a host-native
binary runs for direct hardware access (Swift in Tart, GPU on Metal). The host
binary keeps its control-plane role and reaches in-cluster services only over
loopback (`127.0.0.0/8`) NodePorts — a deliberate security boundary.

```yaml
project: example
base: { flavor: cuda }
container:
  dockerfile: docker/example.Dockerfile
  harbor: { repo: harbor.example/example }
substrates:
  linux-cpu:     { model: multi-substrate }
  linux-gpu:     { model: multi-substrate, gpu: true }
  apple-silicon:
    model: multi-substrate
    host:   { ghc: true, tart: true, metal: true }
    daemon: ".build/example inference --serve"
```

A substrate may declare `daemon` — a host-level command run on `cluster up`.
`hostbootstrap` wraps it in a system-scope systemd unit (Linux) or a
**LaunchDaemon** in `/Library/LaunchDaemons/` (macOS, **never** a per-user
LaunchAgent), so the daemon starts at boot before any user logs in.

---

## Command reference

| Command | What it does |
|---|---|
| `hostbootstrap doctor` | Detect substrate; validate + idempotently install host prereqs |
| `hostbootstrap build` | Idempotently build the project artifact for the current substrate |
| `hostbootstrap push` | Push the arch-explicit custom image to Harbor (never re-pushing the base) |
| `hostbootstrap cluster up` | Bring the whole stack to running (build, bootstrap, publish, daemon) |
| `hostbootstrap cluster down` | Tear the cluster down — **never deletes host `.data`** |
| `hostbootstrap cluster delete` | Thorough teardown (cluster + derived state) — still preserves `.data` |
| `hostbootstrap run <cmd…>` | Replaces `docker compose run …` / `.build/<binary> …`; idempotently `cluster up`s and dispatches per model |
| `hostbootstrap base build` | Build a base tag locally (used inside this repo and by downstream `--build-base`) |
| `hostbootstrap base push` | Push a base tag to Docker Hub |

`doctor`, `build`, `push`, and the `cluster *` verbs are all **idempotent**:
re-running on a healthy host is a no-op.

---

## How the base images get built

Versions, download URLs, the architecture string, and the CUDA base image
are all resolved on the host by [`hostbootstrap/base_image.py`](hostbootstrap/base_image.py)
and passed via `docker build --build-arg`. The Dockerfile
([`docker/basecontainer.Dockerfile`](docker/basecontainer.Dockerfile)) consumes
ARGs only — no `if`/`case`/version probing.

Plain `docker build`. No buildx, no emulation; a build can only ever produce
the host-native arch.

* **Default** for downstream projects: pull the base from Docker Hub.
* **`--build-base`**: build the base locally, fetching
  `basecontainer.Dockerfile` from this repo, tagging it with the identical name.

The CUDA base image is resolved dynamically from Docker Hub: query
`nvidia/cuda` tags matching `*cudnn-devel-ubuntu24.04`, pick the latest version
with a manifest for the target arch (so a CUDA-pinned project must explicitly
override the resolved base).

---

## Repository layout

```
hostbootstrap/                   # the Python package (flat layout)
  cli.py                         # Click entrypoint
  substrate.py                   # apple-silicon | linux-cpu | linux-gpu
  prereqs.py                     # host prereq checks/installers
  spec.py                        # hostbootstrap.yaml schema
  process.py                     # async subprocess wrapper
  docker_ops.py                  # build/run/push arg-builders + runners
  base_image.py                  # version/URL/CUDA resolvers + build helpers
  harbor.py                      # arch-explicit push, no orphans
  check_code.py                  # ruff → black → mypy strict
  models/
    outer_container.py
    host_binary.py
    multi_substrate.py
docker/
  basecontainer.Dockerfile       # logic-free; all values via ARG
support/
  haskell-deps/                  # warm Cabal store
documents/                       # SSoT documentation tree
stubs/                           # mypy .pyi shims
pyproject.toml                   # Poetry; hostbootstrap + check-code scripts
poetry.toml                      # in-project .venv (dev only)
```

---

## Invariants the tool enforces

* The host `.data` bind mount is maintained the entire time the cluster is up.
* `.build/` exists only for host-binary projects; never bind-mounted into an
  outer container.
* `cluster down` / `cluster delete` **never delete host `.data`**.
* Host-level daemons are managed by system-scope systemd units / LaunchDaemons,
  not user-scope LaunchAgents — so they survive a reboot and start
  pre-login (supporting headless remote SSH).
* fourmolu/hlint run **only** inside the container — invoked by the project's
  Dockerfile against the prebuilt tools the base ships.
* In-cluster services are reachable from the host binary over loopback
  (`127.0.0.0/8`) NodePorts only — never off-host.

See `HOSTBOOTSTRAP_REFACTOR_PLAN.md` for the full motivation, acceptance
criteria, and per-project migration map.
