#!/usr/bin/env python3
"""Automate the saved local integration. Nonzero exit on partial success or failure."""
import argparse
import sys
import time
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Replay all source records")
    parser.add_argument("--export", type=Path, help="Write CSV after successful completion")
    args = parser.parse_args()
    try:
        with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10, headers={"X-Toolkit-Request": "1"}) as client:
            response = client.post("/api/runs", json={"full": args.full})
            if response.status_code != 202:
                print("Could not start synchronization. Inspect the local UI.", file=sys.stderr)
                return 1
            run_id = response.json()["id"]
            # Scheduler-friendly deadline. A longer active job remains visible in the UI.
            for _ in range(600):
                response = client.get("/api/runs/" + run_id)
                response.raise_for_status()
                run = response.json()
                if run["status"] != "running":
                    print(f"{run_id[:8]} {run['status']}: {run['inserted']} inserted, {run['updated']} updated, {run['unchanged']} unchanged")
                    if run["status"] != "completed":
                        print("Inspect the execution log and resume in the UI.", file=sys.stderr)
                        return 1
                    if args.export:
                        result = client.get("/api/export/csv")
                        result.raise_for_status()
                        args.export.write_bytes(result.content)
                    return 0
                time.sleep(.5)
            print("Still running after five minutes. Inspect the UI before scheduling another run.", file=sys.stderr)
            return 2
    except httpx.HTTPError:
        print("Local toolkit unavailable. Start scripts/run.py first.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
