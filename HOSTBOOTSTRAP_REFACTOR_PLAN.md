# hostbootstrap Refactor Plan

**Status**: Authoritative source — the reference all implementation work follows.
**Supersedes**: `scripts/build-and-push.sh` and the per-project ad-hoc bootstrap scripts.

> **Purpose**: Comprehensively describe the refactor of `basecontainer` into `hostbootstrap` — a
> small set of prebuilt base images plus one host-installed Python CLI that every sibling project
> adopts via a typed `hostbootstrap.dhall`. This document is a plan only; it changes no code.

---

## 1. Overview & goals

Today `basecontainer` builds a large multi-language container, and each sibling project independently
rebuilds the *same* heavy toolchain from `ubuntu:24.04` and carries its own ad-hoc `bootstrap/*.sh`
scripts and substrate logic. This refactor:

- **Renames** the project `basecontainer` → `hostbootstrap`.
- Publishes a small set of **prebuilt, arch-explicit base images** that contain the shared toolchain.
- Replaces every project's bootstrap shell scripts and bespoke build glue with **one host-installed
  Python CLI** (`hostbootstrap`), driven by a per-project **typed `hostbootstrap.dhall`**.

**Primary goals**

1. **Dramatically simpler per-project layout** — a project keeps only its own source, a thin
   `Dockerfile` that inherits from a base image, and a `hostbootstrap.dhall`.
2. **Accelerated builds** — the heavy toolchain lives in the pulled base image, so project
   (re)builds compile only project-specific code; cold builds are light, no reliance on cross-boundary
   build caches.
3. **A faster compose replacement, first-class.** hostbootstrap is **not** Kubernetes-presumptive. A
   pure-container application with **no cluster at all** is a first-class case: the prebuilt base image
   plus a default-pull / `--build-base` "pull-or-build-local" switch (something compose lacks) makes
   it a faster, simpler `docker compose` replacement. Cluster creation, Helm, and image upload are
   **downstream concerns**, used only by the projects that need them — never assumed by the tool.

---

## 2. Findings that motivate the refactor

The reviewed projects share a near-identical toolchain and differ along exactly one axis.

**Shared (moves into the base image / the tool):**
- GHC + Cabal (via ghcup), **fourmolu/hlint prebuilt**, Node/npm/PureScript, Python, a cluster tool
  belt (kind, kubectl, helm, docker CLI, skopeo, mc) for the **downstream** projects that need it,
  **nvkind** (Go-built), Playwright browsers, C/C++/LLVM, and optional CUDA.
- Per-substrate prerequisite checks: macOS arm64, Xcode CLT, Homebrew, docker-without-sudo, NVIDIA
  driver + container toolkit, Ubuntu 24.04, reboot gates.
- Typed (**Dhall**) configuration.

**The single varying axis — the execution model, chosen *per substrate*:**
1. **container** — hostbootstrap builds a thin image `FROM` the base tag and runs it (one-shot or a
   detached `unless-stopped` service). Any cluster/upload work is the container's own concern.
2. **host-binary** — a binary built and run directly on the host (e.g. a host cluster manager) with
   `handoff` commands the CLI invokes; the binary manages its own services (e.g. an RKE2 systemd unit
   it installs itself).
3. **host-daemon** — a binary plus a **required** `daemon` command for which `cluster up` creates a
   system-level service unit; the **only** model that creates a unit.

A project that must behave differently per substrate simply **declares a different model per
substrate** — there is no separate "multi-substrate" model. The Apple-silicon case (host-native
binary for direct hardware access: Swift in a **Tart** VM, GPU on **Metal**, which cannot run in a
container) is just a substrate that picks `host-binary` or `host-daemon`.

Consolidating the shared 90% into base images + a CLI, and declaring only the per-substrate model in a
small typed Dhall file, is the core of the simplification.

---

## 3. Repo rename & Docker Hub namespace

- Git repository `basecontainer` → **`hostbootstrap`** (`gh repo rename`, update remotes).
- Docker Hub namespace/repo → **`tuee22/hostbootstrap`**.
- Image tags use a `basecontainer-<flavor>-<arch>` scheme (see §4) so the `hostbootstrap` repo can
  also host other artifacts later without ambiguity.

---

## 4. Base container images

### Tag scheme (no multi-arch, ever)
Four single-arch images, arch always explicit in the tag:

```
docker.io/tuee22/hostbootstrap:basecontainer-cpu-amd64
docker.io/tuee22/hostbootstrap:basecontainer-cpu-arm64
docker.io/tuee22/hostbootstrap:basecontainer-cuda-amd64
docker.io/tuee22/hostbootstrap:basecontainer-cuda-arm64
```

There are **no manifest lists**. The tool always knows the substrate (hence the arch) and references
the one correct tag directly — both when pulling (default) and when building locally. Names are
identical in either case.

