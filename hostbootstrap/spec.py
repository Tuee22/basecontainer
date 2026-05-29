"""Parse and validate ``hostbootstrap.yaml`` into frozen dataclasses.

The schema is the one in §8 of the plan. We fail fast (raise :class:`SpecError`)
on a missing file, missing required keys, an unknown model, an unrecognised
substrate, or unexpected types.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

import yaml

from .substrate import Substrate, SubstrateName


class SpecError(RuntimeError):
    """Raised when ``hostbootstrap.yaml`` is missing or invalid."""


class ModelName(str, Enum):
    OUTER_CONTAINER = "outer-container"
    HOST_BINARY = "host-binary"
    MULTI_SUBSTRATE = "multi-substrate"


@dataclass(frozen=True)
class Mount:
    host: str
    container: str
    read_only: bool = False


@dataclass(frozen=True)
class HarborSpec:
    repo: str


@dataclass(frozen=True)
class ContainerSpec:
    dockerfile: Path
    harbor: HarborSpec


@dataclass(frozen=True)
class HostRequirements:
    ghc: bool = False
    tart: bool = False
    metal: bool = False


@dataclass(frozen=True)
class SubstrateSpec:
    name: SubstrateName
    model: ModelName
    gpu: bool = False
    host: HostRequirements = HostRequirements()
    daemon: str | None = None


@dataclass(frozen=True)
class BaseSpec:
    flavor: str  # "cpu" | "cuda"


@dataclass(frozen=True)
class ProjectSpec:
    project: str
    base: BaseSpec
    container: ContainerSpec
    mounts: tuple[Mount, ...]
    substrates: Mapping[SubstrateName, SubstrateSpec]
    source_path: Path

    def substrate_for(self, substrate: Substrate) -> SubstrateSpec:
        if substrate.name not in self.substrates:
            raise SpecError(
                f"hostbootstrap.yaml does not declare substrate {substrate.name.value!r}"
            )
        return self.substrates[substrate.name]


_SUPPORTED_FLAVORS: Final[frozenset[str]] = frozenset({"cpu", "cuda"})


def _require_mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpecError(f"{where}: expected a mapping, got {type(value).__name__}")
    return value


def _require_str(value: Any, *, where: str) -> str:
    if not isinstance(value, str):
        raise SpecError(f"{where}: expected a string, got {type(value).__name__}")
    return value


def _parse_mount(entry: Any, *, index: int) -> Mount:
    mapping = _require_mapping(entry, where=f"mounts[{index}]")
    host = _require_str(mapping.get("host"), where=f"mounts[{index}].host")
    container = _require_str(mapping.get("container"), where=f"mounts[{index}].container")
    read_only = bool(mapping.get("ro", False))
    return Mount(host=host, container=container, read_only=read_only)


def _parse_host(value: Any) -> HostRequirements:
    if value is None:
        return HostRequirements()
    mapping = _require_mapping(value, where="substrate.host")
    return HostRequirements(
        ghc=bool(mapping.get("ghc", False)),
        tart=bool(mapping.get("tart", False)),
        metal=bool(mapping.get("metal", False)),
    )


def _parse_substrate(name: str, raw: Any) -> SubstrateSpec:
    try:
        substrate_name = SubstrateName(name)
    except ValueError as exc:
        raise SpecError(f"unknown substrate {name!r}") from exc

    mapping = _require_mapping(raw, where=f"substrates.{name}")
    try:
        model = ModelName(_require_str(mapping.get("model"), where=f"substrates.{name}.model"))
    except ValueError as exc:
        raise SpecError(f"substrates.{name}.model: unknown model") from exc

    daemon = mapping.get("daemon")
    if daemon is not None and not isinstance(daemon, str):
        raise SpecError(f"substrates.{name}.daemon: must be a string command")

    return SubstrateSpec(
        name=substrate_name,
        model=model,
        gpu=bool(mapping.get("gpu", False)),
        host=_parse_host(mapping.get("host")),
        daemon=daemon,
    )


def load(path: Path) -> ProjectSpec:
    if not path.is_file():
        raise SpecError(f"hostbootstrap.yaml not found at {path}")

    raw_text = path.read_text()
    raw_yaml = yaml.safe_load(raw_text)
    data = _require_mapping(raw_yaml, where="<root>")

    project = _require_str(data.get("project"), where="project")

    base_raw = _require_mapping(data.get("base"), where="base")
    flavor = _require_str(base_raw.get("flavor"), where="base.flavor")
    if flavor not in _SUPPORTED_FLAVORS:
        raise SpecError(f"base.flavor: unsupported value {flavor!r}")

    container_raw = _require_mapping(data.get("container"), where="container")
    dockerfile = Path(
        _require_str(container_raw.get("dockerfile"), where="container.dockerfile")
    )
    harbor_raw = _require_mapping(container_raw.get("harbor"), where="container.harbor")
    harbor = HarborSpec(repo=_require_str(harbor_raw.get("repo"), where="container.harbor.repo"))

    container = ContainerSpec(dockerfile=dockerfile, harbor=harbor)

    mounts_raw = data.get("mounts", []) or []
    if not isinstance(mounts_raw, list):
        raise SpecError("mounts: expected a list")
    mounts = tuple(_parse_mount(entry, index=index) for index, entry in enumerate(mounts_raw))

    substrates_raw = _require_mapping(data.get("substrates"), where="substrates")
    if not substrates_raw:
        raise SpecError("substrates: at least one substrate must be declared")
    substrates = {
        SubstrateName(name): _parse_substrate(name, raw) for name, raw in substrates_raw.items()
    }

    return ProjectSpec(
        project=project,
        base=BaseSpec(flavor=flavor),
        container=container,
        mounts=mounts,
        substrates=substrates,
        source_path=path,
    )
