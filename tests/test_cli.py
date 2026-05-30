"""CLI smoke tests (no docker, no host mutation)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from hostbootstrap import cli


def test_help_lists_commands_and_omits_push() -> None:
    result = CliRunner().invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    for command in ("doctor", "build", "cluster", "run", "base"):
        assert command in result.output
    assert "push" not in result.output


def test_push_command_removed() -> None:
    result = CliRunner().invoke(cli.main, ["push"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_cluster_subcommands() -> None:
    result = CliRunner().invoke(cli.main, ["cluster", "--help"])
    assert result.exit_code == 0
    for verb in ("up", "down", "delete"):
        assert verb in result.output


def test_build_missing_spec_fails_cleanly(tmp_path: Path) -> None:
    missing = tmp_path / "hostbootstrap.dhall"
    result = CliRunner().invoke(cli.main, ["build", "--spec", str(missing)])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_default_spec_path_is_dhall() -> None:
    assert cli._DEFAULT_SPEC_PATH == Path("hostbootstrap.dhall")