### Substrate → base-tag mapping (applied by the tool)
| Substrate | Base tag |
|---|---|
| `apple-silicon` | `basecontainer-cpu-arm64` (Metal GPU is host-native, never in the container) |
| `linux-cpu` (amd64) | `basecontainer-cpu-amd64` |
| `linux-cpu` (arm64) | `basecontainer-cpu-arm64` |
| `linux-gpu` (amd64) | `basecontainer-cuda-amd64` |
| `linux-gpu` (arm64) | `basecontainer-cuda-arm64` (built on demand only) |

### Contents & key changes
- **Single GHC version: 9.12.4** (with Cabal 3.16.1.0). One GHC serves both project builds and
  fourmolu/hlint, whose `ghc-lib-parser` targets 9.12 — so **no dual-GHC, no formatter-only GHC**.
  Downstream projects are refactored to standardize on 9.12.
- **fourmolu/hlint prebuilt** into the image (built once with the single GHC).
- **Warm Haskell store** (`support/haskell-deps/`) rebuilt against GHC 9.12, baked in so downstream
  Haskell builds skip recompiling the shared dependency closure.
- **Go is first-class**: the Go toolchain is installed in the final image with `GOPATH`, `GOCACHE`,
  `GOMODCACHE`, `GOTOOLCHAIN`, and `PATH` set alongside the other languages' conventions.
- **`nvkind` built in a single stage**: `CGO_ENABLED=1 go install …/nvkind@latest` runs natively in
  the final image (native gcc is present). The old `nvkind-builder` multistage + cross-compile logic
  is removed — native-only builds make it unnecessary.
- The remaining toolchain (Node/PureScript/Playwright, Python/Poetry bootstrap, kube tools, LLVM/
  C++ stack, optional CUDA) is preserved.

### Logic-free, POSIX-shell Dockerfile
`docker/basecontainer.Dockerfile` contains **no** `if`/`case`/bash version-resolution. Every value —
GHC/Cabal/Node/Go versions, download URLs, the architecture string, and the CUDA base image — is an
explicit `ARG` the Python tool computes and passes via `--build-arg`. The Dockerfile only consumes
ARGs. Additional hard rules (mirrored in the §15 acceptance criteria):

- **No `/bin/bash`** — no `SHELL` directive; `RUN` steps use the default POSIX `/bin/sh`.
- **No pipes** in `RUN` steps, **no `docker-buildx`**, and **no `--jobs=1`**.
- **Single documented exception:** the `if [ -d /usr/local/cuda/lib64 ]` ldconfig block is kept.
  Rationale: one Dockerfile serves **both** the cpu (`ubuntu:24.04`) and cuda (`nvidia/cuda`) bases
  via the `BASE_IMAGE` arg; this is a **build-time filesystem check** (does the CUDA libdir exist?)
  that needs no GPU, driver, or runtime — so the cuda image still builds on a host with no CUDA
  hardware.

