"""``model: host-binary`` (§9.5).

The primary artifact is a binary that runs **on the host**. hostbootstrap builds
it, optionally builds a container counterpart, and then hands the lifecycle off
to the binary's own commands (``handoff.up`` / ``down`` / ``delete``). It creates
**no** system unit — the binary manages its own services (e.g. an RKE2 systemd
unit it installs itself).

* **Apple silicon** — run the project's ``build.cabal`` command on the host
  (GHC/Cabal via brew→ghcup); hot rebuilds stay incremental.
* **Linux** — run ``build.cabal`` **inside the base container** with the project
  source mounted, so the toolchain never lands on the Linux host; the binary
  appears in the host ``.build/`` directory.

The author's ``build.cabal`` is responsible for placing the binary at
``.build/<project>`` (e.g. ``cabal install --installdir .build
--install-method=copy --overwrite-policy=always exe:<project>``).
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Sequence
from pathlib import Path

from hostbootstrap import base_image, docker_ops, process
from hostbootstrap.spec import BuildSpec, HostBinaryModel, ProjectSpec
from hostbootstrap.substrate import Substrate, SubstrateName

from . import container


def build_dir(project_root: Path) -> Path:
    return project_root / ".build"


def binary_path(spec: ProjectSpec, project_root: Path) -> Path:
    return build_dir(project_root) / spec.project


def resolve_command(raw: str, project_root: Path) -> tuple[str, ...]:
    """Split a host command string, absolutizing a leading ``.build/…`` token."""
    parts = shlex.split(raw)
    if parts and not os.path.isabs(parts[0]) and parts[0].startswith(".build/"):
        parts[0] = os.path.abspath(os.path.join(project_root, parts[0]))
    return tuple(parts)


async def build_binary(
    spec: ProjectSpec,
    build: BuildSpec,
    substrate: Substrate,
    *,
    project_root: Path,
) -> Path:
    """Build the host binary; return its ``.build/<project>`` path."""
    build_dir(project_root).mkdir(parents=True, exist_ok=True)

    if substrate.name is SubstrateName.APPLE_SILICON:
        await process.run_checked(shlex.split(build.cabal), cwd=project_root)
        return binary_path(spec, project_root)

    flavor, _arch = base_image.substrate_to_flavor_arch(substrate)
    base_tag = base_image.base_image_ref(flavor, substrate.arch)
    run_spec = docker_ops.RunSpec(
        image=base_tag,
        command=("sh", "-c", build.cabal),
        rm=True,
        mounts=((str(project_root), "/src", False),),
        extra=("-w", "/src"),
    )
    await process.run_checked(docker_ops.run_command(run_spec))
    return binary_path(spec, project_root)


async def build(
    spec: ProjectSpec,
    model: HostBinaryModel,
    substrate: Substrate,
    *,
    project_root: Path,
) -> Path:
    """Build the binary and, if declared, the optional container counterpart."""
    path = await build_binary(spec, model.build, substrate, project_root=project_root)
    if model.container is not None:
        await container.build_artifact(spec, model.container, substrate, project_root=project_root)
    return path


async def run_one_shot(
    spec: ProjectSpec,
    model: HostBinaryModel,
    substrate: Substrate,
    command: Sequence[str],
    *,
    project_root: Path,
) -> process.CommandResult:
    path = await build(spec, model, substrate, project_root=project_root)
    return await process.run_checked([str(path), *command], cwd=project_root)
