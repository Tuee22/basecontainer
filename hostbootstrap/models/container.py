"""``model: container`` (§9.5).

hostbootstrap builds a thin image ``FROM`` the hostbootstrap base tag and runs
it. The container owns any cluster/upload work itself; hostbootstrap never
creates a system service unit for this model.

* ``service = False`` → one-shot ``docker run --rm`` (the compose-replacement case).
* ``service = True``  → ``cluster up`` runs it detached with
  ``--restart unless-stopped`` so the Docker daemon restarts it across reboots.

Project source is built into the image (the Dockerfile inherits ``FROM
${BASE_IMAGE}``); the heavy toolchain is pulled with the base, so cold builds
compile only project code.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from hostbootstrap import base_image, docker_ops, process
from hostbootstrap.spec import ContainerArtifact, ContainerModel, ProjectSpec
from hostbootstrap.substrate import Substrate


def image_tag(spec: ProjectSpec, substrate: Substrate) -> str:
    return f"{spec.project}:{substrate.name.value}-{substrate.arch}"


def resolve_host_path(host: str, project_root: Path) -> str:
    """Expand ``${VARS}`` and absolutize a bind-mount host path."""
    expanded = os.path.expandvars(host)
    if os.path.isabs(expanded):
        return expanded
    return os.path.abspath(os.path.join(project_root, expanded))


def _mounts(model: ContainerModel, project_root: Path) -> tuple[tuple[str, str, bool], ...]:
    return tuple(
        (resolve_host_path(m.host, project_root), m.container, m.read_only) for m in model.mounts
    )


async def build(
    spec: ProjectSpec,
    model: ContainerModel,
    substrate: Substrate,
    *,
    project_root: Path,
) -> str:
    """Build the project image ``FROM`` the base tag; return its local tag."""
    flavor = base_image.Flavor(model.flavor.value)
    tag = image_tag(spec, substrate)
    build_spec = docker_ops.BuildSpec(
        dockerfile=project_root / model.dockerfile,
        context=project_root,
        tags=(tag,),
        build_args={"BASE_IMAGE": base_image.base_image_ref(flavor, substrate.arch)},
        pull=True,
    )
    await docker_ops.build(build_spec)
    return tag


async def build_artifact(
    spec: ProjectSpec,
    artifact: ContainerArtifact,
    substrate: Substrate,
    *,
    project_root: Path,
) -> str:
    """Build the optional container counterpart declared by a binary/daemon model."""
    flavor = base_image.Flavor(artifact.flavor.value)
    tag = image_tag(spec, substrate)
    build_spec = docker_ops.BuildSpec(
        dockerfile=project_root / artifact.dockerfile,
        context=project_root,
        tags=(tag,),
        build_args={"BASE_IMAGE": base_image.base_image_ref(flavor, substrate.arch)},
        pull=True,
    )
    await docker_ops.build(build_spec)
    return tag


async def run_one_shot(
    spec: ProjectSpec,
    model: ContainerModel,
    substrate: Substrate,
    command: Sequence[str],
    *,
    project_root: Path,
) -> process.CommandResult:
    tag = await build(spec, model, substrate, project_root=project_root)
    run_spec = docker_ops.RunSpec(
        image=tag,
        command=tuple(command),
        rm=True,
        mounts=_mounts(model, project_root),
    )
    return await process.run_checked(docker_ops.run_command(run_spec))


async def start_service(
    spec: ProjectSpec,
    model: ContainerModel,
    substrate: Substrate,
    *,
    project_root: Path,
) -> process.CommandResult:
    """Start the long-running container detached with ``--restart unless-stopped``."""
    tag = await build(spec, model, substrate, project_root=project_root)
    # Recreate idempotently: remove any prior container of the same name first.
    await process.run(["docker", "rm", "-f", spec.project], quiet=True)
    run_spec = docker_ops.RunSpec(
        image=tag,
        detach=True,
        restart="unless-stopped",
        name=spec.project,
        mounts=_mounts(model, project_root),
    )
    return await process.run_checked(docker_ops.run_command(run_spec))


async def stop_service(spec: ProjectSpec) -> process.CommandResult:
    return await process.run(["docker", "rm", "-f", spec.project], quiet=True)
