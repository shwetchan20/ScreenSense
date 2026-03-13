from __future__ import annotations

import os
import subprocess
import sys
import time


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def run() -> int:
    restart_delay = float(os.getenv("WATCHDOG_RESTART_DELAY_SECONDS", "3"))
    max_restarts = int(os.getenv("WATCHDOG_MAX_RESTARTS", "0"))  # 0 = infinite
    stop_on_clean_exit = _env_bool("WATCHDOG_STOP_ON_CLEAN_EXIT", True)

    restarts = 0
    while True:
        print("[Watchdog] starting ScreenSense...")
        proc = subprocess.Popen([sys.executable, "-m", "screensense.app"], cwd=".")
        proc.wait()

        code = int(proc.returncode or 0)
        print(f"[Watchdog] ScreenSense exited with code {code}")

        if stop_on_clean_exit and code == 0:
            print("[Watchdog] clean exit; stopping.")
            return 0

        restarts += 1
        if max_restarts > 0 and restarts > max_restarts:
            print(f"[Watchdog] max restarts reached ({max_restarts}); stopping.")
            return code or 1

        delay = max(0.2, restart_delay)
        print(f"[Watchdog] restarting in {delay:.1f}s...")
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(run())

