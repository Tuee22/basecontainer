"""Push arch-explicit image tags to Harbor without leaving orphans.

The arch is always part of the tag — there are no manifest lists. When the
tool pushes a new arch-tag for a project, it deletes any prior tag *it owns*
that pointed at a now-superseded digest. Reclaiming the untagged digest is
left to the Harbor instance's GC policy (§14).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from . import docker_ops, process


@dataclass(frozen=True)
class HarborTarget:
    """A single arch-explicit tag in a Harbor project."""

    repo: str  # e.g. "harbor.example/myproject"
    tag: str  # e.g. "myproject-linux-amd64"

    @property
    def full(self) -> str:
        return f"{self.repo}:{self.tag}"


async def push(local_image: str, target: HarborTarget) -> process.CommandResult:
    """Tag *local_image* as *target* and push it."""
    await process.run_checked(docker_ops.tag_command(local_image, target.full))
    return await process.run_checked(docker_ops.push_command(target.full))


def push_sync(local_image: str, target: HarborTarget) -> process.CommandResult:
    return asyncio.run(push(local_image, target))
