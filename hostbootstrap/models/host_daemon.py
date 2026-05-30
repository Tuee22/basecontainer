"""``model: host-daemon`` (§9.4, §9.5).

A long-running **host-native** daemon must run on this substrate — typically
Apple-silicon Metal/Tart inference that cannot run in a container. hostbootstrap
builds the binary (and any declared container counterpart) and, on ``cluster
up``, wraps the declared ``daemon`` command in a **system-level** service unit
(a LaunchDaemon on macOS, a system-scope systemd unit on Linux) so it survives
reboots and starts before any user logs in. ``cluster down`` removes the unit.

This is the only model that creates a service unit, because ``daemon`` is the
only field unique to it (and the Dhall schema makes it required here).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from hostbootstrap import process
from hostbootstrap.spec import HostDaemonModel, ProjectSpec
from hostbootstrap.substrate import Substrate

from . import container, host_binary


async def build(
    spec: ProjectSpec,
    model: HostDaemonModel,
    substrate: Substrate,
    *,
    project_root: Path,
) -> Path:
    """Build the host binary and, if declared, the container counterpart."""
    path = await host_binary.build_binary(spec, model.build, substrate, project_root=project_root)
    if model.container is not None:
        await container.build_artifact(spec, model.container, substrate, project_root=project_root)
    return path


def daemon_command(model: HostDaemonModel, *, project_root: Path) -> tuple[str, ...]:
    """The host daemon command, with a leading ``.build/…`` token absolutized."""
    return host_binary.resolve_command(model.daemon, project_root)


async def run_one_shot(
    spec: ProjectSpec,
    model: HostDaemonModel,
    substrate: Substrate,
    command: Sequence[str],
    *,
    project_root: Path,
) -> process.CommandResult:
    path = await build(spec, model, substrate, project_root=project_root)
    return await process.run_checked([str(path), *command], cwd=project_root)
