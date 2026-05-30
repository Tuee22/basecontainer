"""Unit tests for the pure docker command builders."""

from __future__ import annotations

from pathlib import Path

from hostbootstrap import docker_ops


def test_build_command_full() -> None:
    spec = docker_ops.BuildSpec(
        dockerfile=Path("docker/app.Dockerfile"),
        context=Path("/proj"),
        tags=("app:linux-cpu-amd64", "app:latest"),
        build_args={"BASE_IMAGE": "base:tag", "FOO": "bar"},
        target="builder",
        pull=True,
    )
    assert docker_ops.build_command(spec) == (
        "docker",
        "build",
        "--build-arg",
        "BASE_IMAGE=base:tag",
        "--build-arg",
        "FOO=bar",
        "--tag",
        "app:linux-cpu-amd64",
        "--tag",
        "app:latest",
        "--target",
        "builder",
        "--pull",
        "--file",
        "docker/app.Dockerfile",
        "/proj",
    )


def test_build_command_minimal_no_pull_no_target() -> None:
    spec = docker_ops.BuildSpec(
        dockerfile=Path("D"),
        context=Path("."),
        tags=("t",),
        build_args={},
        pull=False,
    )
    cmd = docker_ops.build_command(spec)
    assert "--pull" not in cmd
    assert "--target" not in cmd
    assert cmd[-2:] == ("D", ".") or cmd[-1] == "."


def test_run_command_one_shot_rm_with_mounts() -> None:
    spec = docker_ops.RunSpec(
        image="img",
        command=("echo", "hi"),
        rm=True,
        mounts=(("/h", "/c", False), ("/secret", "/s", True)),
    )
    cmd = docker_ops.run_command(spec)
    assert cmd[:3] == ("docker", "run", "--rm")
    assert "-v" in cmd
    assert "/h:/c" in cmd
    assert "/secret:/s:ro" in cmd
    assert cmd[-3:] == ("img", "echo", "hi")


def test_run_command_detached_service() -> None:
    spec = docker_ops.RunSpec(
        image="img",
        detach=True,
        restart="unless-stopped",
        name="proj",
        env={"K": "V"},
        network="host",
        extra=("-w", "/src"),
    )
    cmd = docker_ops.run_command(spec)
    assert "-d" in cmd
    assert ("--restart", "unless-stopped") == cmd[cmd.index("--restart") : cmd.index("--restart") + 2]
    assert ("--name", "proj") == cmd[cmd.index("--name") : cmd.index("--name") + 2]
    assert ("--network", "host") == cmd[cmd.index("--network") : cmd.index("--network") + 2]
    assert "K=V" in cmd
    assert cmd[-3:] == ("-w", "/src", "img")
    assert "--rm" not in cmd


def test_push_tag_inspect_commands() -> None:
    assert docker_ops.push_command("r:t") == ("docker", "push", "r:t")
    assert docker_ops.tag_command("a", "b") == ("docker", "tag", "a", "b")
    assert docker_ops.image_exists_command("x") == ("docker", "image", "inspect", "x")
