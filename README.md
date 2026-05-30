# hostbootstrap

A small host-installed Python CLI and a tiny family of prebuilt base
container images. Together they replace per-project bootstrap shells and
redundant multi-language Dockerfiles with one shared toolchain pulled from
Docker Hub and one declarative, **typed** `hostbootstrap.dhall` per project.

> **Adopting hostbootstrap**: install the CLI on the host, write a
> `hostbootstrap.dhall` that imports the Dhall package this repo ships, inherit
> your project Dockerfile `FROM` the base tag the CLI selects. Everything else —
> substrate detection, prereqs, build, cluster lifecycle, and (only where a
> project asks for it) a system service unit — is the CLI's job.

The authoritative design document is
[`HOSTBOOTSTRAP_REFACTOR_PLAN.md`](HOSTBOOTSTRAP_REFACTOR_PLAN.md). The full
config schema is [`documents/engineering/schema.md`](documents/engineering/schema.md).
Detailed language/engineering notes live under [`documents/`](documents/README.md).

---

## What you get

* **Four prebuilt base images** on Docker Hub —
  `docker.io/tuee22/hostbootstrap:basecontainer-{cpu,cuda}-{amd64,arm64}` —
  carrying the shared toolchain (GHC 9.12, Cabal, Go, Node + PureScript +
  Playwright, Python + Poetry, kube tools, LLVM/C++, Rust, optional CUDA, with
  fourmolu/hlint and a warm Haskell store baked in).
* **One CLI** (`hostbootstrap`) that detects your substrate, validates host
  prerequisites, drives `docker build` / `docker run`, manages cluster
  lifecycle, and — for the one model that asks for it — installs a system-level
  service unit.

Single-arch tags only — never manifest lists. The CLI always knows the
substrate, so it references the one correct arch tag directly.

---

## Installing the CLI

```bash
python -m pip install \
  "git+https://github.com/tuee22/hostbootstrap.git#egg=hostbootstrap"
```

Install into **host Python**, not into any project virtualenv. This works on a
stock Python 3.12 on Apple Silicon and Ubuntu 24.04 with no Rust toolchain and
no manual steps: hostbootstrap provisions its own native `dhall-to-json` binary
on first use. It prefers one already on `PATH` (e.g. `brew install dhall-json`),
otherwise it downloads a pinned, SHA256-verified static release into
`~/.cache/hostbootstrap/`.

To develop hostbootstrap itself, the repo uses Poetry with an in-project
`.venv` (`poetry.toml` sets `virtualenvs.in-project = true`):

```bash
poetry install
poetry run check-code
```

---

## The config: `hostbootstrap.dhall`

Each project ships a typed `hostbootstrap.dhall` that imports the Dhall package
this repo publishes at [`dhall/package.dhall`](dhall/package.dhall) and builds
one typed value. We use **Dhall** rather than YAML for one reason: its union
types make illegal configurations *unrepresentable at the type level* — a
`Container` has no `daemon` field, so writing one is a type error before the CLI
ever runs.

```dhall
let H = ./vendor/hostbootstrap/package.dhall
in  H.config
      { project = "example"
      , substrates =
        [ H.entry H.Substrate.LinuxCpu
            (H.Model.Container H.Container::{ dockerfile = "docker/example.Dockerfile" })
        ]
      }
```

One `H.entry` per substrate (`H.Substrate.AppleSilicon`, `.LinuxCpu`, or
`.LinuxGpu`); each picks exactly one of the three models below. See the full
field reference in [`documents/engineering/schema.md`](documents/engineering/schema.md).

---

## The three model archetypes

Every substrate picks **one model**. Choose by lifecycle:

* **No cluster, just build + run** → **Container**.
* **A host binary that owns its own lifecycle** → **HostBinary**.
* **A long-running host-native daemon** → **HostDaemon**.

### Container

hostbootstrap builds a thin image `FROM` the base tag and runs it. `service :
Bool` — `False` ⇒ a one-shot `docker run --rm`; `True` ⇒ `cluster up` runs it
detached with `--restart unless-stopped`. `mounts` are bind mounts; `flavor` is
`cpu` or `cuda`. The container itself does any cluster bootstrap / image upload.
**No system unit is ever created** for this model.

This is the compose-replacement case — pure container apps with no cluster are
first-class. The win over compose is faster builds (the prebuilt base tag) plus
a default-pull / `--build-base` "pull-or-build-local" switch compose lacks.

```dhall
H.entry H.Substrate.LinuxCpu
  ( H.Model.Container
      H.Container::{
      , dockerfile = "docker/example.Dockerfile"
      , service = True
      , mounts =
        [ H.Mount::{ host = "./.data", container = "/opt/example/.data" }
        , H.Mount::{ host = "/var/run/docker.sock", container = "/var/run/docker.sock" }
        , H.Mount::{ host = "\${HOME}/.docker/config.json", container = "/root/.docker/config.json", ro = True }
        ]
      }
  )
```

### HostBinary

