"""Multi-substrate model (§9.5, §9.7).

* **Linux** — a containerized daemon ``FROM`` the base image, uploaded
  arch-explicit to Harbor (the fast path).
* **Apple silicon** — a containerized counterpart is **still** built and
  uploaded to Harbor (so quality checks and the in-cluster counterpart exist),
  **and** a host-native binary runs for Metal/Tart hardware access. The host
  binary keeps its control-plane role and reaches in-cluster services only over
  loopback (``127.0.0.0/8``) NodePorts — a deliberate, non-negotiable
  security boundary.

This module composes :mod:`outer_container` (for the Linux side / containerised
counterpart) and :mod:`host_binary` (for the Apple-silicon host-native daemon).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import process
from ..spec import ProjectSpec
from ..substrate import Substrate, SubstrateName
from . import host_binary, outer_container


@dataclass(frozen=True)
class MultiSubstrateBuildResult:
    image_tag: str
    binary_path: Path | None


async def build(
    spec: ProjectSpec,
    substrate: Substrate,
    *,
    project_root: Path,
) -> MultiSubstrateBuildResult:
    # The containerized counterpart is *always* built — even on host-daemon
    # substrates — because code-quality checks and the in-cluster sibling both
    # live there.
    container_result = await outer_container.build(spec, substrate, project_root=project_root)

    binary_path: Path | None = None
    if substrate.name is SubstrateName.APPLE_SILICON:
        host_result = await host_binary.build(spec, substrate, project_root=project_root)
        binary_path = host_result.binary_path

    return MultiSubstrateBuildResult(
        image_tag=container_result.image_tag,
        binary_path=binary_path,
    )


async def run_one_shot(
    spec: ProjectSpec,
    substrate: Substrate,
    command: Sequence[str],
    *,
    project_root: Path,
) -> process.CommandResult:
    if substrate.name is SubstrateName.APPLE_SILICON:
        return await host_binary.run_one_shot(spec, substrate, command, project_root=project_root)
    return await outer_container.run_one_shot(spec, substrate, command, project_root=project_root)
