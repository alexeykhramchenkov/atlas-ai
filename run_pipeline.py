import subprocess
import sys

PYTHON = sys.executable

PIPELINE = [
    [PYTHON, "ingestion/orchestrators/sync_all.py"],
    [PYTHON, "normalized/orchestrators/normalization_all.py"],
    [PYTHON, "snapshots/orchestrators/snapshots_all.py"],
    [PYTHON, "metrics/builders/orchestrators/metrics_all.py"],
]

for command in PIPELINE:
    print(f"\n{'=' * 80}")
    print("PYTHONPATH=. " + " ".join(command))
    print(f"{'=' * 80}\n")

    result = subprocess.run(command)

    if result.returncode != 0:
        print(f"\nFAILED: {' '.join(command)}")
        sys.exit(result.returncode)

print("\nPIPELINE FINISHED SUCCESSFULLY")
