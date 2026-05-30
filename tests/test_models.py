"""Unit tests for the execution models: pure helpers + recorded runners."""

from __future__ import annotations

from pathlib import Path

import pytest

from hostbootstrap.models import container, host_binary, host_daemon
from hostbootstrap.spec import (
    BuildSpec,
    ContainerModel,
    Flavor,
    HostDaemonModel,
    HostReqs,
    Mount,
    ProjectSpec,
)
from hostbootstrap.substrate import Substrate, SubstrateName


def _spec(model: object) -> ProjectSpec:
    return ProjectSpec(
        project="proj",
        substrates={SubstrateName.LINUX_CPU: model},  # type: ignore[dict-item]
        source_path=Path("/proj/hostbootstrap.dhall"),
    )


LINUX = Substrate(SubstrateName.LINUX_CPU, "amd64")
APPLE = Substrate(SubstrateName.APPLE_SILICON, "arm64")


# --- pure helpers ---------------------------------------------------------

def test_resolve_host_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/me")
    assert container.resolve_host_path("${HOME}/.docker/config.json", Path("/proj")) == (
        "/home/me/.docker/config.json"
    )
    assert container.resolve_host_path("/var/run/docker.sock", Path("/proj")) == "/var/run/docker.sock"
    assert container.resolve_host_path("./.data", Path("/proj")) == "/proj/.data"


def test_image_tag() -> None:
    assert container.image_tag(_spec(None), LINUX) == "proj:linux-cpu-amd64"


def test_resolve_command_absolutizes_build_token() -> None:
    assert host_binary.resolve_command(".build/x serve --port 8080", Path("/proj")) == (
        "/proj/.build/x",
        "serve",
        "--port",
        "8080",
    )
    assert host_binary.resolve_command("/usr/bin/x a", Path("/proj")) == ("/usr/bin/x", "a")
    assert host_binary.resolve_command("plaincmd a", Path("/proj")) == ("plaincmd", "a")


def test_daemon_command() -> None:
    model = HostDaemonModel(build=BuildSpec("c", HostReqs()), daemon=".build/proj serve")
    assert host_daemon.daemon_command(model, project_root=Path("/proj")) == ("/proj/.build/proj", "serve")


# --- recorded runners -----------------------------------------------------

async def test_container_build_injects_base_image(
    recorded_commands: list[tuple[str, ...]], project_root: Path
) -> None:
    model = ContainerModel(dockerfile=Path("docker/x.Dockerfile"), flavor=Flavor.CPU, service=False, mounts=())
    tag = await container.build(_spec(model), model, LINUX, project_root=project_root)
    assert tag == "proj:linux-cpu-amd64"
    (build_cmd,) = recorded_commands
    assert "BASE_IMAGE=docker.io/tuee22/hostbootstrap:basecontainer-cpu-amd64" in build_cmd
    assert "proj:linux-cpu-amd64" in build_cmd


async def test_container_start_service(
    recorded_commands: list[tuple[str, ...]], project_root: Path
) -> None:
    model = ContainerModel(
        dockerfile=Path("docker/x.Dockerfile"),
        flavor=Flavor.CPU,
        service=True,
        mounts=(Mount("./.data", "/opt/proj/.data", False),),
    )
    await container.start_service(_spec(model), model, LINUX, project_root=project_root)
    flat = [" ".join(c) for c in recorded_commands]
    assert any(c.startswith("docker build") for c in flat)
    assert any("docker rm -f proj" in c for c in flat)
    run = next(c for c in flat if "docker run" in c)
    assert "-d" in run.split() and "--restart unless-stopped" in run and "--name proj" in run
    assert f"{project_root}/.data:/opt/proj/.data" in run


async def test_container_run_one_shot(
    recorded_commands: list[tuple[str, ...]], project_root: Path
) -> None:
    model = ContainerModel(dockerfile=Path("d"), flavor=Flavor.CPU, service=False, mounts=())
    await container.run_one_shot(_spec(model), model, LINUX, ("echo", "hi"), project_root=project_root)
    run = next(" ".join(c) for c in recorded_commands if "docker run" in " ".join(c))
    assert "--rm" in run and run.endswith("echo hi")


async def test_host_binary_apple_builds_on_host(
    recorded_commands: list[tuple[str, ...]], project_root: Path
) -> None:
    build = BuildSpec("cabal install --installdir .build exe:proj", HostReqs(ghc=True))
    path = await host_binary.build_binary(_spec(None), build, APPLE, project_root=project_root)
    assert path == project_root / ".build" / "proj"
    (cabal_cmd,) = recorded_commands
    assert cabal_cmd[:2] == ("cabal", "install")


async def test_host_binary_linux_builds_in_container(
    recorded_commands: list[tuple[str, ...]], project_root: Path
) -> None:
    build = BuildSpec("cabal install --installdir .build exe:proj", HostReqs())
    await host_binary.build_binary(_spec(None), build, LINUX, project_root=project_root)
    (run,) = recorded_commands
    flat = " ".join(run)
    assert "docker run" in flat
    assert "basecontainer-cpu-amd64" in flat  # builds in the base image
    assert "sh -c" in flat
    assert f"{project_root}:/src" in flat
