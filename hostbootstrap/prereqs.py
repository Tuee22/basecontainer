"""Validate (and where safe, idempotently install) host prerequisites.

Each substrate has its own check function; ``doctor`` dispatches via the
detected :class:`Substrate`. We always *check first* and only invoke the
installer when a check fails — re-running is a no-op on a healthy host.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .spec import HostBinaryModel, HostDaemonModel, HostReqs, ProjectSpec
from .substrate import Substrate, SubstrateName


class PrereqError(RuntimeError):
    """A prerequisite is missing or misconfigured."""


@dataclass(frozen=True)
class DoctorResult:
    substrate: Substrate
    messages: tuple[str, ...]
    reboot_required: bool = False


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _check_passwordless_sudo() -> None:
    if os.geteuid() == 0:
        return
    if not _have("sudo"):
        raise PrereqError("sudo is required but not installed")
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrereqError(f"could not exec sudo: {exc}") from exc
    if result.returncode != 0:
        raise PrereqError(
            "passwordless sudo is required. Add a NOPASSWD entry for your "
            "user in /etc/sudoers.d/ before re-running."
        )


def _check_docker_socket() -> None:
    if not _have("docker"):
        raise PrereqError("docker CLI not found in PATH")
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrereqError(f"could not exec docker: {exc}") from exc
    if result.returncode != 0:
        raise PrereqError(
            "docker daemon is not reachable. On Linux: ensure dockerd is "
            "running and your user is in the docker group; on macOS: ensure "
            "the Colima VM is configured to start at the system level."
        )


def _check_ubuntu_2404() -> None:
    os_release = Path("/etc/os-release")
    if not os_release.is_file():
        raise PrereqError("cannot read /etc/os-release; Linux substrates require Ubuntu 24.04")
    data = dict(line.split("=", 1) for line in os_release.read_text().splitlines() if "=" in line)
    distro_id = data.get("ID", "").strip('"')
    version_id = data.get("VERSION_ID", "").strip('"')
    if distro_id != "ubuntu" or version_id != "24.04":
        raise PrereqError(
            f"Linux substrates require Ubuntu 24.04; got ID={distro_id!r} VERSION_ID={version_id!r}"
        )


def _check_macos_arm64() -> None:
    if platform.system() != "Darwin":
        raise PrereqError("apple-silicon prereqs invoked on a non-Darwin host")
    if platform.machine().lower() not in {"arm64", "aarch64"}:
        raise PrereqError("apple-silicon requires an Apple Silicon Mac (arm64)")


def _check_xcode_clt() -> None:
    try:
        result = subprocess.run(
            ["xcode-select", "-p"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrereqError(f"xcode-select failed: {exc}") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise PrereqError(
            "Xcode Command Line Tools are required. Install with: xcode-select --install"
        )


def _check_homebrew() -> None:
    if not _have("brew"):
        raise PrereqError("Homebrew is required on apple-silicon. Install from https://brew.sh.")


def _check_colima_launchdaemon() -> None:
    plist = Path("/Library/LaunchDaemons/com.colima.default.plist")
    if not plist.is_file():
        raise PrereqError(
            "Colima must be configured to start at the system level "
            "(/Library/LaunchDaemons/com.colima.default.plist). "
            "Reconfigure with `sudo colima start --foreground` under a system-level launchd plist."
        )


def _check_nvidia_runtime() -> None:
    if not _have("nvidia-smi"):
        raise PrereqError("nvidia-smi not found; install the NVIDIA driver")
    if not _have("docker"):
        return
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrereqError(f"docker info failed: {exc}") from exc
    if "nvidia" not in result.stdout:
        raise PrereqError(
            "NVIDIA container toolkit is not registered with Docker. "
            "Install nvidia-container-toolkit and re-configure dockerd."
        )


async def _run_apple(spec: ProjectSpec, substrate: Substrate) -> DoctorResult:
    messages: list[str] = []
    _check_macos_arm64()
    messages.append("macOS arm64: OK")
    _check_xcode_clt()
    messages.append("Xcode Command Line Tools: OK")
    _check_passwordless_sudo()
    messages.append("passwordless sudo: OK")
    _check_homebrew()
    messages.append("Homebrew: OK")
    _check_colima_launchdaemon()
    messages.append("Colima system-level LaunchDaemon: OK")
    _check_docker_socket()
    messages.append("Docker daemon reachable: OK")

    apple = spec.substrates.get(SubstrateName.APPLE_SILICON)
    host: HostReqs | None = None
    if isinstance(apple, (HostBinaryModel, HostDaemonModel)):
        host = apple.build.host
    if host is not None:
        if host.tart and not _have("tart"):
            raise PrereqError(
                "config requires Tart; install via `brew install cirruslabs/cli/tart`"
            )
        if host.ghc and not _have("ghcup"):
            raise PrereqError("config requires GHC on host; install via `brew install ghcup-hs`")

    return DoctorResult(substrate=substrate, messages=tuple(messages))


async def _run_linux(spec: ProjectSpec, substrate: Substrate) -> DoctorResult:
    messages: list[str] = []
    _check_ubuntu_2404()
    messages.append("Ubuntu 24.04: OK")
    _check_passwordless_sudo()
    messages.append("passwordless sudo: OK")
    _check_docker_socket()
    messages.append("Docker daemon reachable: OK")

    if substrate.name is SubstrateName.LINUX_GPU:
        _check_nvidia_runtime()
        messages.append("NVIDIA container runtime: OK")

    _ = spec  # spec is currently only consulted for apple-silicon

    return DoctorResult(substrate=substrate, messages=tuple(messages))


async def run_doctor(spec: ProjectSpec, substrate: Substrate) -> DoctorResult:
    if substrate.name is SubstrateName.APPLE_SILICON:
        return await _run_apple(spec, substrate)
    return await _run_linux(spec, substrate)


def run_doctor_sync(spec: ProjectSpec, substrate: Substrate) -> DoctorResult:
    return asyncio.run(run_doctor(spec, substrate))
