"""Provision and invoke a native ``dhall-to-json`` binary.

hostbootstrap installs as pure Python (``pip install git+…``) and parses each
project's ``hostbootstrap.dhall`` by shelling out to the official, statically
linked ``dhall-json`` release binary. We do **not** depend on the ``dhall`` PyPI
wheel: it ships no CPython 3.12 wheel, so it would compile from a Rust sdist on
the user's host.

Resolution order (``ensure``):

1. a ``dhall-to-json`` already on ``PATH`` (e.g. ``brew install dhall-json``);
2. otherwise download the pinned release asset for the host platform into
   ``~/.cache/hostbootstrap/`` and verify it against a pinned SHA-256.

Dhall's own type-checker enforces the schema's union/illegal-state guarantees
while rendering to JSON, so by the time we ``json.loads`` the output the shape
is already valid; :mod:`hostbootstrap.spec` only runs the residual cross-field
checks Dhall cannot express.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

_RELEASE_TAG: Final[str] = "1.42.2"
_DHALL_JSON_VERSION: Final[str] = "1.7.12"
_EXE: Final[str] = "dhall-to-json"


class DhallToolError(RuntimeError):
    """Raised when ``dhall-to-json`` cannot be provisioned or fails to run."""


@dataclass(frozen=True)
class _Asset:
    filename: str
    sha256: str


# Pinned `dhall-json` release assets (github.com/dhall-lang/dhall-haskell), keyed
# by (system, normalized-arch). SHA-256s verified at pin time; bump together with
# `_RELEASE_TAG` / `_DHALL_JSON_VERSION`.
_ASSETS: Final[dict[tuple[str, str], _Asset]] = {
    ("Darwin", "arm64"): _Asset(
        f"dhall-json-{_DHALL_JSON_VERSION}-aarch64-darwin.tar.bz2",
        "761048afa225dc9978b9fb742cc9d4feee104f2656aefe37b6a6f157862b77dd",
    ),
    ("Darwin", "amd64"): _Asset(
        f"dhall-json-{_DHALL_JSON_VERSION}-x86_64-darwin.tar.bz2",
        "f6b0bc2f120e5ade2c4c789555237cb4a0b4611fb2455f2a16a3bde4a441e589",
    ),
    ("Linux", "amd64"): _Asset(
        f"dhall-json-{_DHALL_JSON_VERSION}-x86_64-linux.tar.bz2",
        "acbada5e29ecc9b6a723c3f390beb76b9db26df81546d1f472415a2f387bc457",
    ),
}

_ARCH_ALIASES: Final[dict[str, str]] = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

_HTTP_TIMEOUT: Final[httpx.Timeout] = httpx.Timeout(120.0)


def _platform_key() -> tuple[str, str]:
    system = platform.system()
    raw_arch = platform.machine().lower()
    arch = _ARCH_ALIASES.get(raw_arch, raw_arch)
    return system, arch


def _cache_dir() -> Path:
    root = os.environ.get("XDG_CACHE_HOME")
    base = Path(root) if root else Path.home() / ".cache"
    return base / "hostbootstrap" / "dhall-json" / _DHALL_JSON_VERSION


def _download_and_extract(asset: _Asset, dest: Path) -> None:
    url = (
        "https://github.com/dhall-lang/dhall-haskell/releases/download/"
        f"{_RELEASE_TAG}/{asset.filename}"
    )
    try:
        response = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DhallToolError(f"could not download {url}: {exc}") from exc

    payload = response.content
    digest = hashlib.sha256(payload).hexdigest()
    if digest != asset.sha256:
        raise DhallToolError(
            f"checksum mismatch for {asset.filename}: " f"expected {asset.sha256}, got {digest}"
        )

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:bz2") as tar:
        member = next(
            (m for m in tar.getmembers() if m.isfile() and m.name.endswith(f"bin/{_EXE}")),
            None,
        )
        if member is None:
            raise DhallToolError(f"{asset.filename} does not contain bin/{_EXE}")
        extracted = tar.extractfile(member)
        if extracted is None:
            raise DhallToolError(f"could not read bin/{_EXE} from {asset.filename}")
        binary = extracted.read()

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".partial")
    tmp.write_bytes(binary)
    tmp.chmod(0o755)
    tmp.replace(dest)


def ensure() -> Path:
    """Return a path to a runnable ``dhall-to-json``, provisioning it if needed."""
    on_path = shutil.which(_EXE)
    if on_path is not None:
        return Path(on_path)

    target = _cache_dir() / _EXE
    if target.is_file() and os.access(target, os.X_OK):
        return target

    key = _platform_key()
    asset = _ASSETS.get(key)
    if asset is None:
        system, arch = key
        raise DhallToolError(
            f"no prebuilt dhall-to-json for {system}/{arch}. "
            "Install it manually (e.g. `brew install dhall-json`) so it is on PATH."
        )
    _download_and_extract(asset, target)
    return target


def to_json(dhall_path: Path) -> object:
    """Render *dhall_path* to a JSON value (type-checked by ``dhall-to-json``)."""
    binary = ensure()
    try:
        result = subprocess.run(
            [str(binary), "--file", str(dhall_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise DhallToolError(f"could not exec {binary}: {exc}") from exc
    if result.returncode != 0:
        raise DhallToolError(result.stderr.strip() or "dhall-to-json failed")
    data: object = json.loads(result.stdout)
    return data