### Dynamic CUDA base resolution (in the tool, not the Dockerfile)
`base_image.py` ports the existing `resolve_latest_cuda_base_image()` logic to Python: query Docker
Hub for `nvidia/cuda` tags matching `*cudnn-devel-ubuntu24.04`, choose the **latest** version that
carries the full build stack and has a manifest for the target arch, and pass it as
`--build-arg BASE_IMAGE=…`. (CPU flavor's base arg is simply `ubuntu:24.04`.)

### Build mechanics
- Plain `docker build` only — **no buildx, no emulation**; a build can only ever produce the
  host-native arch.
- **Default**: downstream consumers **pull** the base from Docker Hub.
- **`--build-base`**: build the base locally, fetching `basecontainer.Dockerfile` from the
  hostbootstrap GitHub repo, tagging it with the identical name.

---

## 5. Repo layout

```
hostbootstrap/                          # (renamed from basecontainer)
  HOSTBOOTSTRAP_REFACTOR_PLAN.md        # this document
  README.md                             # adoption guide (no project names) — see §12
  pyproject.toml                        # Poetry; [tool.poetry.scripts] hostbootstrap, check-code
  poetry.toml                           # [virtualenvs] in-project = true  (DEV use only)
  hostbootstrap/                        # flat package (shipnorth-style; pip-installable + poetry-dev)
    __init__.py
    cli.py                              # Click app; `hostbootstrap` entrypoint
    substrate.py                        # detect apple-silicon | linux-cpu | linux-gpu (frozen models)
    prereqs.py                          # validate + idempotently install host prerequisites
    spec.py                             # load/validate hostbootstrap.dhall; fail-fast (residual checks)
    dhall_tool.py                       # provision dhall-to-json (PATH or pinned static release)
    units.py                            # create/remove system-level units (LaunchDaemon / systemd)
    process.py                          # async subprocess wrapper (asyncio.create_subprocess_exec)
    docker_ops.py                       # build / run (pure arg-builders + async runners)
    base_image.py                       # resolve versions/URLs/CUDA; pull-or-build the 4 base tags
    models/
      __init__.py
      container.py                      #   build thin image FROM base; one-shot or detached service
      host_binary.py                    #   apple: host cabal; linux: build-in-base-container, extract
      host_daemon.py                    #   build binary; cluster up creates a system-level unit
    check_code.py                       # ruff → black → mypy(strict), fail-fast
  dhall/
    package.dhall                       # shipped Dhall package projects import (types + helpers)
  docker/
    basecontainer.Dockerfile            # logic-free POSIX /bin/sh; all values via ARG
  support/
    haskell-deps/                       # warm Cabal store (rebuilt against GHC 9.12)
  documents/                            # SSoT documentation tree
    documentation_standards.md          # authoritative doc standards (shipnorth style)
    README.md                           # documents index
    engineering/                        # base image, build/release, prerequisites, gitignore
      schema.md                         #   full hostbootstrap.dhall schema: field tables + examples
    languages/                          # haskell, python, node, purescript, playwright, rust, cpp,
                                        #   cuda, go, cluster_tooling  (per-language guidance)
  stubs/                                # custom .pyi (likely empty; ready for mypy_path)
```

---

## 6. The hostbootstrap CLI & package

A single Click application, installed on the host (downstream) or run via Poetry (repo dev).

### Command tree
The default config path is **`hostbootstrap.dhall`**.

- `hostbootstrap doctor` — detect substrate; validate + idempotently install host prerequisites
  declared/needed by the project's `hostbootstrap.dhall`.
- `hostbootstrap build` — idempotently build the project artifact for the current substrate's model
  (a thin container image and/or a host binary), reusing container/build caches so no unnecessary work
  is done.
- `hostbootstrap cluster up` — idempotently bring the stack to "running": build the artifact, then
  dispatch by the substrate's model — a `container` service is run detached `unless-stopped`; a
  `host-binary` runs its `handoff.up`; a `host-daemon` gets a system-level unit created (§9). Safe to
  re-run. Cluster/Helm/image-upload are **downstream** concerns owned by the project's binary/container.
- `hostbootstrap cluster down` — reverse `up`: `container` ⇒ `docker rm -f`; `host-binary` ⇒
  `handoff.down`; `host-daemon` ⇒ remove the unit. **Never deletes host `.data`.**
- `hostbootstrap cluster delete` — a more thorough teardown (`host-binary` ⇒ `handoff.delete`, plus
  derived state). **Still never deletes host `.data`.**
- `hostbootstrap run <command...>` — the unified entrypoint replacing `docker compose run …` and
  `.build/<binary> …`. Idempotently triggers `cluster up` (which only rebuilds when something actually
  changed), then dispatches `<command>` to the host binary or into the container per the substrate's
  model (§9).
- `hostbootstrap base build | base push` — produce/publish the four base tags (used inside the
  hostbootstrap repo and by `--build-base`). (This is the **only** `push`; there is no
  `hostbootstrap push`.)
- `check-code` — separate entrypoint for repo development.

### Style
- **Functional / declarative**: `@dataclass(frozen=True)` for substrate, spec, command results;
  `typing.Final` for constants; pure functions that *build* command argument lists, separated from
  the effectful async runners; `asyncio.gather` for independent concurrent work.
- **`process.py`**: `async def run(cmd, *, cwd=None, env=None) -> CommandResult` over
  `asyncio.create_subprocess_exec`, streaming stdout/stderr, returning a frozen result; a
  `run_checked` variant raises a typed `CommandError` on non-zero exit (fail-fast).

---

## 7. Substrate detection & host prerequisites

`substrate.py` detects one of: **`apple-silicon`**, **`linux-cpu`**, **`linux-gpu`** (Darwin arm64;
Linux without NVIDIA GPU; Linux with NVIDIA GPU). `prereqs.py` then validates and **idempotently**
installs only what the substrate + config require, absorbing the projects' existing `bootstrap/*.sh`
checks.

- **apple-silicon** — require macOS arm64, Xcode Command Line Tools, passwordless sudo, and
  **Homebrew**; using **brew only**, install ghcup + the pinned GHC/Cabal (when a host binary is
  built) and a **Tart** VM (when the config needs it). **Docker / Colima**: hostbootstrap does **not**
  install or modify the Colima VM. It **validates** that a Colima-backed Docker VM exists **and is
  configured to start at the system level before the user logs in** (see the headless remote SSH note
  below). If either check fails (no Colima VM, or its launchd setup is user-only), **fail fast** with
  precise instructions for the user to fix. Fail fast with precise instructions if any other hard
  prerequisite (Xcode CLT, passwordless sudo) is absent.
- **linux-cpu** — validate **Ubuntu 24.04** and **passwordless sudo**; idempotently install Docker
  and configure non-sudo access (mirroring the existing bootstrap logic). Everything else on Linux
  happens in containers.
- **linux-gpu** — the above plus idempotent install of GPU drivers and the **NVIDIA container
  toolkit**; configure the Docker runtime; **prompt reboot** when required (e.g. after driver/docker
  install) and exit with a clear "re-run after reboot" message.

Re-running `doctor` is always a no-op when prerequisites are already satisfied.

**Passwordless sudo is a hard prerequisite on every substrate — both Linux and macOS.** The tool
needs it for: apt installs (Docker, GPU drivers, NVIDIA container toolkit) and Docker group/runtime
configuration on Linux; brew installs (Tart, ghcup) on macOS; and, on either OS, creating/destroying
**system-level** service units — systemd units (Linux) or **LaunchDaemons** (macOS) — for host-level
daemons on `cluster up`/`cluster down` (§9.4). Missing passwordless sudo is a fail-fast condition
with precise instructions on how to grant it.

**Headless remote SSH robustness (macOS).** hostbootstrap-configured services must work in setups
where local disk encryption (FileVault) is **off** and the user may reboot the machine remotely and
SSH in **before any GUI login**. Under such setups, two things must come up **before user login**:
(a) the **Colima VM** (which is why `doctor` validates that it is configured for system-level start,
not user-level), and (b) any host-daemon unit the tool installs — which on macOS must therefore be a
**LaunchDaemon** in `/Library/LaunchDaemons/`, **never** a per-user LaunchAgent (and on Linux a
**system-scope** systemd unit, not a user-scope one). If a Colima VM exists but is configured to
start only after user login, `doctor` fails fast with precise instructions to reconfigure it for
system-level start.

---

## 8. `hostbootstrap.dhall` (per downstream project)

The per-project config is **typed Dhall**, not YAML. Each project ships a `hostbootstrap.dhall` that
**imports the Dhall package this repo publishes** at `dhall/package.dhall` (types + helpers). The tool
**fails fast** if the file is missing, and again if the detected substrate is not declared.

> **Full schema — field tables and worked per-model examples — lives in
> [`documents/engineering/schema.md`](documents/engineering/schema.md).** This section gives only the
> design shape; do not duplicate the field reference here.

### Design shape (Dhall makes illegal states unrepresentable)
A project declares, **per substrate** (`apple-silicon` | `linux-cpu` | `linux-gpu`), exactly one
execution **model** drawn from a **tagged union** of three alternatives. Each alternative carries only
the fields that are meaningful for it — so the Dhall type system makes whole classes of mistake
**impossible to even write**:

- **container** — `service : Bool` (false ⇒ one-shot `docker run --rm`; true ⇒ a detached
  `--restart unless-stopped` service), `mounts` (bind mounts), and `flavor : <Cpu | Cuda>`. The
  container owns any cluster/upload work. **Never** creates a system unit.
- **host-binary** — an optional container counterpart and a `handoff` record `{ up, down, delete? }`
  of commands that `cluster up/down/delete` run. The binary manages its own services (e.g. an RKE2
  systemd unit it installs itself). **No** system unit from hostbootstrap.
- **host-daemon** — a **required** `daemon` command. `cluster up` creates a system-level unit and
  `cluster down` removes it. This is the **only** model with a `daemon` field and the **only** model
  that creates a unit.

Because of how the union is typed:
- a `daemon` field exists **iff** the model is `host-daemon` (and is required there) ⇒ **a unit exists
  iff host-daemon**;
- `service`/`mounts` exist **only** on `container`; `handoff` exists **only** on `host-binary`;
- `flavor` is the closed enum `<Cpu | Cuda>`.

The only checks left to Python (in `spec.py`) are the two that Dhall's structure cannot express: **no
duplicate substrate**, and **the detected substrate must be declared**. Everything else fails fast as
a Dhall type error or a `SpecError`.

There is **no `multi-substrate` model.** A project that behaves differently per substrate simply
declares a different model for each substrate (e.g. `linux-*` ⇒ `container`, `apple-silicon` ⇒
`host-daemon`).

---

## 9. Cluster lifecycle, the `run` command, and execution models

### 9.1 Why the CLI replaces docker-compose
For **container**-model projects — including pure-container apps with **no cluster at all**, where
hostbootstrap is simply a faster `docker compose` — the CLI fully replaces `compose.yaml`. Compose is
the wrong tool here because it:
- has **no "pull the base image, or build it locally from a GitHub Dockerfile" switch** (our
  default-pull / `--build-base` behavior, §4) — the single biggest build-speed win;
- does **not handle per-substrate models** cleanly, where the same project runs as a host binary or
  host daemon (Apple silicon) and as a container (Linux);
- cannot express the idempotent **build → dispatch-by-model** lifecycle below.

The CLI drives the Docker CLI directly instead. Note that the pure-container compose-replacement case
involves **no cluster, no Helm, and no image upload** — those are downstream concerns reserved for the
projects that opt into them.

### 9.2 Cluster lifecycle & the unified `run` command
Three lifecycle verbs, all idempotent. Each one **builds, then dispatches by the substrate's model**:

- **`cluster up`** — (a) idempotently build the artifact for the model (a thin container image and/or a
  host binary), reusing container + build caches (no unnecessary work); (b) dispatch:
  - **container** with `service: true` ⇒ run it **detached** with `--restart unless-stopped`
    (`service: false` containers are one-shot via `run`, not a service);
  - **host-binary** ⇒ run `handoff.up`; the binary owns its own cluster/services (e.g. installs its
    own RKE2 systemd unit);
  - **host-daemon** ⇒ create the **system-level unit** (§9.4) that supervises the `daemon` command.
- **`cluster down`** — reverse `up`: **container** ⇒ `docker rm -f`; **host-binary** ⇒ `handoff.down`;
  **host-daemon** ⇒ remove the unit. **Never deletes host `.data`.**
- **`cluster delete`** — a more thorough teardown: **host-binary** ⇒ `handoff.delete` (plus derived
  state). **Still never deletes host `.data`.**

Any cluster creation, Helm, and image upload are **downstream responsibilities** owned by the
project's binary or container — hostbootstrap never assumes Kubernetes.

`hostbootstrap run <command>` is the single entrypoint that replaces both
`docker compose run --rm <project> <service> <command>` and `.build/<binary> <command>`. It
**idempotently triggers `cluster up`** (which only rebuilds when something actually changed), then
dispatches `<command>` to the host binary or into the container according to the substrate's model.

### 9.3 Long-running containers, restart policy, and bind mounts
When the CLI starts long-running containers it does so as **detached background tasks with an
`unless-stopped` restart policy**, so the Docker daemon brings them back after a host reboot — exactly
the behavior projects expect today. The CLI persistently bind-mounts what the `container` model's
`mounts` declares (the `.data` directory, the Docker socket, docker config, …); these are **specified
in `hostbootstrap.dhall` (§8), not hard-coded**. One-shot `hostbootstrap run <command>` invocations
use `--rm`; `service: true` containers use `--restart unless-stopped`.

Invariants:
- **The host `.data` bind-mount is always maintained whenever the cluster is running.**
- **`.build/` exists on the host only when a host binary is built**, and is **never** bind-mounted
  into a container. `container`-model projects keep no host `.build/` — their source is COPYed into
  the thin image at build time (§4, §9.5).

### 9.4 The `host-daemon` model & its system unit (systemd / launchd)
The **`host-daemon`** model is for a daemon that runs **on the host**, not under Docker — typically an
Apple-silicon inference daemon that requires **Metal**. It is the **only** model with a `daemon` field
(required), and the unit is created by `units.py`. The called binary is responsible for running
forever once invoked (long-running host inference is the binary's job, not the CLI's).

Because the Docker daemon does not manage these host processes, they would not survive a reboot. To
match the `unless-stopped` behavior of containerized services, the contract is:

> **`cluster up` idempotently creates a system-level service unit — a system-scope systemd unit on
> Linux (`/etc/systemd/system/`) or a **LaunchDaemon** on macOS (`/Library/LaunchDaemons/`, *never* a
> per-user LaunchAgent) — if-and-only-if the substrate's model is `host-daemon`; `cluster down`
> removes it. A unit exists *iff* host-daemon — guaranteed at the Dhall type level, since `daemon`
> exists only on that model (§8).**

System-level placement is required so the daemon starts at boot **before any user logs in**,
supporting headless remote SSH workflows (§7). Managing these units is **why passwordless sudo is
required** (§7). After a reboot the unit restarts the daemon automatically, pre-login. This mechanism
applies **only** to the `host-daemon` model — `container` services are handled by the Docker daemon's
restart policy, and `host-binary` binaries manage their own services.

### 9.5 The three execution models (chosen per substrate)
- **container** — the CLI builds a thin image `FROM` the base tag and runs it via `docker run`
  (detached + `--restart unless-stopped` when `service: true`; `--rm` for one-shot `run` commands),
  applying the model's `mounts` (including `.data`). No `compose.yaml`. Project source is COPYed into
  the thin image at build time (no code bind-mount); cold builds stay light because the heavy base is
  pulled, not rebuilt. The container owns any cluster/upload work it needs; a pure-container app with
  no cluster is the first-class compose-replacement case.
- **host-binary** — **Apple silicon**: build with host `cabal` (GHC/Cabal via brew→ghcup); hot
  rebuilds kept for efficiency; Swift in a **Tart** VM; GPU on **Metal**, host-native. **Linux**:
  build the binary **inside the base container** and extract it to the host (keeps the toolchain off
  the Linux host); a persistent build dir keeps cabal rebuilds incremental. The host `.build/` holds
  the binary. An optional container counterpart may also be built. `cluster up/down/delete` invoke the
  model's `handoff` commands; the binary manages its own services (e.g. an RKE2 systemd unit).
- **host-daemon** — build the binary (+ optional container counterpart); `cluster up` creates the
  system-level unit (§9.4) that supervises the required `daemon` command — typically an Apple-silicon
  host-native daemon for direct hardware access (Tart for Swift, Metal for GPU) that cannot run in a
  container. A project that wants a clustered counterpart simply also declares a `container` model on
  the Linux substrates and ships/uploads that image as its **own** downstream responsibility.

### 9.6 Downstream guidance: fourmolu/hlint (not tool-enforced)
fourmolu/hlint are best kept **container-only** — not installed, built, or run on the host — even for
`host-binary`/`host-daemon` projects, since the base container ships them **prebuilt**. This is
**downstream guidance, not a hostbootstrap-enforced invariant**: `hostbootstrap` does not invoke
fourmolu/hlint at all. Invoking them is the **project's Dockerfile**'s responsibility (e.g. a
build-time `RUN` over the COPYed source, or a container entrypoint subcommand); the project owns when
and how the quality checks actually run.

### 9.7 Downstream guidance: containerized counterpart, upload, and loopback exposure
The following are **patterns a downstream project may adopt — not behaviors hostbootstrap enforces:**

- A `host-daemon` substrate may **also** declare a `container` model on its Linux substrates and ship
  that as a clustered counterpart of the same binary. Building/uploading that image is the project's
  **own** responsibility (hostbootstrap does no image upload — there is no `push` command, §6).
- A project that runs container-side quality checks does so in **its** Dockerfile, using the prebuilt
  tools the base ships — the single canonical place to run them (§9.6).
- A host binary acting as a control plane should reach in-cluster services (e.g. **MinIO**, **Pulsar**,
  its own counterpart) over **NodePorts bound to `127.0.0.1` / `127.0.0.0/8` — localhost only.** This
  loopback-only exposure is an important security boundary (cluster services must **never** be
  reachable off-host) — but it is the **project's** cluster config that enforces it, not the tool.

**Division of labor:** `hostbootstrap` builds artifacts and orchestrates the per-model lifecycle
(`cluster up/down/delete`, `run`); **cluster creation, Helm, and image upload are downstream
concerns** owned entirely by the project's binary or container. The tool is not Kubernetes-presumptive.

---

## 10. Install-mode isolation

- **Downstream projects** install the tool into **host Python** via `python -m pip install git+…`
  (pointing at the hostbootstrap repo / `pyproject.toml`). **Not** into any virtualenv.
- **The hostbootstrap repo itself** uses Poetry with an **in-project `.venv`** (`poetry.toml`
  `virtualenvs.in-project = true`) — for developing hostbootstrap, running `check-code`, and building/
  pushing the base images.
- **Critical isolation**: projects that maintain their own host-level `.venv` (e.g. ML-inference
  Python adapters) must **never** add `hostbootstrap` to that venv. By bootstrap time the tool's job
  is done; it has no place inside a project's runtime environment.

**Pure-Python install + native `dhall-to-json` provisioning.** The `pip install git+…` is
**pure-Python** — there is **no `dhall` PyPI dependency** (no cp312 wheel exists; it would require a
Rust build). To parse the config, `dhall_tool.py` provisions a native **`dhall-to-json`** binary the
same way §2/§4 provision other tooling: prefer one already on `PATH` (e.g. `brew install dhall-json`),
else download the **pinned, SHA256-verified** static release for the platform
(`aarch64-darwin` / `x86_64-darwin` / `x86_64-linux`) into `~/.cache/hostbootstrap/`. **Ubuntu-arm64
has no prebuilt asset** (brew/source fallback — a documented limitation, consistent with this plan
already treating linux-arm64 as on-demand-only).

---

## 11. check-code & tooling config

Mirror the shipnorth standards exactly in `pyproject.toml`:
- `[tool.ruff]` — line-length 100, target py312, the same `select`/`ignore` lint sets.
- `[tool.black]` — line-length 100, py312.
- `[tool.mypy]` — **fully strict**: `strict = true` **plus** `disallow_any_explicit = true` (and
  `disallow_untyped_defs`, …), `mypy_path = "stubs"`. No `Any` may be written explicitly anywhere.
- `check_code.py` runs **ruff → black → mypy** over `hostbootstrap/` (and `stubs/`), fail-fast,
  returning the first non-zero exit code.
- Python is pinned **`>=3.12`**. Dev/runtime deps pinned `>=X,<Y`: runtime `click`, `httpx`; dev
  `ruff`, `black`, `mypy`. **`pyyaml` is dropped**, and there is **no `dhall` Python dependency** — the
  config is parsed via the provisioned native `dhall-to-json` (§10).

---

## 12. Documentation strategy

- `documents/` is the SSoT tree; **`documents/documentation_standards.md`** is authoritative and
  modeled on shipnorth's (snake_case file names except `README.md`/`AGENTS.md`/`CLAUDE.md`; required
  header metadata; WRONG/RIGHT examples; link liberally).
