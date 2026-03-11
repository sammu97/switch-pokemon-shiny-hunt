#!/usr/bin/env python3
import json
import sys
import time
import tty
import termios
import select
import threading
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SHELL_SCRIPT = BASE_DIR / "run_sequence.sh"
STAR_SCRIPT = BASE_DIR / "check_star.py"
STATE_FILE = BASE_DIR / "hunt_state.json"
ENCOUNTER_FILE = BASE_DIR / "encounter_count.txt"
TIME_FILE = BASE_DIR / "encounter_time.txt"

WATCH_SECONDS = 3
DEFAULT_TOTAL_RUNTIME_SECONDS = 22 * 60 * 60  # 22 hours

stop_requested = False


def format_hms(total_seconds):
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def load_state():
    if not STATE_FILE.exists():
        return {
            "attempt": 0,
            "total_runtime_seconds": DEFAULT_TOTAL_RUNTIME_SECONDS
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            "attempt": int(data.get("attempt", 0)),
            "total_runtime_seconds": int(
                data.get("total_runtime_seconds", DEFAULT_TOTAL_RUNTIME_SECONDS)
            ),
        }
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f"Warning: could not read {STATE_FILE.name}: {e}")
        return {
            "attempt": 0,
            "total_runtime_seconds": DEFAULT_TOTAL_RUNTIME_SECONDS
        }


def write_encounter_count(attempt):
    try:
        with open(ENCOUNTER_FILE, "w", encoding="utf-8") as f:
            f.write(f"Encounters: {attempt}\n")
    except OSError as e:
        print(f"Warning: could not save {ENCOUNTER_FILE.name}: {e}")


def write_time_file(total_runtime_seconds):
    try:
        with open(TIME_FILE, "w", encoding="utf-8") as f:
            f.write(f"{format_hms(total_runtime_seconds)}\n")
    except OSError as e:
        print(f"Warning: could not save {TIME_FILE.name}: {e}")


def save_state(attempt, total_runtime_seconds):
    state = {
        "attempt": int(attempt),
        "total_runtime_seconds": int(total_runtime_seconds)
    }

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        write_encounter_count(attempt)
        write_time_file(total_runtime_seconds)

    except OSError as e:
        print(f"Warning: could not save state files: {e}")


def keyboard_watcher():
    global stop_requested

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        while not stop_requested:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    stop_requested = True
                    print("\nESC pressed. Stopping after current step...")
                    break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def time_updater(previous_runtime, start_time):
    global stop_requested

    while not stop_requested:
        session_runtime = int(time.time() - start_time)
        current_total = previous_runtime + session_runtime

        write_time_file(current_total)

        # also keep JSON in sync if you want runtime persisted live
        current_attempt = load_state()["attempt"]
        save_state(current_attempt, current_total)

        time.sleep(1)


def run_shell_script():
    print("\nRunning run_sequence.sh ...")
    result = subprocess.run(
        ["/bin/zsh", str(SHELL_SCRIPT)],
        cwd=BASE_DIR
    )
    return result.returncode


def run_star_check():
    print(f"Watching for shiny star for {WATCH_SECONDS} seconds...")
    result = subprocess.run(
        [
            sys.executable,
            str(STAR_SCRIPT),
            "--watch-seconds",
            str(WATCH_SECONDS)
        ],
        cwd=BASE_DIR
    )
    return result.returncode


def main():
    global stop_requested

    print("Press ESC at any time to stop.\n")

    state = load_state()
    completed_attempts = state["attempt"]
    previous_runtime = state["total_runtime_seconds"]

    save_state(completed_attempts, previous_runtime)

    watcher = threading.Thread(target=keyboard_watcher, daemon=True)
    watcher.start()

    start_time = time.time()
    attempt = completed_attempts + 1

    print(f"Loaded saved attempt count: {completed_attempts}")
    print(f"Loaded total runtime: {format_hms(previous_runtime)}")
    print(f"Starting at attempt #{attempt}")

    timer_thread = threading.Thread(
        target=time_updater,
        args=(previous_runtime, start_time),
        daemon=True
    )
    timer_thread.start()

    try:
        while not stop_requested:
            print("\n" + "=" * 50)
            print(f"Attempt #{attempt}")
            print("=" * 50)

            shell_rc = run_shell_script()
            if shell_rc != 0:
                print(f"run_sequence.sh failed with code {shell_rc}")
                break

            if stop_requested:
                break

            detect_rc = run_star_check()

            session_runtime = int(time.time() - start_time)
            total_runtime = previous_runtime + session_runtime

            if detect_rc == 0:
                save_state(attempt, total_runtime)
                print("\n✨ SHINY STAR DETECTED — STOPPING BOT ✨")
                print("Save it manually on the Switch.")
                print(f"Saved attempt count: {attempt}")
                break
            elif detect_rc == 1:
                print("No star found. Looping again...")
                save_state(attempt, total_runtime)
                print(f"Saved attempt count: {attempt}")
            else:
                print(f"Detector failed with code {detect_rc}")
                break

            attempt += 1

    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C.")
    finally:
        stop_requested = True

        session_runtime = int(time.time() - start_time)
        total_runtime = previous_runtime + session_runtime
        last_saved = load_state()["attempt"]

        save_state(last_saved, total_runtime)

        print("\nBot stopped.")
        print(f"Last saved attempt: {last_saved}")
        print(f"Session runtime: {format_hms(session_runtime)}")
        print(f"Total runtime: {format_hms(total_runtime)}")


if __name__ == "__main__":
    main()