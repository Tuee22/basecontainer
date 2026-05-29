"""Docker command builders and async runners.

Pure functions assemble the argument lists (so they are trivially testable and
re-orderable); the runners just hand the result to :mod:`hostbootstrap.process`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from . import process

_DOCKER: Final[str] = "docker"


@dataclass(frozen=True)
class BuildSpec:
    """Inputs for a ``docker build`` invocation.

    ``build_args`` becomes one ``--build-arg KEY=VALUE`` flag per entry, in the
    iteration order of the mapping; ``tags`` becomes one ``--tag`` flag per tag.
    """

    dockerfile: Path
    context: Path
    tags: tuple[str, ...]
    build_args: Mapping[str, str]
    target: str | None = None
    pull: bool = True


def build_command(spec: BuildSpec) -> tuple[str, ...]:
    cmd: list[str] = [_DOCKER, "build"]
    for key, value in spec.build_args.items():
        cmd.extend(["--build-arg", f"{key}={value}"])
    for tag in spec.tags:
        cmd.extend(["--tag", tag])
    if spec.target is not None:
        cmd.extend(["--target", spec.target])
    if spec.pull:
        cmd.append("--pull")
    cmd.extend(["--file", str(spec.dockerfile)])
    cmd.append(str(spec.context))
    return tuple(cmd)


@dataclass(frozen=True)
class RunSpec:
    """Inputs for a ``docker run`` invocation."""

    image: str
    command: tuple[str, ...] = ()
    name: str | None = None
    detach: bool = False
    rm: bool = False
    restart: str | None = None  # e.g. "unless-stopped"
    env: Mapping[str, str] = ()  # type: ignore[assignment]
    mounts: Sequence[tuple[str, str, bool]] = ()  # (host, container, read_only)
    network: str | None = None
    extra: tuple[str, ...] = ()


def run_command(spec: RunSpec) -> tuple[str, ...]:
    cmd: list[str] = [_DOCKER, "run"]
    if spec.detach:
        cmd.append("-d")
    if spec.rm:
        cmd.append("--rm")
    if spec.name is not None:
        cmd.extend(["--name", spec.name])
    if spec.restart is not None:
        cmd.extend(["--restart", spec.restart])
    if spec.network is not None:
        cmd.extend(["--network", spec.network])
    for key, value in dict(spec.env).items():
        cmd.extend(["-e", f"{key}={value}"])
    for host, container, read_only in spec.mounts:
        suffix = ":ro" if read_only else ""
        cmd.extend(["-v", f"{host}:{container}{suffix}"])
    cmd.extend(spec.extra)
    cmd.append(spec.image)
    cmd.extend(spec.command)
    return tuple(cmd)


def push_command(tag: str) -> tuple[str, ...]:
    return (_DOCKER, "push", tag)


def tag_command(source: str, target: str) -> tuple[str, ...]:
    return (_DOCKER, "tag", source, target)


def image_exists_command(tag: str) -> tuple[str, ...]:
    return (_DOCKER, "image", "inspect", tag)


async def build(spec: BuildSpec) -> process.CommandResult:
    return await process.run_checked(build_command(spec))


async def push(tag: str) -> process.CommandResult:
    return await process.run_checked(push_command(tag))


async def image_exists(tag: str) -> bool:
    result = await process.run(image_exists_command(tag), quiet=True)
    return result.ok
