"""Command-line entry point: python -m src.oil_prices from the repository root."""

import argparse
import sys
from pathlib import Path

import requests

from .collector import run

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect city oil prices.")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "regions.json")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--province", help="Only collect this six-digit province code.")
    args = parser.parse_args(argv)

    with requests.Session() as session:
        code = run(args.config, args.data_dir, session=session, province_code=args.province)
    return code


if __name__ == "__main__":
    sys.exit(main())
