#!/usr/bin/env python3
"""Keepalive commit — pushes a no-op commit weekly to prevent GitHub
disabling scheduled workflows after 60 idle days."""

import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def main() -> int:
    ts = subprocess.run(
        ["date", "+%Y-%m-%d %H:%M:%S"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    Path(".keepalive").touch()
    _run(["git", "add", ".keepalive"])
    _run(
        [
            "git",
            "commit",
            "--allow-empty",
            "-m",
            f"keepalive: {ts}",
        ],
        check=False,
    )
    _run(["git", "push"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
