---
name: engineering-prerequisites
description: Host prerequisites validated and (where safe) installed by hostbootstrap doctor.
type: reference
---

# Prerequisites

`hostbootstrap doctor` validates and idempotently installs only what the
substrate plus the project's `hostbootstrap.yaml` actually require. Re-running
on a healthy host is a no-op.

## Universal

**Passwordless sudo** is a hard prerequisite on every substrate. The tool
needs it for:

* apt installs (Docker, GPU drivers, NVIDIA container toolkit) on Linux.
* Docker group/runtime configuration on Linux.
* brew installs (Tart, ghcup) on macOS.
* Creating and destroying **system-level** service units (systemd units on
  Linux; **LaunchDaemons** on macOS) for host-level daemons declared in the
  yaml.

Missing passwordless sudo is a fail-fast condition with precise remediation.

## apple-silicon

* macOS arm64.
* Xcode Command Line Tools.
* Homebrew.
* Tart (when the yaml declares `host: { tart: true }`).
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
login**. The Colima VM and any host-level daemon unit therefore start at the
system level — `LaunchAgents` (user scope) and user-scope systemd units would
not survive that workflow.