hostbootstrap builds a binary that runs **on the host** (Apple: native via
brew → ghcup; Linux: inside the base container, extracted to `.build/`), plus an
optional container counterpart. The binary owns its own lifecycle: `handoff`
declares `up` / `down` (and optional `delete`) commands that `cluster up` /
`cluster down` / `cluster delete` invoke. **hostbootstrap creates no system
unit** — the binary manages its own services (e.g. an RKE2 systemd unit it
installs).

```dhall
H.entry H.Substrate.LinuxCpu
  ( H.Model.HostBinary
      H.HostBinary::{
      , build = H.Build::{ cabal = "cabal install --installdir .build --install-method=copy --overwrite-policy=always exe:mgr" }
      , handoff = H.Handoff::{ up = ".build/mgr cluster up", down = ".build/mgr cluster down" }
      }
  )
```

### HostDaemon

A long-running **host-native** daemon (e.g. Apple-silicon Metal inference). This
is the **only** model with a `daemon` field — and it is **required**. `cluster
up` wraps the daemon command in a system-level unit: a **LaunchDaemon** in
`/Library/LaunchDaemons` on macOS (**never** a per-user LaunchAgent) or a
system-scope systemd unit on Linux — so it starts before any user logs in
(headless remote SSH). `cluster down` removes it.

```dhall
H.entry H.Substrate.AppleSilicon
  ( H.Model.HostDaemon
      H.HostDaemon::{
      , build =
          H.Build::{
          , cabal = "cabal install --installdir .build exe:infer"
          , host = H.HostReqs::{ ghc = True, tart = True, metal = True }
          }
      , daemon = ".build/infer inference --serve"
      }
  )
```

Because the `daemon` field exists **only** on `HostDaemon`, a system unit is
created **if and only if** a project declares that model — the rule is
structural, not a runtime check (illegal states are unrepresentable in the Dhall
types). See [`documents/engineering/schema.md`](documents/engineering/schema.md)
for the full type story.

---

## Command reference

| Command | What it does |
|---|---|
| `hostbootstrap doctor` | Detect substrate; validate + idempotently install host prereqs |
| `hostbootstrap build` | Idempotently build the project artifact for the current substrate |
| `hostbootstrap cluster up` | Bring the whole stack to running (build, then run the container / invoke the binary's `handoff up` / install the daemon unit) |
| `hostbootstrap cluster down` | Tear the cluster down — **never deletes host `.data`** |
| `hostbootstrap cluster delete` | Thorough teardown (cluster + derived state) — still preserves `.data` |
| `hostbootstrap run <cmd…>` | Build if needed, then dispatch to the binary or container per the substrate's model |
| `hostbootstrap base build` | Build a base tag locally (used inside this repo and by downstream `--build-base`) |
| `hostbootstrap base push` | Push a base tag to Docker Hub |

All commands are **idempotent**: re-running on a healthy host is a no-op.

---

## How the base images get built

Versions, download URLs, the architecture string, and the CUDA base image are
all resolved on the host by
[`hostbootstrap/base_image.py`](hostbootstrap/base_image.py) and passed via
`docker build --build-arg`. The Dockerfile
([`docker/basecontainer.Dockerfile`](docker/basecontainer.Dockerfile)) consumes
ARGs only — no `if`/`case`/version probing.

Plain `docker build`. No buildx, no emulation; a build can only ever produce the
host-native arch.

* **Default** for downstream projects: pull the base from Docker Hub.
* **`--build-base`**: build the base locally from this repo's Dockerfile,
  tagging it with the identical name.

---

## Repository layout

```
dhall/
  package.dhall                  # the typed project-config schema (imported by projects)
hostbootstrap/                   # the Python package (flat layout)
  cli.py                         # Click entrypoint
  substrate.py                   # apple-silicon | linux-cpu | linux-gpu
  prereqs.py                     # host prereq checks/installers
  spec.py                        # hostbootstrap.dhall → JSON → frozen dataclasses
  dhall_tool.py                  # provision/run native dhall-to-json
  process.py                     # async subprocess wrapper
  docker_ops.py                  # build/run arg-builders + runners
  base_image.py                  # version/URL/CUDA resolvers + build helpers
  units.py                       # system unit (LaunchDaemon / systemd) management
  check_code.py                  # ruff → black → mypy strict
  models/
    container.py
    host_binary.py
    host_daemon.py
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

* The host `.data` bind mount is preserved across `cluster down` and
  `cluster delete` — neither ever deletes it.
* A system unit is created **if and only if** a substrate uses the HostDaemon
  model. Such units are system-scope (systemd / LaunchDaemon), not user-scope
  LaunchAgents — so they survive a reboot and start pre-login (supporting
  headless remote SSH).
* `.build/` exists only for HostBinary / HostDaemon projects and is never
  bind-mounted into a container.

### Downstream guidance (conventions, not enforced)

* Run fourmolu/hlint **inside** the container — invoked by the project's
  Dockerfile against the prebuilt tools the base ships.
* Reach in-cluster services from a host binary over loopback (`127.0.0.0/8`)
  NodePorts only — never off-host.

See [`HOSTBOOTSTRAP_REFACTOR_PLAN.md`](HOSTBOOTSTRAP_REFACTOR_PLAN.md) for the
full motivation and acceptance criteria, and
[`documents/README.md`](documents/README.md) for the deep docs.
