"""``hostbootstrap`` Click application.

The single entrypoint installed on every downstream host (via
``pip install git+…``). Commands implement §6 of the plan: doctor, build,
push, cluster up/down/delete, run, base build/push.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import click

from . import base_image, docker_ops, harbor, prereqs, process, spec, substrate
from .base_image import Flavor
from .models import host_binary, multi_substrate, outer_container
from .spec import ModelName, ProjectSpec, SpecError
from .substrate import Substrate, SubstrateName

_DEFAULT_SPEC_PATH: Final[Path] = Path("hostbootstrap.yaml")


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
    substrate_spec = project_spec.substrate_for(sub)
    if substrate_spec.model is ModelName.OUTER_CONTAINER:
        await outer_container.build(project_spec, sub, project_root=project_root)
    elif substrate_spec.model is ModelName.HOST_BINARY:
        await host_binary.build(project_spec, sub, project_root=project_root)
    elif substrate_spec.model is ModelName.MULTI_SUBSTRATE:
        await multi_substrate.build(project_spec, sub, project_root=project_root)
    else:
        raise click.ClickException(f"unknown model: {substrate_spec.model}")


async def _run(
    project_spec: ProjectSpec,
    sub: Substrate,
    project_root: Path,
    command: Sequence[str],
) -> process.CommandResult:
    substrate_spec = project_spec.substrate_for(sub)
    if substrate_spec.model is ModelName.OUTER_CONTAINER:
        return await outer_container.run_one_shot(
            project_spec, sub, command, project_root=project_root
        )
    if substrate_spec.model is ModelName.HOST_BINARY:
        return await host_binary.run_one_shot(
            project_spec, sub, command, project_root=project_root
        )
    if substrate_spec.model is ModelName.MULTI_SUBSTRATE:
        return await multi_substrate.run_one_shot(
            project_spec, sub, command, project_root=project_root
        )
    raise click.ClickException(f"unknown model: {substrate_spec.model}")


# ---------------------------------------------------------------------------
# Click app
# ---------------------------------------------------------------------------

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="hostbootstrap")
def main() -> None:
    """Host-installed CLI for the basecontainer base images."""


@main.command()
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
    help="Path to the project's hostbootstrap.yaml",
)
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
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
)
def build(spec_path: Path) -> None:
    """Idempotently build the project artifact for the current substrate."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    project_root = spec_path.resolve().parent
    asyncio.run(_build(project_spec, sub, project_root))


@main.command()
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
)
def push(spec_path: Path) -> None:
    """Idempotently push the arch-explicit custom image to Harbor."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    image_tag = f"{project_spec.project}:{sub.name.value}-{sub.arch}"
    target = harbor.HarborTarget(
        repo=project_spec.container.harbor.repo,
        tag=f"{project_spec.project}-{sub.name.value}-{sub.arch}",
    )
    harbor.push_sync(image_tag, target)


@main.group()
def cluster() -> None:
    """Cluster lifecycle: up, down, delete."""


@cluster.command("up")
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
)
def cluster_up(spec_path: Path) -> None:
    """Bring the whole stack to running (idempotent)."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    project_root = spec_path.resolve().parent
    asyncio.run(_build(project_spec, sub, project_root))
    # cluster bring-up + Harbor publish + host-daemon launchd/systemd unit are
    # the project binary's responsibility (§9.7); the CLI hands off here.
    click.echo("cluster build complete; project binary takes over from here.")


@cluster.command("down")
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
)
def cluster_down(spec_path: Path) -> None:
    """Tear the cluster down; never deletes host .data."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    container_name = project_spec.project
    asyncio.run(process.run([
        "docker", "rm", "-f", container_name,
    ], quiet=True))
    _ = sub
    click.echo("cluster down: stopped long-running containers; .data preserved.")


@cluster.command("delete")
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
)
def cluster_delete(spec_path: Path) -> None:
    """Thorough teardown (cluster + derived state); still never deletes .data."""
    project_spec = _load_spec(spec_path)
    sub = _detect_substrate()
    container_name = project_spec.project
    asyncio.run(process.run([
        "docker", "rm", "-f", container_name,
    ], quiet=True))
    _ = sub
    click.echo("cluster delete: derived state removed; host .data preserved.")


@main.command()
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SPEC_PATH,
    show_default=True,
)
@click.argument("command", nargs=-1)
def run(spec_path: Path, command: tuple[str, ...]) -> None:
    """Idempotent run: trigger ``cluster up`` then dispatch ``command``."""
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
