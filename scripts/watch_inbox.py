"""Inbox watcher — the trigger. Polls the simulated SU inbox and runs the shipment pipeline
the moment an email arrives. Mocks the email plumbing; the activation is the point.
"""

import time

from src import shipment, storage

POLL_SECONDS = 3


def main() -> None:
    storage.init_db()
    print(f"watching inbox every {POLL_SECONDS}s — Ctrl+C to stop")
    while True:
        try:
            for result in shipment.process_inbox(on_event=lambda s: print(f"   {s}")):
                print(f"  processed {result.shipment_id}: {result.outcome.value}")
        except Exception as e:
            print(f"  error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
