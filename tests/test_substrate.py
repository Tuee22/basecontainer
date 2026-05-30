"""Unit tests for substrate detection."""

from __future__ import annotations

import platform

import pytest

from hostbootstrap import substrate
from hostbootstrap.substrate import SubstrateName


@pytest.mark.parametrize(
    ("machine", "expected"),
    [("x86_64", "amd64"), ("amd64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64")],
)
def test_docker_arch_mapping(
    monkeypatch: pytest.MonkeyPatch, machine: str, expected: str
) -> None:
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert substrate._docker_arch() == expected


def test_unknown_arch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "machine", lambda: "sparc")
    with pytest.raises(RuntimeError):
        substrate._docker_arch()


def test_detect_apple_silicon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    assert substrate.detect() == substrate.Substrate(SubstrateName.APPLE_SILICON, "arm64")


def test_detect_darwin_intel_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    with pytest.raises(RuntimeError):
        substrate.detect()


def test_detect_linux_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(substrate, "_has_nvidia_gpu", lambda: False)
    assert substrate.detect() == substrate.Substrate(SubstrateName.LINUX_CPU, "amd64")


def test_detect_linux_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(substrate, "_has_nvidia_gpu", lambda: True)
    assert substrate.detect() == substrate.Substrate(SubstrateName.LINUX_GPU, "arm64")


def test_detect_unknown_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Plan9")
    with pytest.raises(RuntimeError):
        substrate.detect()
