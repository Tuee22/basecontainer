"""Resolve versions/URLs/CUDA bases and build/push the four base tags.

This module is the source of truth for every value the logic-free
``docker/basecontainer.Dockerfile`` consumes. The CLI's ``base build`` /
``base push`` commands call into the helpers here.

Tag scheme (single-arch, no manifest lists; §4):

* ``basecontainer-cpu-amd64``
* ``basecontainer-cpu-arm64``
* ``basecontainer-cuda-amd64``
* ``basecontainer-cuda-arm64``
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Final

import httpx

from . import docker_ops
from .substrate import Substrate, SubstrateName


class Flavor(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


# ---------------------------------------------------------------------------
# Hostbootstrap repo / image-name conventions
# ---------------------------------------------------------------------------

HOSTBOOTSTRAP_IMAGE_REPO: Final[str] = "docker.io/tuee22/hostbootstrap"
CPU_BASE_IMAGE: Final[str] = "ubuntu:24.04"

# Pinned toolchain versions (the single-GHC line from §4).
GHC_VERSION: Final[str] = "9.12.4"
CABAL_VERSION: Final[str] = "3.16.1.0"
RUST_TOOLCHAIN: Final[str] = "stable"

# LLVM major is hardcoded against the Ubuntu 24.04 noble apt repo (latest llvm-N
# available there). Probing apt-cache from outside the container would require
# spawning a throwaway container; hardcoding keeps the Dockerfile truly
# logic-free and makes the resolved value visible at the call site.
LLVM_MAJOR: Final[str] = "19"


# ---------------------------------------------------------------------------
# Arch-to-string maps (one row per Docker arch)
# ---------------------------------------------------------------------------

_NODE_ARCH: Final[Mapping[str, str]] = {"amd64": "x64", "arm64": "arm64"}
_GHCUP_ARCH: Final[Mapping[str, str]] = {"amd64": "x86_64", "arm64": "aarch64"}
_AWS_ARCH: Final[Mapping[str, str]] = {"amd64": "x86_64", "arm64": "aarch64"}
_PULUMI_ARCH: Final[Mapping[str, str]] = {"amd64": "x64", "arm64": "arm64"}
_GO_ARCH: Final[Mapping[str, str]] = {"amd64": "amd64", "arm64": "arm64"}
_PURESCRIPT_ASSET: Final[Mapping[str, str]] = {
    "amd64": "linux64.tar.gz",
    "arm64": "linux-arm64.tar.gz",
}


# ---------------------------------------------------------------------------
# Substrate → base tag mapping (§4)
# ---------------------------------------------------------------------------


def base_tag(flavor: Flavor, arch: str) -> str:
    return f"basecontainer-{flavor.value}-{arch}"


def base_image_ref(flavor: Flavor, arch: str) -> str:
    return f"{HOSTBOOTSTRAP_IMAGE_REPO}:{base_tag(flavor, arch)}"


def substrate_to_flavor_arch(substrate: Substrate) -> tuple[Flavor, str]:
    if substrate.name is SubstrateName.APPLE_SILICON:
        return Flavor.CPU, "arm64"
    if substrate.name is SubstrateName.LINUX_GPU:
        return Flavor.CUDA, substrate.arch
    return Flavor.CPU, substrate.arch


# ---------------------------------------------------------------------------
# Version resolvers
# ---------------------------------------------------------------------------

_HTTP_TIMEOUT: Final[httpx.Timeout] = httpx.Timeout(30.0)


def _http_get_json(url: str) -> object:
    response = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    payload: object = response.json()
    return payload


def _http_get_text(url: str) -> str:
    response = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object, got {type(value).__name__}")
    return value


def _as_list(value: object) -> Sequence[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"expected a JSON array, got {type(value).__name__}")
    return value


def _str_field(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise RuntimeError(f"expected a string at {key!r}")
    return value


def resolve_node_version(arch: str) -> str:
    """Latest Node release that ships a ``linux-<arch>`` tarball."""
    node_arch = _NODE_ARCH[arch]
    platform_key = f"linux-{node_arch}"
    index = _as_list(_http_get_json("https://nodejs.org/dist/index.json"))
    for raw in index:
        entry = _as_dict(raw)
        files = entry.get("files")
        if isinstance(files, list) and platform_key in files:
            return _str_field(entry, "version")
    raise RuntimeError(f"no node release found for {platform_key}")


def _latest_release_tag(url: str) -> str:
    return _str_field(_as_dict(_http_get_json(url)), "tag_name")


def resolve_purescript_version() -> str:
    return _latest_release_tag("https://api.github.com/repos/purescript/purescript/releases/latest")


def resolve_kind_version() -> str:
    return _latest_release_tag("https://api.github.com/repos/kubernetes-sigs/kind/releases/latest")


def resolve_kubectl_version() -> str:
    return _http_get_text("https://dl.k8s.io/release/stable.txt").strip()


def resolve_helm_version() -> str:
    return _latest_release_tag("https://api.github.com/repos/helm/helm/releases/latest")


def resolve_pulumi_version() -> str:
    return _latest_release_tag("https://api.github.com/repos/pulumi/pulumi/releases/latest")


def resolve_go_version() -> str:
    """Latest stable Go release version (e.g. ``1.23.4``)."""
    data = _as_list(_http_get_json("https://go.dev/dl/?mode=json"))
    for raw in data:
        entry = _as_dict(raw)
        if entry.get("stable") is True:
            version = _str_field(entry, "version")
            return version[2:] if version.startswith("go") else version
    raise RuntimeError("no stable go release found")


_CUDA_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)-cudnn-devel-ubuntu24\.04$"
)


def _iter_cuda_tags() -> list[dict[str, object]]:
    tags: list[dict[str, object]] = []
    url: str | None = (
        "https://hub.docker.com/v2/repositories/nvidia/cuda/tags"
        "?page_size=100&name=cudnn-devel-ubuntu24.04"
    )
    while url:
        page = _as_dict(_http_get_json(url))
        results = page.get("results")
        if isinstance(results, list):
            tags.extend(_as_dict(item) for item in results)
        next_url = page.get("next")
        url = next_url if isinstance(next_url, str) else None
    return tags


def _arch_in_images(images: object, arch: str) -> bool:
    if not isinstance(images, list):
        return False
    return any(isinstance(image, dict) and image.get("architecture") == arch for image in images)


def resolve_cuda_base_image(arch: str) -> str:
    """Latest ``nvidia/cuda:*-cudnn-devel-ubuntu24.04`` with a manifest for *arch*."""
    candidates: list[tuple[tuple[int, int, int], str, object]] = []
    for tag_entry in _iter_cuda_tags():
        name_value = tag_entry.get("name")
        if not isinstance(name_value, str):
            continue
        match = _CUDA_TAG_PATTERN.match(name_value)
        if match is None:
            continue
        version = (int(match[1]), int(match[2]), int(match[3]))
        candidates.append((version, name_value, tag_entry.get("images")))

    candidates.sort(key=lambda item: item[0], reverse=True)

    for _version, name, images in candidates:
        if _arch_in_images(images, arch):
            return f"nvidia/cuda:{name}"

    raise RuntimeError(f"no nvidia/cuda cudnn-devel-ubuntu24.04 tag found with a {arch} manifest")


# ---------------------------------------------------------------------------
# Build args
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaseImageBuildArgs:
    """Every ARG the logic-free Dockerfile consumes, resolved on the host."""

    base_image: str
    image_flavor: str
    target_arch: str
    tool_arch: str
    node_arch: str
    ghcup_arch: str
    aws_arch: str
    pulumi_arch: str
    go_arch: str
    purescript_asset: str
    llvm_major: str
    ghc_version: str
    cabal_version: str
    rust_toolchain: str
    go_version: str
    go_download_url: str
    node_version: str
    node_download_url: str
    purescript_version: str
    purescript_download_url: str
    kind_version: str
    kubectl_version: str
    helm_version: str
    pulumi_version: str
    ghcup_download_url: str
    kind_download_url: str
    kubectl_download_url: str
    helm_download_url: str
    mc_download_url: str
    aws_download_url: str
    pulumi_download_url: str

    def as_build_args(self) -> dict[str, str]:
        return {
            "BASE_IMAGE": self.base_image,
            "IMAGE_FLAVOR": self.image_flavor,
            "TARGETARCH": self.target_arch,
            "TOOL_ARCH": self.tool_arch,
            "NODE_ARCH": self.node_arch,
            "GHCUP_ARCH": self.ghcup_arch,
            "AWS_ARCH": self.aws_arch,
            "PULUMI_ARCH": self.pulumi_arch,
            "LLVM_MAJOR": self.llvm_major,
            "GHC_VERSION": self.ghc_version,
            "CABAL_VERSION": self.cabal_version,
            "RUST_TOOLCHAIN": self.rust_toolchain,
            "GO_VERSION": self.go_version,
            "GO_DOWNLOAD_URL": self.go_download_url,
            "NODE_VERSION": self.node_version,
            "NODE_DOWNLOAD_URL": self.node_download_url,
            "PURESCRIPT_VERSION": self.purescript_version,
            "PURESCRIPT_DOWNLOAD_URL": self.purescript_download_url,
            "KIND_VERSION": self.kind_version,
            "KUBECTL_VERSION": self.kubectl_version,
            "HELM_VERSION": self.helm_version,
            "PULUMI_VERSION": self.pulumi_version,
            "GHCUP_DOWNLOAD_URL": self.ghcup_download_url,
            "KIND_DOWNLOAD_URL": self.kind_download_url,
            "KUBECTL_DOWNLOAD_URL": self.kubectl_download_url,
            "HELM_DOWNLOAD_URL": self.helm_download_url,
            "MC_DOWNLOAD_URL": self.mc_download_url,
            "AWS_DOWNLOAD_URL": self.aws_download_url,
            "PULUMI_DOWNLOAD_URL": self.pulumi_download_url,
        }


def compute_build_args(
    flavor: Flavor,
    arch: str,
    *,
    base_image_override: str | None = None,
) -> BaseImageBuildArgs:
    """Resolve every dynamic value for ``(flavor, arch)`` in one shot."""

    if arch not in {"amd64", "arm64"}:
        raise RuntimeError(f"unsupported arch: {arch}")

    if base_image_override is not None:
        base_image = base_image_override
    elif flavor is Flavor.CPU:
        base_image = CPU_BASE_IMAGE
    else:
        base_image = resolve_cuda_base_image(arch)

    node_arch = _NODE_ARCH[arch]
    ghcup_arch = _GHCUP_ARCH[arch]
    aws_arch = _AWS_ARCH[arch]
    pulumi_arch = _PULUMI_ARCH[arch]
    go_arch = _GO_ARCH[arch]
    purescript_asset = _PURESCRIPT_ASSET[arch]

    go_version = resolve_go_version()
    node_version = resolve_node_version(arch)
    purescript_version = resolve_purescript_version()
    kind_version = resolve_kind_version()
    kubectl_version = resolve_kubectl_version()
    helm_version = resolve_helm_version()
    pulumi_version = resolve_pulumi_version()

    go_download_url = f"https://go.dev/dl/go{go_version}.linux-{go_arch}.tar.gz"
    node_download_url = (
        f"https://nodejs.org/dist/{node_version}/node-{node_version}-linux-{node_arch}.tar.xz"
    )
    purescript_download_url = (
        f"https://github.com/purescript/purescript/releases/download/"
        f"{purescript_version}/{purescript_asset}"
    )
    ghcup_download_url = f"https://downloads.haskell.org/~ghcup/{ghcup_arch}-linux-ghcup"
    kind_download_url = f"https://kind.sigs.k8s.io/dl/{kind_version}/kind-linux-{arch}"
    kubectl_download_url = f"https://dl.k8s.io/release/{kubectl_version}/bin/linux/{arch}/kubectl"
    helm_download_url = f"https://get.helm.sh/helm-{helm_version}-linux-{arch}.tar.gz"
    mc_download_url = f"https://dl.min.io/client/mc/release/linux-{arch}/mc"
    aws_download_url = f"https://awscli.amazonaws.com/awscli-exe-linux-{aws_arch}.zip"
    pulumi_download_url = (
        f"https://get.pulumi.com/releases/sdk/pulumi-{pulumi_version}-linux-{pulumi_arch}.tar.gz"
    )

    return BaseImageBuildArgs(
        base_image=base_image,
        image_flavor=flavor.value,
        target_arch=arch,
        tool_arch=arch,
        node_arch=node_arch,
        ghcup_arch=ghcup_arch,
        aws_arch=aws_arch,
        pulumi_arch=pulumi_arch,
        go_arch=go_arch,
        purescript_asset=purescript_asset,
        llvm_major=LLVM_MAJOR,
        ghc_version=GHC_VERSION,
        cabal_version=CABAL_VERSION,
        rust_toolchain=RUST_TOOLCHAIN,
        go_version=go_version,
        go_download_url=go_download_url,
        node_version=node_version,
        node_download_url=node_download_url,
        purescript_version=purescript_version,
        purescript_download_url=purescript_download_url,
        kind_version=kind_version,
        kubectl_version=kubectl_version,
        helm_version=helm_version,
        pulumi_version=pulumi_version,
        ghcup_download_url=ghcup_download_url,
        kind_download_url=kind_download_url,
        kubectl_download_url=kubectl_download_url,
        helm_download_url=helm_download_url,
        mc_download_url=mc_download_url,
        aws_download_url=aws_download_url,
        pulumi_download_url=pulumi_download_url,
    )


# ---------------------------------------------------------------------------
# Pull / build
# ---------------------------------------------------------------------------

REPO_ROOT_DOCKERFILE: Final[Path] = Path("docker/basecontainer.Dockerfile")


def build_spec_for(
    flavor: Flavor,
    arch: str,
    *,
    context: Path,
    dockerfile: Path | None = None,
    extra_tags: tuple[str, ...] = (),
    args: BaseImageBuildArgs | None = None,
) -> tuple[docker_ops.BuildSpec, BaseImageBuildArgs]:
    """Build the ``BuildSpec`` for ``(flavor, arch)``.

    *args* is resolved lazily; pass it in to override values for testing.
    """
    resolved = args if args is not None else compute_build_args(flavor, arch)
    primary_tag = base_image_ref(flavor, arch)
    spec = docker_ops.BuildSpec(
        dockerfile=dockerfile if dockerfile is not None else context / REPO_ROOT_DOCKERFILE,
        context=context,
        tags=(primary_tag, *extra_tags),
        build_args=resolved.as_build_args(),
        pull=True,
    )
    return spec, resolved


def with_base_override(args: BaseImageBuildArgs, new_base: str) -> BaseImageBuildArgs:
    return replace(args, base_image=new_base)