- Per-language guidance (including a new **`languages/go.md`**) and engineering references
  (base image, build/release, prerequisites, gitignore guardrails) migrate out of the current
  monolithic README into `documents/`.
- **`documents/engineering/schema.md`** is the authoritative reference for `hostbootstrap.dhall`:
  the full per-model field tables and worked examples (§8 links to it rather than duplicating it). It
  documents the shipped **`dhall/package.dhall`** package that projects import.
- **`README.md` becomes a concise adoption guide**: what a project must do to adopt the hostbootstrap
  way and author its `hostbootstrap.dhall` (importing `dhall/package.dhall`), described through the
  three model **archetypes** (container, host-binary, host-daemon) **without naming any specific
  project**.
- Per-project ad-hoc `.sh` build/bootstrap scripts are deleted as each project migrates.

---

## 13. Per-project migration mapping (internal reference; names excluded from README)

| Project | Substrates | Model | Notes |
|---|---|---|---|
| `mattandjames` | linux-cpu (+arm64) | container | drop `compose.yaml`; inherit base; run via `docker run` + socket |
| `prodbox` | linux-cpu | host-binary | manages host cluster; Linux build-in-base-container, extract binary; `handoff` up/down/delete |
| `mcts` | linux-cpu, linux-gpu | container | drop in-Dockerfile Python/Node/Playwright; keep C++/SCons/pybind11 + FastAPI/React layers |
| `jitML` | linux-cpu, linux-gpu, apple-silicon | container (linux) / host-daemon (apple) | Linux container; Apple host-native Tart/Metal daemon; absorb `bootstrap/*.sh` into `doctor` |
| `infernix` | linux-cpu, linux-gpu, apple-silicon | container (linux) / host-daemon (apple) | as above; **Apple-silicon daemon still WIP**; preserve its own python adapters `.venv` (isolation) |

