"""``hostbootstrap`` Click application.

The single entrypoint installed on every downstream host (via
``pip install git+…``). Commands implement §6 of the plan: doctor, build,
cluster up/down/delete, run, base build/push. Each substrate's execution model
(``container`` / ``host-binary`` / ``host-daemon``) is declared in the project's
``hostbootstrap.dhall`` and dispatched here.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import click

from . import base_image, docker_ops, prereqs, process, spec, substrate, units
from .base_image import Flavor
from .models import container as container_model
from .models import host_binary, host_daemon
from .spec import ContainerModel, HostBinaryModel, ProjectSpec, SpecError
from .substrate import Substrate, SubstrateName

_DEFAULT_SPEC_PATH: Final[Path] = Path("hostbootstrap.dhall")


def _load_spec(spec_path: Path) -> ProjectSpec:
    try:
        return spec.load(spec_path)
    except SpecError as exc:
        raise click.ClickException(str(exc)) from exc


def _detect_substrate() -> Substrate:
    try:
        return substrate.detect()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


async def _build(project_spec: ProjectSpec, sub: Substrate, project_root: Path) -> None:
    model = project_spec.model_for(sub)
    if isinstance(model, ContainerModel):
        await container_model.build(project_spec, model, sub, project_root=project_root)
    elif isinstance(model, HostBinaryModel):
        await host_binary.build(project_spec, model, sub, project_root=project_root)
    else:
        await host_daemon.build(project_spec, model, sub, project_root=project_root)


async def _run(
    project_spec: ProjectSpec,
    sub: Substrate,
    project_root: Path,
    command: Sequence[str],
) -> process.CommandResult:
    model = project_spec.model_for(sub)
    if isinstance(model, ContainerModel):
        return await container_model.run_one_shot(
            project_spec, model, sub, command, project_root=project_root
        )
    if isinstance(model, HostBinaryModel):
        return await host_binary.run_one_shot(
            project_spec, model, sub, command, project_root=project_root
        )
    return await host_daemon.run_one_shot(
        project_spec, model, sub, command, project_root=project_root
    )


async def _cluster_up(project_spec: ProjectSpec, sub: Substrate, project_root: Path) -> None:
    model = project_spec.model_for(sub)
    if isinstance(model, ContainerModel):
        if model.service:
            await container_model.start_service(project_spec, model, sub, project_root=project_root)
            click.echo(f"started service container {project_spec.project!r} (unless-stopped).")
        else:
            await container_model.build(project_spec, model, sub, project_root=project_root)
            click.echo("built project image; invoke one-shot work with `hostbootstrap run …`.")
    elif isinstance(model, HostBinaryModel):
        await host_binary.build(project_spec, model, sub, project_root=project_root)
        cmd = host_binary.resolve_command(model.handoff.up, project_root)
        await process.run_checked(list(cmd), cwd=project_root)
    else:
        await host_daemon.build(project_spec, model, sub, project_root=project_root)
        cmd = host_daemon.daemon_command(model, project_root=project_root)
        unit_path = await units.ensure(project_spec.project, cmd, project_root)
        click.echo(f"ensured host-daemon unit {unit_path}.")


async def _cluster_down(project_spec: ProjectSpec, sub: Substrate, project_root: Path) -> None:
    model = project_spec.model_for(sub)
    if isinstance(model, ContainerModel):
        await container_model.stop_service(project_spec)
    elif isinstance(model, HostBinaryModel):
        cmd = host_binary.resolve_command(model.handoff.down, project_root)
        await process.run_checked(list(cmd), cwd=project_root)
    else:
        await units.remove(project_spec.project)


async def _cluster_delete(project_spec: ProjectSpec, sub: Substrate, project_root: Path) -> None:
    model = project_spec.model_for(sub)
    if isinstance(model, ContainerModel):
        await container_model.stop_service(project_spec)
    elif isinstance(model, HostBinaryModel):
        raw = model.handoff.delete if model.handoff.delete is not None else model.handoff.down
        cmd = host_binary.resolve_command(raw, project_root)
        await process.run_checked(list(cmd), cwd=project_root)
    else:
        await units.remove(project_spec.project)


# ---------------------------------------------------------------------------
# Click app
# ---------------------------------------------------------------------------

_SPEC_OPTION = click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
    help="Path to the project's hostbootstrap.dhall",
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="hostbootstrap")
def main() -> None:
    """Host-installed CLI for the hostbootstrap base images."""


@main.command()
@_SPEC_OPTION
def doctor(spec_path: Path) -> None:
    """Detect substrate; validate + idempotently install host prerequisites."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    try:
        result = prereqs.run_doctor_sync(project_spec, sub)
    except prereqs.PrereqError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"substrate: {result.substrate.name.value} ({result.substrate.arch})")
    for message in result.messages:
        click.echo(f"  - {message}")
    if result.reboot_required:
        click.echo("reboot required; re-run `hostbootstrap doctor` after rebooting.")
        sys.exit(1)


