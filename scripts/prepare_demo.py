"""Create a disposable dashboard demo database without altering operational data."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("var/italix.db"))
    parser.add_argument("--destination", type=Path, default=Path("var/demo/italix-demo.db"))
    parser.add_argument("--force", action="store_true", help="Replace only the disposable demo copy")
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit(f"source database not found: {args.source}")
    if args.destination.exists() and not args.force:
        raise SystemExit(f"demo database exists: {args.destination}; pass --force to refresh it")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.source, args.destination)
    print(f"Created disposable demo database: {args.destination}")


if __name__ == "__main__":
    main()