All projects standardize Haskell on **GHC 9.12** as part of migration.

---

## 14. Risks & constraints

1. **GHC standardization effort** — projects currently on GHC 9.14.1 must refactor to 9.12; validate
   each builds and that the warm Haskell store + fourmolu/hlint remain compatible.
2. **Loss of buildx SBOM/provenance** — plain `docker build` does not emit the attestation manifests
   buildx produced. Accepted.
3. **No `dhall-to-json` asset for ubuntu-arm64** — the pinned static release covers `aarch64-darwin`,
   `x86_64-darwin`, and `x86_64-linux` only; linux-arm64 falls back to brew/source. A documented
   limitation, consistent with treating linux-arm64 as on-demand-only.
4. **`cuda-arm64`** — supported by the naming scheme but built only on demand (GPU projects are
   amd64 in practice).
5. **CUDA drift** — dynamic resolution always pulls the latest `cudnn-devel-ubuntu24.04`; a project
   pinned to an older CUDA must override the resolved base arg explicitly.

---

## 15. Verification / acceptance criteria

- A clean host `python -m pip install git+…` is **pure-Python** and exposes `hostbootstrap`; running
  it in a project with no `hostbootstrap.dhall` **fails fast** with a clear message; an unsupported
  substrate also fails fast. The config imports `dhall/package.dhall`, and a native `dhall-to-json` is
  provisioned (from `PATH` or a pinned, SHA256-verified static release) with **no `dhall` Python dep**.
