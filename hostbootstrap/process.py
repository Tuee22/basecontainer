"""Async subprocess wrapper.

A thin layer over :mod:`asyncio.create_subprocess_exec` returning a frozen
:class:`CommandResult`. Output is streamed to the parent process's stdout/stderr
in real time (so long-running builds show progress live) while also being
captured into the result for later inspection.

``run_checked`` raises :class:`CommandError` on a non-zero exit (fail-fast).
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandError(RuntimeError):
    def __init__(self, result: CommandResult) -> None:
        super().__init__(f"command failed ({result.returncode}): {' '.join(result.args)}")
        self.result = result


async def _drain(
    stream: asyncio.StreamReader | None,
    sink_lines: list[str],
    mirror: TextIO,
) -> None:
    if stream is None:
        return
    while True:
        chunk = await stream.readline()
        if not chunk:
            return
        text = chunk.decode("utf-8", errors="replace")
        sink_lines.append(text)
        mirror.write(text)
        mirror.flush()


async def run(
    cmd: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    quiet: bool = False,
) -> CommandResult:
    """Run *cmd* asynchronously, streaming output and capturing the result."""

    effective_env: Mapping[str, str] | None
    if env is None:
        effective_env = None
    else:
        merged = dict(os.environ)
        merged.update(env)
        effective_env = merged

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd is not None else None,
        env=dict(effective_env) if effective_env is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    out_lines: list[str] = []
    err_lines: list[str] = []

    out_sink = open(os.devnull, "w") if quiet else sys.stdout  # noqa: SIM115
    err_sink = open(os.devnull, "w") if quiet else sys.stderr  # noqa: SIM115

    try:
        await asyncio.gather(
            _drain(process.stdout, out_lines, out_sink),
            _drain(process.stderr, err_lines, err_sink),
        )
        returncode = await process.wait()
    finally:
        if quiet:
            out_sink.close()
            err_sink.close()

    return CommandResult(
        args=tuple(cmd),
        returncode=returncode,
        stdout="".join(out_lines),
        stderr="".join(err_lines),
    )


async def run_checked(
    cmd: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    quiet: bool = False,
) -> CommandResult:
    result = await run(cmd, cwd=cwd, env=env, quiet=quiet)
    if not result.ok:
        raise CommandError(result)
    return result
