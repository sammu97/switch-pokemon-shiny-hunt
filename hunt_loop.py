#!/usr/bin/env python3
import json
import sys
import time
import tty
import termios
import select
import threading
from pathlib import Path
import requests
import cv2
import argparse
import os

# Local imports
from switch_control import run_starter_sequence
from star_detector import is_shiny_from_frame

# --- Config Loading ---
BASE_DIR = Path(__file__).resolve().parent
try:
    with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"FATAL: Could not load config.json: {e}")
    sys.exit(1)

# --- Constants from Config ---
STATE_FILE = BASE_DIR / "hunt_state.json"
ENCOUNTER_FILE = BASE_DIR / "encounter_count.txt"
TIME_FILE = BASE_DIR / "encounter_time.txt"
CHECKS_DIR = BASE_DIR / "shiny_checks"

SHINY_CHECK_CONFIG = CONFIG["shiny_check"]
TARGET_POKEMON = SHINY_CHECK_CONFIG["target_pokemon"]
CAPTURE_INDEX = SHINY_CHECK_CONFIG["capture_index"]
NTFY_TOPIC = CONFIG["notifications"]["ntfy_topic"]

stop_requested = False


# --- Helper Functions ---
def format_hms(total_seconds):
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def send_notification(message):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode(encoding='utf-8'),
            headers={"Title": "Shiny Bot Alert"}
        )
        print("Sent notification.")
    except requests.exceptions.RequestException as e:
        print(f"Warning: could not send notification: {e}")


# --- State Management ---
def load_state():
    if not STATE_FILE.exists():
        return {"attempt": 0, "total_runtime_seconds": 0}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "attempt": int(data.get("attempt", 0)),
            "total_runtime_seconds": int(data.get("total_runtime_seconds", 0)),
        }
    except Exception as e:
        print(f"Warning: could not read {STATE_FILE.name}: {e}")
        return {"attempt": 0, "total_runtime_seconds": 0}


def save_state(attempt, total_runtime_seconds):
    state = {"attempt": int(attempt), "total_runtime_seconds": int(total_runtime_seconds)}
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        with open(ENCOUNTER_FILE, "w", encoding="utf-8") as f:
            f.write(f"Encounters: {attempt}\n")
        with open(TIME_FILE, "w", encoding="utf-8") as f:
            f.write(f"{format_hms(total_runtime_seconds)}\n")
    except OSError as e:
        print(f"Warning: could not save state files: {e}")


# --- Background Threads ---
def keyboard_watcher():
    global stop_requested
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while not stop_requested:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                if sys.stdin.read(1) == "\x1b":
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
        current_attempt = load_state()["attempt"]
        save_state(current_attempt, current_total)
        time.sleep(1)


# --- Main Loop ---
def main():
    global stop_requested

    parser = argparse.ArgumentParser(description="Shiny hunting bot for Pokémon FireRed/LeafGreen.")
    parser.add_argument("--test-run", action="store_true", help="Run sequence once and show ROI debug windows.")
    args = parser.parse_args()

    print("Press ESC at any time to stop.\n")

    CHECKS_DIR.mkdir(exist_ok=True)
    os.chmod(CHECKS_DIR, 0o777)

    cap = cv2.VideoCapture(CAPTURE_INDEX)
    if not cap.isOpened():
        print(f"FATAL: Could not open capture device at index {CAPTURE_INDEX}.")
        sys.exit(1)
    print(f"Video capture started on device {CAPTURE_INDEX}.")

    if args.test_run:
        print("--- Performing a single test run ---")
        run_starter_sequence()
        time.sleep(2)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite("test_capture.png", frame)
            os.chmod("test_capture.png", 0o666)
            print("\nScreenshot saved as 'test_capture.png'.")

            # Use debug windows to let the user check their ROI
            is_shiny_from_frame(frame, "summary_sprite_roi", debug_windows=True)
        else:
            print("\nFailed to capture image from video device.")
        cap.release()
        return

    state = load_state()
    completed_attempts = state["attempt"]
    previous_runtime = state["total_runtime_seconds"]

    threading.Thread(target=keyboard_watcher, daemon=True).start()
    start_time = time.time()
    threading.Thread(target=time_updater, args=(previous_runtime, start_time), daemon=True).start()

    attempt = completed_attempts + 1
    print(f"Starting hunt for Pokémon #{TARGET_POKEMON} at attempt #{attempt}")

    try:
        while not stop_requested:
            print("\n" + "=" * 50)
            print(f"Attempt #{attempt}")
            print("=" * 50)

            run_starter_sequence()

            if stop_requested: break

            time.sleep(2)

            for _ in range(5):
                cap.grab()
            ret, frame = cap.read()

            if not ret:
                print("Warning: Failed to capture frame.")
                continue

            # Save the full frame
            full_img_path = str(CHECKS_DIR / f"attempt_{attempt}_full.png")
            cv2.imwrite(full_img_path, frame)
            os.chmod(full_img_path, 0o666)

            # --- NEW: Extract and save the ROI frame for live monitoring ---
            roi = SHINY_CHECK_CONFIG["summary_sprite_roi"]
            roi_box = frame[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]]

            roi_img_path = str(CHECKS_DIR / f"attempt_{attempt}_roi.png")
            if roi_box.size > 0:
                cv2.imwrite(roi_img_path, roi_box)
                os.chmod(roi_img_path, 0o666)
            else:
                print("Warning: ROI Box is empty, skipping saving ROI preview.")

            # Check for the star
            shiny_found = is_shiny_from_frame(frame, "summary_sprite_roi")

            session_runtime = int(time.time() - start_time)
            total_runtime = previous_runtime + session_runtime

            if shiny_found:
                save_state(attempt, total_runtime)
                message = f"Shiny {TARGET_POKEMON} found after {attempt} attempts!"
                print(f"\n✨ {message} — STOPPING BOT ✨")
                send_notification(message)

                # Rename the files to have the SHINY prefix so they are easy to spot
                Path(full_img_path).rename(CHECKS_DIR / f"SHINY_FOUND_attempt_{attempt}_full.png")
                if Path(roi_img_path).exists():
                    Path(roi_img_path).rename(CHECKS_DIR / f"SHINY_FOUND_attempt_{attempt}_roi.png")
                break
            else:
                print("No star found. Looping again...")
                save_state(attempt, total_runtime)

            attempt += 1

    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C.")
    finally:
        stop_requested = True
        cap.release()
        cv2.destroyAllWindows()
        if not args.test_run:
            session_runtime = int(time.time() - start_time)
            total_runtime = previous_runtime + session_runtime
            last_saved = load_state()["attempt"]
            save_state(last_saved, total_runtime)
            print("\nBot stopped.")
            print(f"Total runtime: {format_hms(total_runtime)}")


if __name__ == "__main__":
    main()