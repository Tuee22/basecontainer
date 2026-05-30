"""Unit tests for spec parsing/validation against crafted JSON (no real Dhall)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hostbootstrap import spec
from hostbootstrap.spec import (
    ContainerModel,
    HostBinaryModel,
    HostDaemonModel,
    SpecError,
)
from hostbootstrap.substrate import Substrate, SubstrateName


def _container(dockerfile: str = "d", **over: object) -> dict[str, object]:
    payload: dict[str, object] = {"dockerfile": dockerfile, "flavor": "Cpu", "service": False}
    payload.update(over)
    return {"tag": "Container", "container": payload}


def _entry(sub: str, model: dict[str, object]) -> dict[str, object]:
    return {"substrate": sub, "model": model}


def _load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data: object) -> spec.ProjectSpec:
    path = tmp_path / "hostbootstrap.dhall"
    path.write_text("-- placeholder; to_json is monkeypatched\n")
    monkeypatch.setattr(spec.dhall_tool, "to_json", lambda _p: data)
    return spec.load(path)


def test_parse_all_three_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = {
        "project": "demo",
        "substrates": [
            _entry("linux-cpu", _container(service=True, mounts=[{"host": "./.data", "container": "/d", "ro": False}])),
            _entry(
                "linux-gpu",
                {
                    "tag": "HostBinary",
                    "hostBinary": {
                        "build": {"cabal": "cabal install exe:demo", "host": {"ghc": True, "tart": False, "metal": False}},
                        "handoff": {"up": ".build/demo up", "down": ".build/demo down", "delete": None},
                    },
                },
            ),
            _entry(
                "apple-silicon",
                {
                    "tag": "HostDaemon",
                    "hostDaemon": {
                        "build": {"cabal": "c", "host": {"ghc": True, "tart": True, "metal": True}},
                        "daemon": ".build/demo serve",
                    },
                },
            ),
        ],
    }
    ps = _load(monkeypatch, tmp_path, data)
    assert ps.project == "demo"
    cpu = ps.substrates[SubstrateName.LINUX_CPU]
    assert isinstance(cpu, ContainerModel) and cpu.service and cpu.mounts[0].container == "/d"
    assert isinstance(ps.substrates[SubstrateName.LINUX_GPU], HostBinaryModel)
    daemon = ps.substrates[SubstrateName.APPLE_SILICON]
    assert isinstance(daemon, HostDaemonModel) and daemon.daemon == ".build/demo serve"
    assert daemon.build.host.metal is True


def test_container_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ps = _load(
        monkeypatch,
        tmp_path,
        {"project": "p", "substrates": [_entry("linux-cpu", {"tag": "Container", "container": {"dockerfile": "d"}})]},
    )
    model = ps.substrates[SubstrateName.LINUX_CPU]
    assert isinstance(model, ContainerModel)
    assert model.flavor is spec.Flavor.CPU and model.service is False and model.mounts == ()


def test_duplicate_substrate_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = {"project": "p", "substrates": [_entry("linux-cpu", _container()), _entry("linux-cpu", _container())]}
    with pytest.raises(SpecError, match="more than once"):
        _load(monkeypatch, tmp_path, data)


def test_unknown_substrate_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="unknown substrate"):
        _load(monkeypatch, tmp_path, {"project": "p", "substrates": [_entry("freebsd", _container())]})


def test_empty_substrates_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="at least one"):
        _load(monkeypatch, tmp_path, {"project": "p", "substrates": []})


def test_unknown_tag_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="unknown model"):
        _load(monkeypatch, tmp_path, {"project": "p", "substrates": [_entry("linux-cpu", {"tag": "Nope"})]})


def test_bad_flavor_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="unknown flavor"):
        _load(monkeypatch, tmp_path, {"project": "p", "substrates": [_entry("linux-cpu", _container(flavor="Gpu"))]})


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="not found"):
        spec.load(tmp_path / "nope.dhall")


def test_model_for_undeclared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ps = _load(monkeypatch, tmp_path, {"project": "p", "substrates": [_entry("linux-cpu", _container())]})
    with pytest.raises(SpecError, match="does not declare substrate"):
        ps.model_for(Substrate(SubstrateName.APPLE_SILICON, "arm64"))


def test_narrowers() -> None:
    with pytest.raises(SpecError):
        spec._as_map([1], where="x")
    with pytest.raises(SpecError):
        spec._as_str(5, where="x")
    with pytest.raises(SpecError):
        spec._as_bool("nope", where="x")
    assert spec._as_bool(True, where="x") is True
