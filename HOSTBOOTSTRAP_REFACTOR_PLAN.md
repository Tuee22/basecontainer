# hostbootstrap Refactor Plan

**Status**: Authoritative source — the reference all implementation work follows.
**Supersedes**: `scripts/build-and-push.sh` and the per-project ad-hoc bootstrap scripts.

> **Purpose**: Comprehensively describe the refactor of `basecontainer` into `hostbootstrap` — a
> small set of prebuilt base images plus one host-installed Python CLI that every sibling project
> adopts via a `hostbootstrap.yaml`. This document is a plan only; it changes no code.

---

## 1. Overview & goals

Today `basecontainer` builds a large multi-language container, and each sibling project independently
rebuilds the *same* heavy toolchain from `ubuntu:24.04` and carries its own ad-hoc `bootstrap/*.sh`
scripts and substrate logic. This refactor:

- **Renames** the project `basecontainer` → `hostbootstrap`.
- Publishes a small set of **prebuilt, arch-explicit base images** that contain the shared toolchain.
- Replaces every project's bootstrap shell scripts and bespoke build glue with **one host-installed
  Python CLI** (`hostbootstrap`), driven by a per-project **`hostbootstrap.yaml`**.

**Primary goals**

1. **Dramatically simpler per-project layout** — a project keeps only its own source, a thin
   `Dockerfile` that inherits from a base image, and a `hostbootstrap.yaml`.
2. **Accelerated builds** — the heavy toolchain lives in the pulled base image, so project
   (re)builds compile only project-specific code; cold builds are light, no reliance on cross-boundary
   build caches.

---

## 2. Findings that motivate the refactor

The reviewed projects share a near-identical toolchain and differ along exactly one axis.

**Shared (moves into the base image / the tool):**
- GHC + Cabal (via ghcup), **fourmolu/hlint prebuilt**, Node/npm/PureScript, Python, the Kubernetes
  tool belt (kind, kubectl, helm, docker CLI, skopeo, mc), **nvkind** (Go-built), Playwright
  browsers, C/C++/LLVM, and optional CUDA.
- Per-substrate prerequisite checks: macOS arm64, Xcode CLT, Homebrew, docker-without-sudo, NVIDIA
  driver + container toolkit, Ubuntu 24.04, reboot gates.
- Kind + Harbor + Helm umbrella charts; typed (Dhall) configuration.

**The single varying axis — the execution model:**
1. **Outer container** — a CLI runs inside a container with the Docker socket forwarded, orchestrating
   Kind/Harbor/Helm.
2. **Host binary** — a binary built and run directly on the host (e.g. a host cluster manager); no
   outer container.
3. **Multi-substrate** — a containerized daemon pushed to Harbor on Linux substrates, **plus** an
   Apple-Silicon host-native binary for direct hardware access (Swift in a **Tart** VM, GPU on
   **Metal**) that cannot run in a container.

Consolidating the shared 90% into base images + a CLI, and declaring only the varying model in a
small YAML file, is the core of the simplification.

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
- **Single GHC version: 9.12.x** (with Cabal 3.16.x). One GHC serves both project builds and
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

### Logic-free Dockerfile
`docker/basecontainer.Dockerfile` contains **no** `if`/`case`/bash version-resolution. Every value —
GHC/Cabal/Node/Go versions, download URLs, the architecture string, and the CUDA base image — is an
explicit `ARG` the Python tool computes and passes via `--build-arg`. The Dockerfile only consumes
ARGs.

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
    spec.py                             # load/validate hostbootstrap.yaml; fail-fast
    process.py                          # async subprocess wrapper (asyncio.create_subprocess_exec)
    docker_ops.py                       # build / run / push (pure arg-builders + async runners)
    base_image.py                       # resolve versions/URLs/CUDA; pull-or-build the 4 base tags
    harbor.py                           # arch-explicit push; clean / no-orphan enforcement
    models/
      __init__.py
      outer_container.py                #   docker run + socket forward (replaces compose)
      host_binary.py                    #   apple: host cabal; linux: build-in-base-container, extract
      multi_substrate.py                #   linux daemon→Harbor + apple host-native (Tart/Metal)
    check_code.py                       # ruff → black → mypy(strict), fail-fast
  docker/
    basecontainer.Dockerfile            # logic-free; all values via ARG
  support/
    haskell-deps/                       # warm Cabal store (rebuilt against GHC 9.12)
  documents/                            # SSoT documentation tree
    documentation_standards.md          # authoritative doc standards (shipnorth style)
    README.md                           # documents index
    engineering/                        # base image, build/release, prerequisites, harbor, gitignore
    languages/                          # haskell, python, node, purescript, playwright, rust, cpp,
                                        #   cuda, go, cluster_tooling  (per-language guidance)
  stubs/                                # custom .pyi (likely empty; ready for mypy_path)
