#!/usr/bin/env python3
"""Demo mode — runs the full stack locally in simulator mode.

No vendor keys required. Just:

    make demo
"""

import subprocess
import sys


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def main() -> int:
    run(["make", "up"], check=True)
    run(["make", "migrate"], check=True)
    run(["make", "backfill"], check=True)
    run(["make", "collect"], check=True)
    run(["make", "run"], check=True)
    print("Demo stack running at:")
    print("  - Simulator:  http://localhost:8001")
    print("  - Grafana:    http://localhost:3000")
    print("  - Postgres:   localhost:55432")
    return 0


if __name__ == "__main__":
    sys.exit(main())
