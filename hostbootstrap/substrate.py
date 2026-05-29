"""Substrate detection.

Three frozen models — *apple-silicon*, *linux-cpu*, *linux-gpu* — match the
three substrates downstream projects target. Detection is pure: it reads the
platform and a small set of files (``/proc/driver/nvidia/version`` etc.) and
returns one frozen value. No side effects.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final


class SubstrateName(str, Enum):
    APPLE_SILICON = "apple-silicon"
    LINUX_CPU = "linux-cpu"
    LINUX_GPU = "linux-gpu"


@dataclass(frozen=True)
class Substrate:
    """The detected host substrate.

    ``arch`` is the Docker-style architecture (``amd64`` / ``arm64``). For
    apple-silicon it is always ``arm64``.
    """

    name: SubstrateName
    arch: str

    @property
    def is_apple_silicon(self) -> bool:
        return self.name is SubstrateName.APPLE_SILICON

    @property
    def is_linux(self) -> bool:
        return self.name in {SubstrateName.LINUX_CPU, SubstrateName.LINUX_GPU}

    @property
    def has_gpu(self) -> bool:
        return self.name is SubstrateName.LINUX_GPU


_DOCKER_ARCH: Final[dict[str, str]] = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

_NVIDIA_MARKERS: Final[tuple[Path, ...]] = (
    Path("/proc/driver/nvidia/version"),
    Path("/dev/nvidiactl"),
)


def _docker_arch() -> str:
    raw = platform.machine().lower()
    if raw not in _DOCKER_ARCH:
        raise RuntimeError(f"unsupported host architecture: {raw}")
    return _DOCKER_ARCH[raw]


def _has_nvidia_gpu() -> bool:
    if any(marker.exists() for marker in _NVIDIA_MARKERS):
        return True
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return False
    try:
        result = subprocess.run(
            [nvidia_smi, "-L"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "GPU" in result.stdout


def detect() -> Substrate:
    system = platform.system()
    if system == "Darwin":
        arch = _docker_arch()
        if arch != "arm64":
            raise RuntimeError(
                "hostbootstrap only supports Apple Silicon (arm64) on macOS; "
                f"detected arch={arch!r}"
            )
        return Substrate(SubstrateName.APPLE_SILICON, arch)
    if system == "Linux":
        arch = _docker_arch()
        if _has_nvidia_gpu():
            return Substrate(SubstrateName.LINUX_GPU, arch)
        return Substrate(SubstrateName.LINUX_CPU, arch)
    raise RuntimeError(f"unsupported host platform: {system}")
