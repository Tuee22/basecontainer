---
name: engineering-prerequisites
description: Host prerequisites validated and (where safe) installed by hostbootstrap doctor.
type: reference
---

# Prerequisites

`hostbootstrap doctor` validates and idempotently installs only what the
substrate plus the project's [`hostbootstrap.dhall`](schema.md) actually
require. Re-running on a healthy host is a no-op.

## Universal

**Passwordless sudo** is a hard prerequisite on every substrate. The tool
needs it for:

* apt installs (Docker, GPU drivers, NVIDIA container toolkit) on Linux.
* Docker group/runtime configuration on Linux.
* brew installs (Tart, ghcup, `dhall-json`) on macOS.
* Creating and destroying **system-level** service units (a system-scope
  systemd unit in `/etc/systemd/system` on Linux; a **LaunchDaemon** in
  `/Library/LaunchDaemons` on macOS) — but **only** for the
  [host-daemon model](schema.md). No other model touches a system unit, so on a
  pure container or host-binary project the unit-creation reason simply does not
  apply; the apt/brew and Docker/GPU reasons above still do.

Missing passwordless sudo is a fail-fast condition with precise remediation.

### Why a unit is daemon-gated

A system service unit is created **if and only if** a substrate uses the
host-daemon execution model — that model exists precisely to wrap a
long-running host-native daemon in a unit. The container and host-binary models
never create one: a container runs under Docker, and a host binary owns its own
service lifecycle (any unit it installs is the binary's concern, not the tool's).
See [schema.md](schema.md) for the structural rule that makes a unit
unrepresentable for the other two models.

## Dhall parsing (`dhall-to-json`)

Reading `hostbootstrap.dhall` needs `dhall-to-json`, but this is **not** a new
manual prerequisite. The tool auto-provisions a native binary on first use: it
prefers one already on `PATH` (e.g. `brew install dhall-json`), and otherwise
downloads a pinned, SHA256-verified static release into
`~/.cache/hostbootstrap/`. The one documented gap is **Ubuntu arm64**, which has
no prebuilt static asset — there the fallback is `brew install dhall-json` (via
Linux Homebrew) or building `dhall-json` from source.

## apple-silicon

* macOS arm64.
* Xcode Command Line Tools.
* Homebrew.
* Tart (when an entry's host requirements declare `tart = True`).
* ghcup + pinned GHC/Cabal (when a host-binary build is needed).
* **Colima-backed Docker VM configured to start at the system level
  (before user login).** hostbootstrap does not install or modify Colima — it
  validates that the system-level launchd plist exists.

## linux-cpu

* Ubuntu 24.04.
* Docker installed with non-sudo group access.

## linux-gpu

Everything from linux-cpu, plus:

* NVIDIA driver.
* NVIDIA container toolkit, registered with the Docker runtime.
* Reboot prompted (and exit) when a fresh driver/docker install requires one.

## Headless remote SSH

On macOS, hostbootstrap-configured services must work in setups where
FileVault is off and the user may reboot remotely and SSH in **before any GUI
login**. The Colima VM and any host-daemon unit therefore start at the
system level — a **LaunchDaemon**, never a per-user **LaunchAgent**. User-scope
launchd agents and user-scope systemd units would not survive that workflow.
(This applies only when the host-daemon model is in play; container and
host-binary projects create no unit at all.)
