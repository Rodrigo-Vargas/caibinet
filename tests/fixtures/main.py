#!/usr/bin/env python3
"""Entry point for the data pipeline."""

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, default=Path("out"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    print(f"Processing {args.input} → {args.output}")


if __name__ == "__main__":
    main()
