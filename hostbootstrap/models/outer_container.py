"""Outer-container model (§9.5).

The CLI runs the project's CLI inside a custom image via ``docker run``,
forwarding the Docker socket and applying the mounts declared in
``hostbootstrap.yaml``. There is **no compose.yaml**: ``docker run`` is the
only orchestration call.

Persistent services are launched detached with ``--restart unless-stopped``
so the Docker daemon brings them back after a host reboot. One-shot
``hostbootstrap run <command>`` invocations use ``--rm``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import base_image, docker_ops, process
from ..spec import ProjectSpec, SubstrateSpec
from ..substrate import Substrate


@dataclass(frozen=True)
class OuterContainerBuildResult:
    image_tag: str


def _custom_image_tag(spec: ProjectSpec, substrate: Substrate) -> str:
    return f"{spec.project}:{substrate.name.value}-{substrate.arch}"


def _mounts(spec: ProjectSpec) -> tuple[tuple[str, str, bool], ...]:
    return tuple((m.host, m.container, m.read_only) for m in spec.mounts)


async def build(
    spec: ProjectSpec,
    substrate: Substrate,
    *,
    project_root: Path,
) -> OuterContainerBuildResult:
    flavor = base_image.Flavor(spec.base.flavor)
    base_args = base_image.compute_build_args(flavor, substrate.arch)
    image_tag = _custom_image_tag(spec, substrate)

    build_spec = docker_ops.BuildSpec(
        dockerfile=project_root / spec.container.dockerfile,
        context=project_root,
        tags=(image_tag,),
        build_args={
            "BASE_IMAGE": base_image.base_image_ref(flavor, substrate.arch),
            **base_args.as_build_args(),
        },
        pull=True,
    )
    await docker_ops.build(build_spec)
    return OuterContainerBuildResult(image_tag=image_tag)


async def run_one_shot(
    spec: ProjectSpec,
    substrate: Substrate,
    command: Sequence[str],
    *,
    project_root: Path,
) -> process.CommandResult:
    build_result = await build(spec, substrate, project_root=project_root)
    run_spec = docker_ops.RunSpec(
        image=build_result.image_tag,
        command=tuple(command),
        rm=True,
        mounts=_mounts(spec),
    )
    return await process.run_checked(docker_ops.run_command(run_spec))


async def start_service(
    spec: ProjectSpec,
    substrate: Substrate,
    substrate_spec: SubstrateSpec,
    *,
    project_root: Path,
) -> process.CommandResult:
    _ = substrate_spec
    build_result = await build(spec, substrate, project_root=project_root)
    run_spec = docker_ops.RunSpec(
        image=build_result.image_tag,
        detach=True,
        restart="unless-stopped",
        name=spec.project,
        mounts=_mounts(spec),
    )
    return await process.run_checked(docker_ops.run_command(run_spec))
