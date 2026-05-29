"""Host-binary model (§9.5).

* **Apple silicon** — build on the host with ``cabal`` (GHC/Cabal installed via
  brew→ghcup); hot rebuilds stay incremental.
* **Linux** — build the binary **inside the base container** and extract it to
  the host so the toolchain never lands on the Linux host directly. A persistent
  cabal build dir keeps rebuilds incremental.

The host ``.build/`` directory exists *only* for host-binary projects and is
never bind-mounted into an outer container (§9.3 invariant).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import base_image, docker_ops, process
from ..spec import ProjectSpec, SubstrateSpec
from ..substrate import Substrate, SubstrateName


@dataclass(frozen=True)
class HostBinaryBuildResult:
    binary_path: Path


def _build_dir(project_root: Path) -> Path:
    return project_root / ".build"


async def _build_on_host(spec: ProjectSpec, project_root: Path) -> HostBinaryBuildResult:
    build_dir = _build_dir(project_root)
    build_dir.mkdir(parents=True, exist_ok=True)
    await process.run_checked(["cabal", "update"], cwd=project_root)
    await process.run_checked(
        [
            "cabal",
            "install",
            "--installdir",
            str(build_dir),
            "--install-method=copy",
            "--overwrite-policy=always",
            spec.project,
        ],
        cwd=project_root,
    )
    return HostBinaryBuildResult(binary_path=build_dir / spec.project)


async def _build_in_base_container_and_extract(
    spec: ProjectSpec,
    substrate: Substrate,
    project_root: Path,
) -> HostBinaryBuildResult:
    flavor = base_image.Flavor(spec.base.flavor)
    base_tag = base_image.base_image_ref(flavor, substrate.arch)
    build_dir = _build_dir(project_root)
    build_dir.mkdir(parents=True, exist_ok=True)

    # Bind-mount the project source and a persistent cabal build dir, then run
    # cabal install inside the base image; the output binary appears in the
    # host's .build/ directory.
    run_spec = docker_ops.RunSpec(
        image=base_tag,
        command=(
            "bash",
            "-lc",
            (
                "set -eux; "
                "cd /src; "
                "cabal update; "
                "cabal install "
                "  --installdir /out "
                "  --install-method=copy "
                "  --overwrite-policy=always "
                f"  {spec.project}"
            ),
        ),
        rm=True,
        mounts=(
            (str(project_root), "/src", False),
            (str(build_dir), "/out", False),
        ),
        extra=("-w", "/src"),
    )
    await process.run_checked(docker_ops.run_command(run_spec))
    return HostBinaryBuildResult(binary_path=build_dir / spec.project)


async def build(
    spec: ProjectSpec,
    substrate: Substrate,
    *,
    project_root: Path,
) -> HostBinaryBuildResult:
    if substrate.name is SubstrateName.APPLE_SILICON:
        return await _build_on_host(spec, project_root)
    return await _build_in_base_container_and_extract(spec, substrate, project_root)


async def run_one_shot(
    spec: ProjectSpec,
    substrate: Substrate,
    command: Sequence[str],
    *,
    project_root: Path,
) -> process.CommandResult:
    result = await build(spec, substrate, project_root=project_root)
    return await process.run_checked([str(result.binary_path), *command], cwd=project_root)


def daemon_command(
    substrate_spec: SubstrateSpec,
    *,
    project_root: Path,
) -> tuple[str, ...] | None:
    """The yaml-declared host daemon command, resolved against *project_root*.

    The CLI wraps this in a system-level service unit on ``cluster up``
    (a LaunchDaemon on macOS, a system-scope systemd unit on Linux). The
    binary itself is responsible for running forever once invoked (§9.4).
    """
    if substrate_spec.daemon is None:
        return None
    raw = substrate_spec.daemon
    # Resolve a leading ".build/..." token relative to project_root so the
    # service unit holds an absolute path.
    parts = raw.split()
    if parts and parts[0].startswith(".build/"):
        parts[0] = str(project_root / parts[0])
    _ = os.path.abspath  # silence unused-import warning if any
    return tuple(parts)
