"""``test-all`` entrypoint: run the full hostbootstrap test suite.

This is the supported way to run the tests. Invoking ``pytest`` directly is
refused by ``tests/conftest.py`` (it checks the ``HOSTBOOTSTRAP_TEST_ALL``
sentinel this entrypoint sets), so the suite always runs through one command
with one configuration. Extra arguments are forwarded to pytest, e.g.
``poetry run test-all -k docker_ops -q``.
"""

from __future__ import annotations

import os
import subprocess
import sys

_SENTINEL: str = "HOSTBOOTSTRAP_TEST_ALL"


def main() -> int:
    env = dict(os.environ)
    env[_SENTINEL] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", *sys.argv[1:]],
        env=env,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
