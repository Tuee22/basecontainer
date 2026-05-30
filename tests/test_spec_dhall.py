"""Contract tests: real dhall-to-json + the shipped dhall/package.dhall.

These exercise the headline guarantee — illegal states are unrepresentable — by
loading fixtures through the actual Dhall type-checker. They are skipped when a
dhall-to-json binary cannot be provisioned (e.g. offline CI).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hostbootstrap import spec
from hostbootstrap.spec import ContainerModel, HostBinaryModel, HostDaemonModel, SpecError
from hostbootstrap.substrate import SubstrateName

pytestmark = pytest.mark.dhall

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dhall"


def test_valid_container(require_dhall: Path) -> None:
    ps = spec.load(FIXTURES / "valid" / "container.dhall")
    assert isinstance(ps.substrates[SubstrateName.LINUX_CPU], ContainerModel)


def test_valid_service_container(require_dhall: Path) -> None:
    ps = spec.load(FIXTURES / "valid" / "service_container.dhall")
    model = ps.substrates[SubstrateName.LINUX_CPU]
    assert isinstance(model, ContainerModel)
    assert model.service is True
    assert {m.container for m in model.mounts} == {"/opt/demo/.data", "/var/run/docker.sock"}


def test_valid_host_binary(require_dhall: Path) -> None:
    ps = spec.load(FIXTURES / "valid" / "host_binary.dhall")
    model = ps.substrates[SubstrateName.LINUX_CPU]
    assert isinstance(model, HostBinaryModel)
    assert model.handoff.up == ".build/demo cluster up"
    assert model.handoff.delete is None


def test_valid_host_daemon(require_dhall: Path) -> None:
    ps = spec.load(FIXTURES / "valid" / "host_daemon.dhall")
    model = ps.substrates[SubstrateName.APPLE_SILICON]
    assert isinstance(model, HostDaemonModel)
    assert model.daemon == ".build/demo inference --serve"
    assert model.build.host.metal is True


def test_valid_mixed(require_dhall: Path) -> None:
    ps = spec.load(FIXTURES / "valid" / "mixed.dhall")
    assert isinstance(ps.substrates[SubstrateName.APPLE_SILICON], HostDaemonModel)
    assert isinstance(ps.substrates[SubstrateName.LINUX_GPU], ContainerModel)
    assert ps.substrates[SubstrateName.LINUX_GPU].flavor is spec.Flavor.CUDA  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "fixture",
    ["daemon_on_container", "missing_daemon", "mounts_on_host_binary", "bad_flavor"],
)
def test_illegal_states_are_type_errors(require_dhall: Path, fixture: str) -> None:
    with pytest.raises(SpecError):
        spec.load(FIXTURES / "invalid" / f"{fixture}.dhall")
