from __future__ import annotations

import importlib.util
import os
import signal
import sys
import threading
import time

from screensense.config import load_settings
from screensense.core.coordinator import RootCoordinator


class ARIAApp:
    def __init__(self) -> None:
        self._shutdown_event = threading.Event()
        self._coordinator: RootCoordinator | None = None
        self._core_thread: threading.Thread | None = None
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame) -> None:
        print("\nARIA shutting down...")
        self._shutdown_event.set()
        self.stop()
        sys.exit(0)

    def start(self) -> None:
        settings = load_settings()
        start_overlay = os.getenv("START_OVERLAY_UI", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._coordinator = RootCoordinator(settings=settings)
        self._shutdown_event = self._coordinator.shutdown_event

        if not start_overlay:
            self._coordinator.run()
            return

        def _run_core() -> None:
            if self._coordinator is not None:
                self._coordinator.run()

        self._core_thread = threading.Thread(
            target=_run_core, daemon=True, name="ScreenSense-Core"
        )
        self._core_thread.start()

        if importlib.util.find_spec("PySide6") is None:
            print(
                "[ScreenSense] PySide6 not installed; overlay disabled. "
                "Set START_OVERLAY_UI=false to hide this."
            )
            self._shutdown_event.wait()
            return

        from screensense.ui.orb_overlay import run_overlay

        try:
            run_overlay(self._shutdown_event)
        finally:
            self.stop()

    def stop(self) -> None:
        if self._coordinator is not None:
            self._coordinator.stop()
        if self._core_thread is not None and self._core_thread.is_alive():
            self._core_thread.join(timeout=2.0)
        print("ARIA stopped cleanly.")


def main() -> None:
    app = ARIAApp()
    app.start()


if __name__ == "__main__":
    main()
