"""Unit tests for system-unit rendering and platform dispatch."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from hostbootstrap import units


def test_systemd_unit_rendering() -> None:
    text = units._systemd_unit("demo", (".build/demo", "serve --port", "8080"), Path("/proj"))
    assert "Description=hostbootstrap host daemon for demo" in text
    assert "WorkingDirectory=/proj" in text
    # ExecStart is shell-quoted (the arg with a space is quoted).
    assert "ExecStart=.build/demo 'serve --port' 8080" in text
    assert "Restart=always" in text
    assert "WantedBy=multi-user.target" in text


def test_systemd_unit_name() -> None:
    assert units._systemd_unit_name("demo") == "hostbootstrap-demo.service"


def test_launchd_plist_rendering() -> None:
    text = units._launchd_plist("demo", (".build/demo", "serve"), Path("/proj"))
    assert "<string>com.hostbootstrap.demo</string>" in text
    assert "<string>.build/demo</string>" in text
    assert "<string>serve</string>" in text
    assert "<key>RunAtLoad</key>" in text and "<key>KeepAlive</key>" in text
    assert "<string>/proj</string>" in text


async def test_ensure_linux_uses_systemctl(
    monkeypatch: pytest.MonkeyPatch, recorded_commands: list[tuple[str, ...]]
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    dest = await units.ensure("demo", (".build/demo", "serve"), Path("/proj"))
    assert dest == Path("/etc/systemd/system/hostbootstrap-demo.service")
    flat = [" ".join(c) for c in recorded_commands]
    assert any("sudo install" in c for c in flat)
    assert any("systemctl daemon-reload" in c for c in flat)
    assert any("systemctl enable --now hostbootstrap-demo.service" in c for c in flat)


async def test_ensure_darwin_uses_launchctl(
    monkeypatch: pytest.MonkeyPatch, recorded_commands: list[tuple[str, ...]]
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    dest = await units.ensure("demo", (".build/demo", "serve"), Path("/proj"))
    assert dest == Path("/Library/LaunchDaemons/com.hostbootstrap.demo.plist")
    flat = [" ".join(c) for c in recorded_commands]
    assert any("launchctl bootstrap system" in c for c in flat)


async def test_remove_linux(
    monkeypatch: pytest.MonkeyPatch, recorded_commands: list[tuple[str, ...]]
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    await units.remove("demo")
    flat = [" ".join(c) for c in recorded_commands]
    assert any("systemctl disable --now hostbootstrap-demo.service" in c for c in flat)


async def test_unsupported_platform_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    with pytest.raises(units.UnitError):
        await units.ensure("demo", ("x",), Path("/p"))
