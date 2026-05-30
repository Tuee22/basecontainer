"""System-level service units for host daemons (§9.4).

Only the ``host-daemon`` model uses this. To match the ``unless-stopped`` restart
behaviour of containerised services — and to start **before any user logs in**
(headless remote SSH, §7) — the unit is always **system scope**:

* Linux  → a systemd unit in ``/etc/systemd/system/``.
* macOS  → a **LaunchDaemon** in ``/Library/LaunchDaemons/`` (never a per-user
  LaunchAgent).

Writing to those locations and (de)registering the unit is why passwordless
``sudo`` is a hard prerequisite. ``ensure`` is idempotent; ``remove`` tolerates a
missing unit.
"""

from __future__ import annotations

import platform
import shlex
import tempfile
from collections.abc import Sequence
from pathlib import Path

from . import process

_SYSTEMD_DIR = Path("/etc/systemd/system")
_LAUNCHD_DIR = Path("/Library/LaunchDaemons")


class UnitError(RuntimeError):
    """Raised when a service unit cannot be created or removed."""


def _systemd_unit_name(project: str) -> str:
    return f"hostbootstrap-{project}.service"


def _launchd_label(project: str) -> str:
    return f"com.hostbootstrap.{project}"


def _systemd_unit(project: str, command: Sequence[str], working_dir: Path) -> str:
    exec_start = " ".join(shlex.quote(part) for part in command)
    return (
        "[Unit]\n"
        f"Description=hostbootstrap host daemon for {project}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={working_dir}\n"
        f"ExecStart={exec_start}\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _launchd_plist(project: str, command: Sequence[str], working_dir: Path) -> str:
    args = "".join(f"    <string>{part}</string>\n" for part in command)
    label = _launchd_label(project)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        f"  <key>Label</key>\n  <string>{label}</string>\n"
        "  <key>ProgramArguments</key>\n  <array>\n"
        f"{args}"
        "  </array>\n"
        f"  <key>WorkingDirectory</key>\n  <string>{working_dir}</string>\n"
        "  <key>RunAtLoad</key>\n  <true/>\n"
        "  <key>KeepAlive</key>\n  <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )


async def _sudo_install(content: str, dest: Path, mode: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".unit", delete=False) as handle:
        handle.write(content)
        tmp = handle.name
    await process.run_checked(["sudo", "install", "-m", mode, tmp, str(dest)])
    await process.run_checked(["rm", "-f", tmp])


async def ensure(project: str, command: Sequence[str], working_dir: Path) -> Path:
    """Idempotently create and start the system unit; return its path."""
    system = platform.system()
    if system == "Linux":
        dest = _SYSTEMD_DIR / _systemd_unit_name(project)
        await _sudo_install(_systemd_unit(project, command, working_dir), dest, "0644")
        await process.run_checked(["sudo", "systemctl", "daemon-reload"])
        await process.run_checked(["sudo", "systemctl", "enable", "--now", dest.name])
        return dest
    if system == "Darwin":
        dest = _LAUNCHD_DIR / f"{_launchd_label(project)}.plist"
        await _sudo_install(_launchd_plist(project, command, working_dir), dest, "0644")
        # bootout first so a changed plist is reloaded cleanly (ignore failure).
        await process.run(["sudo", "launchctl", "bootout", "system", str(dest)], quiet=True)
        await process.run_checked(["sudo", "launchctl", "bootstrap", "system", str(dest)])
        return dest
    raise UnitError(f"host daemons are unsupported on {system}")


async def remove(project: str) -> None:
    """Idempotently stop and remove the system unit (no-op if absent)."""
    system = platform.system()
    if system == "Linux":
        dest = _SYSTEMD_DIR / _systemd_unit_name(project)
        await process.run(["sudo", "systemctl", "disable", "--now", dest.name], quiet=True)
        await process.run(["sudo", "rm", "-f", str(dest)], quiet=True)
        await process.run(["sudo", "systemctl", "daemon-reload"], quiet=True)
        return
    if system == "Darwin":
        dest = _LAUNCHD_DIR / f"{_launchd_label(project)}.plist"
        await process.run(["sudo", "launchctl", "bootout", "system", str(dest)], quiet=True)
        await process.run(["sudo", "rm", "-f", str(dest)], quiet=True)
        return
    raise UnitError(f"host daemons are unsupported on {system}")
