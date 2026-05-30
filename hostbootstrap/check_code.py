"""``check-code`` entrypoint: ruff → black → mypy(strict), fail-fast."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from typing import Final

_PACKAGES: Final[tuple[str, ...]] = ("hostbootstrap", "stubs")


def _run(cmd: Sequence[str]) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=False).returncode


def main() -> int:
    for step in (
        ("ruff", "check", *_PACKAGES),
        ("black", "--check", *_PACKAGES),
        # `stubs/` is on mypy_path for resolution, not a check target; mypy
        # errors on an empty directory, so only the package is type-checked.
        ("mypy", "hostbootstrap"),
    ):
        rc = _run(step)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
