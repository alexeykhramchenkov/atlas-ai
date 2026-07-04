

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SCHEDULER_PATH = PROJECT_ROOT / "normalized" / "orchestrators" / "normalization_scheduler.py"
WORKER_PATH = PROJECT_ROOT / "normalized" / "orchestrators" / "normalization_worker.py"


def run_script(script_path: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=PROJECT_ROOT,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(PROJECT_ROOT)},
        text=True,
        capture_output=True,
    )

    output = ""

    if result.stdout:
        print(result.stdout, end="")
        output += result.stdout

    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
        output += result.stderr

    if result.returncode != 0:
        raise RuntimeError(f"Script failed: {script_path}")

    return output


def main() -> None:
    print("Starting normalization scheduler...")
    run_script(SCHEDULER_PATH)

    print("Starting normalization worker loop...")

    processed_jobs = 0

    while True:
        output = run_script(WORKER_PATH)

        if "No pending normalization jobs" in output:
            break

        processed_jobs += 1

    print(f"Normalization all finished. Jobs processed: {processed_jobs}")


if __name__ == "__main__":
    main()