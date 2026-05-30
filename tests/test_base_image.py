"""Unit tests for base-image tag/URL builders and JSON resolvers (no network)."""

from __future__ import annotations

import pytest

from hostbootstrap import base_image
from hostbootstrap.base_image import Flavor
from hostbootstrap.substrate import Substrate, SubstrateName


def test_base_tag_and_ref() -> None:
    assert base_image.base_tag(Flavor.CPU, "amd64") == "basecontainer-cpu-amd64"
    assert (
        base_image.base_image_ref(Flavor.CUDA, "arm64")
        == "docker.io/tuee22/hostbootstrap:basecontainer-cuda-arm64"
    )


@pytest.mark.parametrize(
    ("name", "arch", "expected"),
    [
        (SubstrateName.APPLE_SILICON, "arm64", (Flavor.CPU, "arm64")),
        (SubstrateName.LINUX_CPU, "amd64", (Flavor.CPU, "amd64")),
        (SubstrateName.LINUX_GPU, "amd64", (Flavor.CUDA, "amd64")),
    ],
)
def test_substrate_to_flavor_arch(
    name: SubstrateName, arch: str, expected: tuple[Flavor, str]
) -> None:
    assert base_image.substrate_to_flavor_arch(Substrate(name, arch)) == expected


def test_compute_build_args_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    for fn, val in [
        ("resolve_go_version", "1.23.4"),
        ("resolve_purescript_version", "v0.15.0"),
        ("resolve_kind_version", "v0.23.0"),
        ("resolve_kubectl_version", "v1.30.0"),
        ("resolve_helm_version", "v3.15.0"),
        ("resolve_pulumi_version", "v3.120.0"),
    ]:
        monkeypatch.setattr(base_image, fn, lambda v=val: v)
    monkeypatch.setattr(base_image, "resolve_node_version", lambda arch: "v22.0.0")

    args = base_image.compute_build_args(Flavor.CUDA, "amd64", base_image_override="custom:base")
    d = args.as_build_args()
    assert d["BASE_IMAGE"] == "custom:base"
    assert d["IMAGE_FLAVOR"] == "cuda"
    assert d["TARGETARCH"] == "amd64"
    assert d["GO_DOWNLOAD_URL"] == "https://go.dev/dl/go1.23.4.linux-amd64.tar.gz"
    assert "node-v22.0.0-linux-x64.tar.xz" in d["NODE_DOWNLOAD_URL"]
    assert "GO_ARCH" not in d  # go_arch is folded into the URL, not a separate arg


def test_json_narrowers_reject_bad_types() -> None:
    with pytest.raises(RuntimeError):
        base_image._as_dict([1, 2])
    with pytest.raises(RuntimeError):
        base_image._as_list({"a": 1})
    with pytest.raises(RuntimeError):
        base_image._str_field({"k": 5}, "k")
    assert base_image._str_field({"k": "v"}, "k") == "v"


def test_arch_in_images() -> None:
    images = [{"architecture": "amd64"}, {"architecture": "arm64"}]
    assert base_image._arch_in_images(images, "arm64")
    assert not base_image._arch_in_images(images, "ppc64le")
    assert not base_image._arch_in_images("not-a-list", "amd64")


def test_resolve_cuda_picks_latest_with_arch(monkeypatch: pytest.MonkeyPatch) -> None:
    tags = [
        {"name": "12.4.1-cudnn-devel-ubuntu24.04", "images": [{"architecture": "amd64"}]},
        {"name": "12.6.0-cudnn-devel-ubuntu24.04", "images": [{"architecture": "arm64"}]},
        {"name": "not-matching", "images": [{"architecture": "amd64"}]},
    ]
    monkeypatch.setattr(base_image, "_iter_cuda_tags", lambda: tags)
    # amd64 only exists on the older tag.
    assert base_image.resolve_cuda_base_image("amd64") == "nvidia/cuda:12.4.1-cudnn-devel-ubuntu24.04"
    assert base_image.resolve_cuda_base_image("arm64") == "nvidia/cuda:12.6.0-cudnn-devel-ubuntu24.04"


def test_resolve_cuda_no_match_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_image, "_iter_cuda_tags", lambda: [])
    with pytest.raises(RuntimeError):
        base_image.resolve_cuda_base_image("amd64")