@main.command()
@_SPEC_OPTION
def build(spec_path: Path) -> None:
    """Idempotently build the project artifact for the current substrate."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    project_root = spec_path.resolve().parent
    asyncio.run(_build(project_spec, sub, project_root))


@main.group()
def cluster() -> None:
    """Cluster lifecycle: up, down, delete."""


@cluster.command("up")
@_SPEC_OPTION
def cluster_up(spec_path: Path) -> None:
    """Bring the whole stack to running (idempotent)."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    project_root = spec_path.resolve().parent
    asyncio.run(_cluster_up(project_spec, sub, project_root))


@cluster.command("down")
@_SPEC_OPTION
def cluster_down(spec_path: Path) -> None:
    """Tear the cluster down; never deletes host .data."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    project_root = spec_path.resolve().parent
    asyncio.run(_cluster_down(project_spec, sub, project_root))
    click.echo("cluster down: host .data preserved.")


@cluster.command("delete")
@_SPEC_OPTION
def cluster_delete(spec_path: Path) -> None:
    """Thorough teardown (cluster + derived state); still never deletes .data."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    project_root = spec_path.resolve().parent
    asyncio.run(_cluster_delete(project_spec, sub, project_root))
    click.echo("cluster delete: derived state removed; host .data preserved.")


@main.command()
@_SPEC_OPTION
@click.argument("command", nargs=-1)
def run(spec_path: Path, command: tuple[str, ...]) -> None:
    """Build if needed, then dispatch ``command`` to the binary or container."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    project_root = spec_path.resolve().parent
    asyncio.run(_run(project_spec, sub, project_root, command))


# ---------------------------------------------------------------------------
# base build / push
# ---------------------------------------------------------------------------


@main.group()
def base() -> None:
    """Produce/publish the four ``basecontainer-<flavor>-<arch>`` tags."""


def _arch_default() -> str:
    return substrate.detect().arch


@base.command("build")
@click.option(
    "--flavor",
    type=click.Choice([f.value for f in Flavor]),
    default=Flavor.CPU.value,
    show_default=True,
)
@click.option(
    "--arch",
    type=click.Choice(["amd64", "arm64"]),
    default=None,
    help="Target arch; defaults to the host arch.",
)
@click.option(
    "--context",
    type=click.Path(path_type=Path),
    default=Path.cwd(),
    show_default=True,
    help="Build context root (the hostbootstrap repo).",
)
def base_build(flavor: str, arch: str | None, context: Path) -> None:
    """Build a base image locally with ``docker build``."""
    flavor_enum = Flavor(flavor)
    target_arch = arch or _arch_default()
    build_spec, _ = base_image.build_spec_for(flavor_enum, target_arch, context=context)
    asyncio.run(docker_ops.build(build_spec))
    click.echo(f"built {base_image.base_image_ref(flavor_enum, target_arch)}")


@base.command("push")
@click.option(
    "--flavor",
    type=click.Choice([f.value for f in Flavor]),
    default=Flavor.CPU.value,
    show_default=True,
)
@click.option(
    "--arch",
    type=click.Choice(["amd64", "arm64"]),
    default=None,
)
def base_push(flavor: str, arch: str | None) -> None:
    """Push the previously-built base tag to Docker Hub."""
    flavor_enum = Flavor(flavor)
    target_arch = arch or _arch_default()
    tag = base_image.base_image_ref(flavor_enum, target_arch)
    asyncio.run(docker_ops.push(tag))
    click.echo(f"pushed {tag}")


_ = SubstrateName  # re-exported for downstream importers


if __name__ == "__main__":
    main()
