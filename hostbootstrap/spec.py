"""Parse and validate ``hostbootstrap.dhall`` into frozen dataclasses.

The schema is the Dhall package under ``dhall/`` (see
``documents/engineering/schema.md``). Dhall's type-checker already guarantees
the per-substrate union is well-formed — a ``daemon`` can only appear under the
``HostDaemon`` variant, ``mounts``/``service`` only under ``Container``, and so
on — so by the time :func:`load` sees the rendered JSON the shape is valid. This
module maps that JSON into frozen dataclasses and performs the few residual
cross-field checks Dhall cannot express (no duplicate substrate; the detected
substrate must be declared). Every failure raises :class:`SpecError`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from . import dhall_tool
from .substrate import Substrate, SubstrateName


class SpecError(RuntimeError):
    """Raised when ``hostbootstrap.dhall`` is missing or invalid."""


class Model(StrEnum):
    CONTAINER = "container"
    HOST_BINARY = "host-binary"
    HOST_DAEMON = "host-daemon"


class Flavor(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


@dataclass(frozen=True)
class Mount:
    host: str
    container: str
    read_only: bool = False


@dataclass(frozen=True)
class HostReqs:
    ghc: bool = False
    tart: bool = False
    metal: bool = False


@dataclass(frozen=True)
class BuildSpec:
    cabal: str
    host: HostReqs


@dataclass(frozen=True)
class Handoff:
    up: str
    down: str
    delete: str | None = None


@dataclass(frozen=True)
class ContainerArtifact:
    dockerfile: Path
    flavor: Flavor


@dataclass(frozen=True)
class ContainerModel:
    """``model: container`` — build a thin image and run it (no host unit)."""

    dockerfile: Path
    flavor: Flavor
    service: bool
    mounts: tuple[Mount, ...]

    kind: Model = Model.CONTAINER


@dataclass(frozen=True)
class HostBinaryModel:
    """``model: host-binary`` — build a host binary, hand off its lifecycle."""

    build: BuildSpec
    handoff: Handoff
    container: ContainerArtifact | None = None

    kind: Model = Model.HOST_BINARY


@dataclass(frozen=True)
class HostDaemonModel:
    """``model: host-daemon`` — build + run a host daemon under a system unit."""

    build: BuildSpec
    daemon: str
    container: ContainerArtifact | None = None

    kind: Model = Model.HOST_DAEMON


ModelSpec = ContainerModel | HostBinaryModel | HostDaemonModel


@dataclass(frozen=True)
class ProjectSpec:
    project: str
    substrates: Mapping[SubstrateName, ModelSpec]
    source_path: Path

    def model_for(self, substrate: Substrate) -> ModelSpec:
        if substrate.name not in self.substrates:
            raise SpecError(
                f"hostbootstrap.dhall does not declare substrate {substrate.name.value!r}"
            )
        return self.substrates[substrate.name]


# ---------------------------------------------------------------------------
# JSON narrowing helpers (the rendered Dhall is plain JSON)
# ---------------------------------------------------------------------------


def _as_map(value: object, *, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise SpecError(f"{where}: expected an object, got {type(value).__name__}")
    return value


def _as_list(value: object, *, where: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise SpecError(f"{where}: expected a list, got {type(value).__name__}")
    return value


def _as_str(value: object, *, where: str) -> str:
    if not isinstance(value, str):
        raise SpecError(f"{where}: expected a string, got {type(value).__name__}")
    return value


def _as_bool(value: object, *, where: str) -> bool:
    if not isinstance(value, bool):
        raise SpecError(f"{where}: expected a boolean, got {type(value).__name__}")
    return value


def _flavor(value: object, *, where: str) -> Flavor:
    try:
        return Flavor(_as_str(value, where=where).lower())
    except ValueError as exc:
        raise SpecError(f"{where}: unknown flavor {value!r}") from exc


def _mount(value: object, *, where: str) -> Mount:
    mapping = _as_map(value, where=where)
    return Mount(
        host=_as_str(mapping.get("host"), where=f"{where}.host"),
        container=_as_str(mapping.get("container"), where=f"{where}.container"),
        read_only=_as_bool(mapping.get("ro", False), where=f"{where}.ro"),
    )


def _host_reqs(value: object, *, where: str) -> HostReqs:
    mapping = _as_map(value, where=where)
    return HostReqs(
        ghc=_as_bool(mapping.get("ghc", False), where=f"{where}.ghc"),
        tart=_as_bool(mapping.get("tart", False), where=f"{where}.tart"),
        metal=_as_bool(mapping.get("metal", False), where=f"{where}.metal"),
    )


def _build(value: object, *, where: str) -> BuildSpec:
    mapping = _as_map(value, where=where)
    return BuildSpec(
        cabal=_as_str(mapping.get("cabal"), where=f"{where}.cabal"),
        host=_host_reqs(mapping.get("host", {}), where=f"{where}.host"),
    )


def _handoff(value: object, *, where: str) -> Handoff:
    mapping = _as_map(value, where=where)
    delete_raw = mapping.get("delete")
    delete = None if delete_raw is None else _as_str(delete_raw, where=f"{where}.delete")
    return Handoff(
        up=_as_str(mapping.get("up"), where=f"{where}.up"),
        down=_as_str(mapping.get("down"), where=f"{where}.down"),
        delete=delete,
    )


def _container_artifact(value: object, *, where: str) -> ContainerArtifact | None:
    if value is None:
        return None
    mapping = _as_map(value, where=where)
    return ContainerArtifact(
        dockerfile=Path(_as_str(mapping.get("dockerfile"), where=f"{where}.dockerfile")),
        flavor=_flavor(mapping.get("flavor", "cpu"), where=f"{where}.flavor"),
    )


def _model(value: object, *, where: str) -> ModelSpec:
    mapping = _as_map(value, where=where)
    tag = _as_str(mapping.get("tag"), where=f"{where}.tag")

    if tag == "Container":
        payload = _as_map(mapping.get("container"), where=f"{where}.container")
        mounts_raw = _as_list(payload.get("mounts", []), where=f"{where}.container.mounts")
        return ContainerModel(
            dockerfile=Path(
                _as_str(payload.get("dockerfile"), where=f"{where}.container.dockerfile")
            ),
            flavor=_flavor(payload.get("flavor", "cpu"), where=f"{where}.container.flavor"),
            service=_as_bool(payload.get("service", False), where=f"{where}.container.service"),
            mounts=tuple(
                _mount(entry, where=f"{where}.container.mounts[{i}]")
                for i, entry in enumerate(mounts_raw)
            ),
        )
    if tag == "HostBinary":
        payload = _as_map(mapping.get("hostBinary"), where=f"{where}.hostBinary")
        return HostBinaryModel(
            build=_build(payload.get("build"), where=f"{where}.hostBinary.build"),
            handoff=_handoff(payload.get("handoff"), where=f"{where}.hostBinary.handoff"),
            container=_container_artifact(
                payload.get("container"), where=f"{where}.hostBinary.container"
            ),
        )
    if tag == "HostDaemon":
        payload = _as_map(mapping.get("hostDaemon"), where=f"{where}.hostDaemon")
        return HostDaemonModel(
            build=_build(payload.get("build"), where=f"{where}.hostDaemon.build"),
            daemon=_as_str(payload.get("daemon"), where=f"{where}.hostDaemon.daemon"),
            container=_container_artifact(
                payload.get("container"), where=f"{where}.hostDaemon.container"
            ),
        )
    raise SpecError(f"{where}.tag: unknown model {tag!r}")


def load(path: Path) -> ProjectSpec:
    if not path.is_file():
        raise SpecError(f"hostbootstrap.dhall not found at {path}")

    try:
        rendered = dhall_tool.to_json(path)
    except dhall_tool.DhallToolError as exc:
        raise SpecError(f"could not evaluate {path}: {exc}") from exc

    data = _as_map(rendered, where="<root>")
    project = _as_str(data.get("project"), where="project")

    entries = _as_list(data.get("substrates"), where="substrates")
    if not entries:
        raise SpecError("substrates: at least one substrate must be declared")

    substrates: dict[SubstrateName, ModelSpec] = {}
    for index, raw_entry in enumerate(entries):
        where = f"substrates[{index}]"
        entry = _as_map(raw_entry, where=where)
        name_str = _as_str(entry.get("substrate"), where=f"{where}.substrate")
        try:
            name = SubstrateName(name_str)
        except ValueError as exc:
            raise SpecError(f"{where}.substrate: unknown substrate {name_str!r}") from exc
        if name in substrates:
            raise SpecError(f"substrate {name.value!r} is declared more than once")
        substrates[name] = _model(entry.get("model"), where=f"{where}.model")

    return ProjectSpec(project=project, substrates=substrates, source_path=path)