- `hostbootstrap doctor` detects the substrate correctly and validates/installs prerequisites
  **idempotently** (re-run is a no-op; reboot-required paths exit with guidance).
- `hostbootstrap build` pulls the correct `basecontainer-<flavor>-<arch>` and compiles **only project
  code** — a warm-base cold build is dramatically faster than today's from-scratch build (measure it).
- `--build-base` reproduces a base tag locally under the identical name; `docker images` shows the
  arch-explicit tag; **no manifest list** exists anywhere.
- A pure-`container` project (no cluster) runs via `docker run` and **no `compose.yaml`** — the
  compose-replacement case works with no Kubernetes, Helm, or image upload.
- `cluster up` builds, then dispatches by model: a `service: true` **container** runs detached; a
  **host-binary** runs `handoff.up`; a **host-daemon** gets its system unit. `down`/`delete` reverse
  it (`docker rm -f` / `handoff.down`/`handoff.delete` / remove unit).
- `cluster up`/`down`/`delete` are idempotent and **never delete host `.data`**; `.data` stays
  bind-mounted the entire time the cluster is running.
- `hostbootstrap run <command>` idempotently triggers `cluster up` (rebuilding only when needed) and
  dispatches the command to the host binary or container per the substrate's model.
- Long-running `container` services are started detached with `--restart unless-stopped` and survive a
  host reboot; one-shot `run` invocations use `--rm`.
