"""Run tons of bots"""
import argparse
import os
import random
import sys
import time
import subprocess
from collections import defaultdict

from src.util.osm_dir import OSM_DIR

# TODO: make this more flexible than just a hardcoded start point

def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("region", choices=os.listdir(OSM_DIR))
    parser.add_argument("--stationary", default=0, type=int)
    parser.add_argument("--ramble", default=0, type=int)
    parser.add_argument("--interval", default=1.0, type=float, help="time to wait before starting another")
    return parser


def main() -> None:
    # play errbody and log outputs
    parser = get_parser()
    args = parser.parse_args()

    if not args.stationary and not args.ramble:
        raise ValueError("No bots running huh?")

    procs = defaultdict(list)
    for _ in range(args.stationary):
        pass

    for idx in range(args.ramble):
        procs["ramble"].append(subprocess.Popen(
                [
                    sys.executable,
                    os.path.join(os.getcwd(), "src", "process", "run_bot.py"),
                    args.region,
                    "ramble",
                    "--speed",
                    "1.5"  # TODO: configure
                ],
                stdout=open(os.path.join("logs", f"ramble-{idx}.log"), 'w+'),
                stderr=open(os.path.join("logs", f"ramble-{idx}.err"), 'w+'),
            )
        )
        time.sleep(args.interval)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
        #for proclist in procs.values():
        #    for proc in proclist:
        #        proc: subprocess.Popen = proc
        #        proc.


if __name__ == "__main__":
    main()
