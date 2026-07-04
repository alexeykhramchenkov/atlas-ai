

from detectors.orchestrators.detector_scheduler import DetectorScheduler
from detectors.orchestrators.detector_worker import DetectorWorker


def main():
    print("Starting detector scheduler...")
    DetectorScheduler().run()

    print("Starting detector worker loop...")
    processed = DetectorWorker().run_loop()

    print(f"Detectors all finished. Jobs processed: {processed}")


if __name__ == "__main__":
    main()