- `cluster up` creates a **system-level** service unit — a system-scope systemd unit (Linux) or a
  **LaunchDaemon** in `/Library/LaunchDaemons/` (macOS, **never** a per-user LaunchAgent) — **iff** the
  substrate's model is `host-daemon`; `cluster down` removes it. A unit exists iff host-daemon
  (guaranteed at the Dhall type level, since `daemon` exists only on that model). After reboot, the
  unit restarts the daemon automatically **before user login** (supporting headless remote SSH).
- On macOS, hostbootstrap **does not** install or modify the Colima VM. `doctor` **validates** that a
  Colima-backed Docker VM exists **and** is configured to start at system level before user login; if
  either check fails, it fails fast with precise remediation instructions.
- A host `.build/` exists only for `host-binary`/`host-daemon` projects and is **never** bind-mounted
  into a container.
- There is **no `hostbootstrap push` command and no `harbor.py`** — image upload (and any cluster/Helm
  work) is the downstream binary's/container's responsibility, documented as guidance only.
- Downstream guidance (not tool-enforced) holds: fourmolu/hlint are invoked by the **project's
  Dockerfile** using the **prebuilt** tools the base ships — never on the host; a control-plane host
  binary reaches in-cluster services (MinIO, Pulsar, its own counterpart) only over loopback
  (`127.0.0.0/8`) NodePorts via the **project's** cluster config.