```

---

## 6. The hostbootstrap CLI & package

A single Click application, installed on the host (downstream) or run via Poetry (repo dev).

### Command tree
- `hostbootstrap doctor` — detect substrate; validate + idempotently install host prerequisites
  declared/needed by the project's `hostbootstrap.yaml`.
- `hostbootstrap build` — idempotently build the project artifact for the current substrate (custom
  container or host binary), reusing container/build caches so no unnecessary work is done.
- `hostbootstrap push` — idempotently push the arch-explicit custom image to Harbor (never re-pushing
  the large base image; no orphans).
- `hostbootstrap cluster up` — idempotently bring the whole stack to "running": build the artifact
  (a), bootstrap the Kind/k8s cluster per the yaml (b), build & push the custom image to Harbor (c),
  and start any declared host-level daemon (d). Safe to re-run.
- `hostbootstrap cluster down` — tear the cluster down; stop/remove the long-running containers and
  any host daemon (and its systemd/launchd unit). **Never deletes host `.data`.**
- `hostbootstrap cluster delete` — a more thorough teardown (cluster plus derived state). **Still
  never deletes host `.data`.**
- `hostbootstrap run <command...>` — the unified entrypoint replacing `docker compose run …` and
  `.build/<binary> …`. Idempotently triggers `cluster up` (which only rebuilds/repushes when
  something actually changed), then dispatches `<command>` to the host binary or into the container
  per the substrate's model (§9).
- `hostbootstrap base build | base push` — produce/publish the four base tags (used inside the
  hostbootstrap repo and by `--build-base`).
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
installs only what the substrate + yaml require, absorbing the projects' existing `bootstrap/*.sh`
checks.

- **apple-silicon** — require macOS arm64, Xcode Command Line Tools, passwordless sudo, and
  **Homebrew**; using **brew only**, install ghcup + the pinned GHC/Cabal (when a host binary is
  built) and a **Tart** VM (when the yaml needs it). **Docker / Colima**: hostbootstrap does **not**
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

## 8. `hostbootstrap.yaml` (per downstream project)

The tool **fails fast** if the file is missing, and again if the detected substrate is not declared.

### Schema (validated into frozen dataclasses)
```yaml
project: <name>
base:
  flavor: cpu | cuda                     # which base family the custom container inherits
container:
  dockerfile: docker/<name>.Dockerfile   # MUST inherit FROM the base tag the tool injects
  harbor:
    repo: harbor.example/<name>          # arch-explicit tags pushed here
mounts:                                  # persistent bind mounts for long-running containers
  - { host: ./.data, container: /opt/<name>/.data }            # ALWAYS maintained while running
  - { host: /var/run/docker.sock, container: /var/run/docker.sock }
  - { host: ${HOME}/.docker/config.json, container: /root/.docker/config.json, ro: true }
substrates:                              # only the substrates this project supports
  linux-cpu:     { model: outer-container }
  linux-gpu:     { model: multi-substrate, gpu: true }
  apple-silicon:
    model: multi-substrate
    host: { ghc: true, tart: true, metal: true }
    daemon: ".build/<name> inference --serve"   # host daemon started on `cluster up`; the tool
                                                 #   wraps it in a launchd/systemd unit (§9.4)
```

**Notes on `mounts` and `daemon`:**
- `mounts` declares the persistent bind mounts the CLI applies to long-running containers (it is not
  hard-coded). The `.data` mount is **always maintained while the cluster is running**.
- A substrate may declare a `daemon` command, applied on `cluster up` for host-level daemons that
  cannot be containerized (typically Apple-silicon Metal inference). The called binary is responsible
  for running forever; the tool manages its restart via a launchd/systemd unit (§9.4).

### Examples per model
- **Outer-container project**: declares `linux-cpu`/`linux-gpu` with `model: outer-container`.
- **Host-binary project**: declares its substrates with `model: host-binary` (and `host: { ghc: true }`
  on apple).
- **Mixed-substrate project**: `linux-*` with `model: multi-substrate` (container daemon → Harbor) and
  `apple-silicon` with `model: multi-substrate` + `host: { ghc, tart, metal }`.

---

## 9. Cluster lifecycle, the `run` command, and execution models

### 9.1 Why the CLI replaces docker-compose
For outer-container projects, the `hostbootstrap` CLI fully replaces `compose.yaml`. Compose is the
wrong tool here because it:
- has **no "pull the base image, or build it locally from a GitHub Dockerfile" switch** (our
  default-pull / `--build-base` behavior, §4);
- does **not handle mixed substrates** cleanly, where the same project sometimes runs as a host
  binary (Apple silicon) and sometimes as an outer container (Linux);
- cannot express the idempotent **build → bootstrap → push → run** pipeline below.

The CLI drives the Docker CLI directly instead.

### 9.2 Cluster lifecycle & the unified `run` command
Three lifecycle verbs, all idempotent:
- **`cluster up`** brings the whole stack to "running": (a) idempotently build the host binary **and**
  the custom container, reusing container + build caches (no unnecessary work); (b) idempotently
  bring up the cluster substrate and hand off to the project binary, which configures the actual k8s
  cluster as it does today (§9.7); (c) **enforce** that the custom image is built — the project binary
  then **uploads** it to Harbor (arch-explicit, no multi-arch, no orphans, never re-pushing the large
  base — §9.7); (d) start any declared host-level daemon (§9.4).
- **`cluster down`** tears the cluster down and stops/removes the long-running containers and any
  host daemon + its service unit. **Never deletes host `.data`.**
- **`cluster delete`** is a more thorough teardown (cluster plus derived state). **Still never
  deletes host `.data`.**

`hostbootstrap run <command>` is the single entrypoint that replaces both
`docker compose run --rm <project> <service> <command>` and `.build/<binary> <command>`. It
**idempotently triggers `cluster up`** (which only rebuilds/repushes when something actually changed),
then dispatches `<command>` to the host binary or into the container according to the substrate's
model in the yaml.

### 9.3 Long-running containers, restart policy, and bind mounts
When the CLI starts long-running containers it does so as **detached background tasks with an
`unless-stopped` restart policy**, so the Docker daemon brings them back after a host reboot — exactly
the behavior projects expect today. The CLI persistently bind-mounts what the yaml's `mounts`
declares (the `.data` directory, the Docker socket, docker config, …); these are **specified in
`hostbootstrap.yaml` (§8), not hard-coded**. One-shot `hostbootstrap run <command>` invocations use
`--rm`; persistent services use `--restart unless-stopped`.

Invariants:
- **The host `.data` bind-mount is always maintained whenever the cluster is running.**
- **`.build/` exists on the host only when a host binary is built**, and is **never** bind-mounted
  into an outer container. Outer-container projects keep no host `.build/` — their source is COPYed
  into the custom image at build time (§4, §9.5).

### 9.4 Host-level daemons (systemd / launchd)
Some substrates need a daemon that runs **on the host**, not under Docker — typically Apple-silicon
inference daemons that require **Metal** (e.g. mixed-substrate projects). The yaml may declare a
`daemon` command applied on `cluster up`. The called binary is responsible for running forever once
invoked (long-running host inference is the binary's job, not the CLI's).

Because the Docker daemon does not manage these host processes, they would not survive a reboot. To
match the `unless-stopped` behavior of containerized services, the contract is:

> **`cluster up` always ensures (idempotently creates) a system-level service unit — a system-scope
> systemd unit on Linux (`/etc/systemd/system/`) or a **LaunchDaemon** on macOS
> (`/Library/LaunchDaemons/`, *never* a per-user LaunchAgent) — if-and-only-if a host-level daemon is
> declared in the yaml; `cluster down` removes it. When no host-level daemon is declared, no unit is
> ever created.**

System-level placement is required so the daemon starts at boot **before any user logs in**,
supporting headless remote SSH workflows (§7). Managing these units is **why passwordless sudo is
required** (§7). After a reboot the unit restarts the daemon automatically, pre-login. This
mechanism applies **only** to host-level daemons — everything containerized is handled by the Docker
daemon's restart policy.

### 9.5 The three execution models
- **Outer container** — the CLI runs the project's CLI inside the custom image via `docker run`
  (detached + `--restart unless-stopped` for services; `--rm` for one-shot `run` commands),
  forwarding the Docker socket and applying the yaml's `mounts` (including `.data`). No `compose.yaml`.
  Project source is COPYed into the thin custom image at build time (no code bind-mount); cold builds
  stay light because the heavy base is pulled, not rebuilt.
- **Host binary** — **Apple silicon**: build with host `cabal` (GHC/Cabal via brew→ghcup); hot
  rebuilds kept for efficiency; Swift in a **Tart** VM; GPU on **Metal**, host-native. **Linux**:
  build the binary **inside the base container** and extract it to the host (keeps the toolchain off
  the Linux host); a persistent build dir keeps cabal rebuilds incremental. The host `.build/` holds
  the binary.
- **Multi-substrate** — **Linux**: containerized daemon `FROM` the base, uploaded arch-explicit to
  Harbor (fast path). **Apple silicon**: a containerized counterpart is **still** built and uploaded
  to Harbor (§9.7), **and** a host-native binary runs for direct hardware access (Tart for Swift,
  Metal for GPU), started as a host daemon per §9.4; the host binary keeps its control-plane role and
  reaches cluster services over loopback-only NodePorts (§9.7). The clustered daemon may forward
  inference to the host binary.

### 9.6 Note on fourmolu/hlint (all models)
fourmolu/hlint are **container-only** — never installed, built, or run on the host. They run inside
the (already-built) base/custom container even for host-binary projects.

**Responsibility split:** the base container ships fourmolu/hlint **prebuilt**; **invoking them is
the responsibility of the project's Dockerfile**, which simply calls the prebuilt tools (e.g. in a
build-time `RUN` over the COPYed source, or as a container entrypoint subcommand). `hostbootstrap`
itself does not invoke fourmolu/hlint — it builds the container; the project's Dockerfile owns when
and how the quality checks actually run.

### 9.7 Host-daemon substrates still build & ship a containerized counterpart
Even on host-daemon substrates (e.g. Apple-silicon Metal), the binary is **also** built as a container
and **uploaded to Harbor** — the host daemon and the in-cluster container are two faces of the same
binary, not an either/or. Consequences to make explicit:

- **Code-quality checks (fourmolu/hlint, and any container-run linters) happen only in the container,
  never on the host.** The container is built regardless, so it is the single, canonical place these
  run; the **project's Dockerfile** invokes them using the **prebuilt** tools the base ships (§9.6).
- The host binary retains **control-plane responsibilities on the host**. It communicates with its
  in-cluster counterpart **and** other cluster services (e.g. **MinIO**, **Pulsar**) over **NodePorts
  bound to `127.0.0.1` / `127.0.0.0/8` — reachable from localhost only.** This loopback-only exposure
  is a deliberate, important security boundary: cluster services must **never** be reachable off-host,
  to avoid opening a network backdoor.

**Division of labor (documenting existing project behavior):** `hostbootstrap` **enforces** that the
container is built (and is where quality checks run) and orchestrates the outer lifecycle, but it is
still the **custom binary** that **configures the actual k8s cluster** and **uploads its image to
Harbor**, exactly as the projects do today. The tool brings up the substrate and hands off to the
binary; the binary owns cluster configuration and image publication.

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

---

## 11. check-code & tooling config

Mirror the shipnorth standards exactly in `pyproject.toml`:
- `[tool.ruff]` — line-length 100, target py312, the same `select`/`ignore` lint sets.
- `[tool.black]` — line-length 100, py312.
- `[tool.mypy]` — **strict** (`strict = true`, `disallow_untyped_defs`, `disallow_any_explicit`, …),
  `mypy_path = "stubs"`.
- `check_code.py` runs **ruff → black → mypy** over `hostbootstrap/` (and `stubs/`), fail-fast,
  returning the first non-zero exit code.
- Dev/runtime deps pinned `>=X,<Y`: runtime `click`, `httpx`, `pyyaml`; dev `ruff`, `black`, `mypy`.

---

## 12. Documentation strategy

- `documents/` is the SSoT tree; **`documents/documentation_standards.md`** is authoritative and
  modeled on shipnorth's (snake_case file names except `README.md`/`AGENTS.md`/`CLAUDE.md`; required
  header metadata; WRONG/RIGHT examples; link liberally).
- Per-language guidance (including a new **`languages/go.md`**) and engineering references
  (base image, build/release, prerequisites, harbor, gitignore guardrails) migrate out of the
  current monolithic README into `documents/`.
- **`README.md` becomes a concise adoption guide**: what a project must do to adopt the hostbootstrap
  way and author its `hostbootstrap.yaml`, described through the three model **archetypes**
  (outer-container, host-binary, mixed-substrate) **without naming any specific project**.
- Per-project ad-hoc `.sh` build/bootstrap scripts are deleted as each project migrates.

---

## 13. Per-project migration mapping (internal reference; names excluded from README)

| Project | Substrates | Model | Notes |
|---|---|---|---|
| `mattandjames` | linux-cpu (+arm64) | outer-container | drop `compose.yaml`; inherit base; CLI via `docker run` + socket |
| `prodbox` | linux-cpu | host-binary | manages host cluster; Linux build-in-base-container, extract binary |
| `mcts` | linux-cpu, linux-gpu | outer-container or daemon | drop in-Dockerfile Python/Node/Playwright; keep C++/SCons/pybind11 + FastAPI/React layers |
| `jitML` | linux-cpu, linux-gpu, apple-silicon | multi-substrate | Linux daemon→Harbor; Apple host-native Tart/Metal; absorb `bootstrap/*.sh` into `doctor` |
| `infernix` | linux-cpu, linux-gpu, apple-silicon | multi-substrate | as above; Apple Metal path still WIP; preserve its own python adapters `.venv` (isolation) |

All projects standardize Haskell on **GHC 9.12** as part of migration.

---

## 14. Risks & constraints

1. **GHC standardization effort** — projects currently on GHC 9.14.1 must refactor to 9.12; validate
   each builds and that the warm Haskell store + fourmolu/hlint remain compatible.
2. **Loss of buildx SBOM/provenance** — plain `docker build` does not emit the attestation manifests
   buildx produced. Accepted.
3. **Harbor "no orphans"** — the tool deletes superseded arch-explicit tags it owns; reclaiming
   untagged digests depends on the Harbor instance's GC policy.
4. **`cuda-arm64`** — supported by the naming scheme but built only on demand (GPU projects are
   amd64 in practice).
5. **CUDA drift** — dynamic resolution always pulls the latest `cudnn-devel-ubuntu24.04`; a project
   pinned to an older CUDA must override the resolved base arg explicitly.

---

## 15. Verification / acceptance criteria

- A clean host `python -m pip install git+…` exposes `hostbootstrap`; running it in a project with no
  `hostbootstrap.yaml` **fails fast** with a clear message; an unsupported substrate also fails fast.
- `hostbootstrap doctor` detects the substrate correctly and validates/installs prerequisites
  **idempotently** (re-run is a no-op; reboot-required paths exit with guidance).
- `hostbootstrap build` pulls the correct `basecontainer-<flavor>-<arch>` and compiles **only project
  code** — a warm-base cold build is dramatically faster than today's from-scratch build (measure it).
- `--build-base` reproduces a base tag locally under the identical name; `docker images` shows the
  arch-explicit tag; **no manifest list** exists anywhere.
- An outer-container project runs via `docker run` with the socket forwarded and **no `compose.yaml`**.
- `cluster up`/`down`/`delete` are idempotent and **never delete host `.data`**; `.data` stays
  bind-mounted the entire time the cluster is running.
- `hostbootstrap run <command>` idempotently triggers `cluster up` (rebuilding/repushing only when
  needed) and dispatches the command to the host binary or container per the yaml.
- Long-running containers are started detached with `--restart unless-stopped` and survive a host
  reboot; one-shot `run` invocations use `--rm`.
- `cluster up` **always** (idempotently) creates a **system-level** service unit — a system-scope
  systemd unit (Linux) or a **LaunchDaemon** in `/Library/LaunchDaemons/` (macOS, **never** a
  per-user LaunchAgent) — **iff** the yaml declares a host-level daemon; `cluster down` removes it.
  No unit is ever created when no host-level daemon is declared. After reboot, the unit restarts the
  daemon automatically **before user login** (supporting headless remote SSH).
- On macOS, hostbootstrap **does not** install or modify the Colima VM. `doctor` **validates** that a
  Colima-backed Docker VM exists **and** is configured to start at system level before user login; if
  either check fails, it fails fast with precise remediation instructions.
- A host `.build/` exists only for host-binary projects and is **never** bind-mounted into an outer
  container.
- On host-daemon substrates, a containerized counterpart is still built and uploaded to Harbor;
  fourmolu/hlint are invoked by the **project's Dockerfile** (using the **prebuilt** tools the base
  ships) inside that container — never on the host; and the host binary reaches in-cluster services
  (MinIO, Pulsar, its own counterpart) only over loopback (`127.0.0.0/8`) NodePorts.
- `hostbootstrap` enforces the container build, but the custom binary performs the actual cluster
  configuration and the Harbor image upload (matching current project behavior).
- Host-binary: Apple builds on host; Linux builds in-container and extracts a runnable binary;
  fourmolu/hlint never appear on the host.
- `poetry run check-code` passes (ruff/black/mypy-strict) in the hostbootstrap repo; downstream
  projects' own `.venv`s remain free of hostbootstrap.
- The base Dockerfile contains no `if`/`case`/version-resolution logic; all such values arrive as
  build args; a single GHC 9.12 is present; `nvkind` is built in a single stage with a first-class
  Go toolchain.
- `documents/documentation_standards.md` exists; `README.md` reads as a model-archetype adoption
  guide naming no specific project.
```
