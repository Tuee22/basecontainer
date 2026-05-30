"""Shared fixtures and the direct-pytest blocker.

The suite must be run via ``poetry run test-all`` (see ``hostbootstrap/test_all.py``),
which sets the ``HOSTBOOTSTRAP_TEST_ALL`` sentinel. Running ``pytest`` directly is
refused here so there is exactly one supported entry point and configuration.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from hostbootstrap import dhall_tool, process


def pytest_configure(config: pytest.Config) -> None:
    if os.environ.get("HOSTBOOTSTRAP_TEST_ALL") != "1":
        raise pytest.UsageError(
            "Run the test suite with `poetry run test-all` "
            "(not pytest directly). test-all forwards extra args to pytest."
        )


REPO_ROOT = Path(__file__).resolve().parent.parent
DHALL_PACKAGE = REPO_ROOT / "dhall" / "package.dhall"


@pytest.fixture
def recorded_commands(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Replace process.run/run_checked with recorders; return the captured argv list."""
    calls: list[tuple[str, ...]] = []

    async def _fake(cmd: object, **_: object) -> process.CommandResult:
        argv = tuple(str(part) for part in cmd)  # type: ignore[union-attr]
        calls.append(argv)
        return process.CommandResult(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(process, "run", _fake)
    monkeypatch.setattr(process, "run_checked", _fake)
    return calls


@pytest.fixture(scope="session")
def dhall_binary() -> Path | None:
    """A provisioned dhall-to-json, or None if it cannot be obtained (offline)."""
    try:
        return dhall_tool.ensure()
    except dhall_tool.DhallToolError:
        return None


@pytest.fixture
def require_dhall(dhall_binary: Path | None) -> Path:
    if dhall_binary is None:
        pytest.skip("dhall-to-json is not available")
    return dhall_binary


@pytest.fixture
def project_root(tmp_path: Path) -> Iterator[Path]:
    """A throwaway project directory."""
    yield tmp_path