- Host-binary: Apple builds on host; Linux builds in-container and extracts a runnable binary;
  `handoff` up/down/delete drive the lifecycle; fourmolu/hlint never appear on the host.
- `poetry run check-code` passes (ruff/black/**fully-strict** mypy with `disallow_any_explicit`) in
  the hostbootstrap repo; downstream projects' own `.venv`s remain free of hostbootstrap; **`pyyaml`
  is absent**.
- The base Dockerfile contains no `if`/`case`/version-resolution logic and uses the **default POSIX
  `/bin/sh`** (no `SHELL`/`/bin/bash`), **no pipes**, **no `docker-buildx`**, **no `--jobs=1`**; the
  **sole** exception is the `if [ -d /usr/local/cuda/lib64 ]` ldconfig block (a build-time filesystem
  check serving both the cpu and cuda `BASE_IMAGE`s, needing no GPU/driver/runtime). All versioned
  values arrive as build args; a single GHC 9.12.4 (Cabal 3.16.1.0) is present; `nvkind` is built in a
  single stage with a first-class Go toolchain.
- `documents/documentation_standards.md` exists; `README.md` reads as a model-archetype adoption
  guide naming no specific project.

---

## 16. Test suite (sketch)

The code deliberately separates **pure functions that build command-argument lists / resolve values**
from the thin effectful async runners, so the suite is a **thin pyramid weighted to fast, hermetic
tests**. Full detail lives in [`documents/engineering/testing.md`](documents/engineering/testing.md);
the shape:

- **One entry point — `poetry run test-all`** (`hostbootstrap/test_all.py`). Running `pytest`
  directly is **refused** by `tests/conftest.py` (it requires a sentinel `test-all` sets), so there is
  one supported command and configuration. `check-code` (ruff/black/mypy) stays separate.
- **Pure unit tests (the bulk; no network/docker/sudo):** `docker_ops` command tuples, `base_image`
  tag/URL builders + JSON narrowers (HTTP `monkeypatch`ed), `units` systemd/launchd text, `substrate`
  detection, `dhall_tool` provisioning (in-memory tarball + checksum-mismatch), and the `models`
  path/mount/command helpers.
- **Dhall contract tests (the high-value layer):** drive `spec.load` through the real `dhall-to-json`
  against `tests/fixtures/dhall/{valid,invalid}/` — the five archetypes load to the right dataclasses
  and the four illegal configs (`daemon` on a `Container`, missing `daemon`, `mounts` on a
  `HostBinary`, bad `flavor`) raise `SpecError`. This is the executable form of the §8
  illegal-states-unrepresentable promise and a contract check of `dhall/package.dhall`. Parsing is
  also tested against crafted JSON with no Dhall.
- **Integration / smoke (thin, gated):** Click `CliRunner` smoke (command tree, no `push`, clean
  errors); model dispatch via a recorded-`process` fixture (asserts the exact `docker`/`cabal` argv,
  no daemon); a real-docker e2e behind the `docker` marker.
- **Markers `dhall` / `docker` / `slow`** skip cleanly when their requirement is absent, so a default
  run is hermetic and green; CI opts into the gated layers. Real systemd/launchd unit creation (root)
  and `doctor` host mutation are left to manual/CI-on-a-VM.
