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
from palette_detector import extract_palette, palette_distance, DB_PATH, clean_sprite_from_frame

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
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f"Warning: could not read {STATE_FILE.name}: {e}")
        return {"attempt": 0, "total_runtime_seconds": 0}

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
    state = {"attempt": int(attempt), "total_runtime_seconds": int(total_runtime_seconds)}
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        write_encounter_count(attempt)
        write_time_file(total_runtime_seconds)
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
        write_time_file(current_total)
        current_attempt = load_state()["attempt"]
        save_state(current_attempt, current_total)
        time.sleep(1)

# --- Main Loop ---

def main():
    global stop_requested
    
    parser = argparse.ArgumentParser(description="Shiny hunting bot for Pokémon FireRed/LeafGreen.")
    parser.add_argument("--test-run", action="store_true", help="Run the sequence once and save screenshots for ROI tuning.")
    args = parser.parse_args()

    # --- Initialization ---
    print("Press ESC at any time to stop.\n")

    # Create shiny_checks directory if it doesn't exist and set permissions
    CHECKS_DIR.mkdir(exist_ok=True)
    os.chmod(CHECKS_DIR, 0o777) # Set wide-open permissions to prevent write errors

    # Load Palette Database early to catch errors
    if not DB_PATH.exists():
        print(f"FATAL: Palette database not found at {DB_PATH}.")
        sys.exit(1)
    with open(DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)
    print("Palette database loaded.")

    # Initialize video capture
    cap = cv2.VideoCapture(CAPTURE_INDEX)
    if not cap.isOpened():
        print(f"FATAL: Could not open capture device at index {CAPTURE_INDEX}.")
        sys.exit(1)
    print(f"Video capture started on device {CAPTURE_INDEX}.")

    # --- Test Run Logic ---
    if args.test_run:
        print("--- Performing a single test run ---")
        run_starter_sequence()
        time.sleep(2) # Wait for summary screen
        
        # Flush buffer
        for _ in range(5):
            cap.grab()
            
        ret, frame = cap.read()
        if ret:
            cv2.imwrite("test_capture.png", frame)
            os.chmod("test_capture.png", 0o666) # Make it readable/writable by anyone
            print("\nScreenshot saved as 'test_capture.png'.")
            
            roi = SHINY_CHECK_CONFIG["summary_sprite_roi"]
            if roi['y2'] <= frame.shape[0] and roi['x2'] <= frame.shape[1]:
                cropped_roi = frame[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]]
                cv2.imwrite("test_capture_roi.png", cropped_roi)
                os.chmod("test_capture_roi.png", 0o666)
                print("ROI preview saved as 'test_capture_roi.png'.")
                
                cleaned_sprite = clean_sprite_from_frame(frame, "summary_sprite_roi")
                if cleaned_sprite is not None:
                    cv2.imwrite("test_capture_cleaned.png", cleaned_sprite)
                    os.chmod("test_capture_cleaned.png", 0o666)
                    print("Cleaned ROI preview saved as 'test_capture_cleaned.png'.")
            else:
                print("Warning: ROI is outside the bounds of the captured image. Cannot save ROI previews.")
        else:
            print("\nFailed to capture image from video device.")
        cap.release()
        return

    # --- Full Hunt Logic ---
    
    # Load saved state
    state = load_state()
    completed_attempts = state["attempt"]
    previous_runtime = state["total_runtime_seconds"]

    # --- First Run Reference Logic ---
    baseline_palette_path = CHECKS_DIR / "baseline_palette.json"
    baseline_palette = None
    
    if not baseline_palette_path.exists():
         print("\n--- BASELINE SETUP ---")
         print("Performing the first run to capture a baseline reference sprite.")
         print("This ensures the detector is perfectly calibrated to your capture card.")
         
         run_starter_sequence()
         time.sleep(2)
         
         # Flush the buffer by rapidly grabbing a few frames
         for _ in range(5):
             cap.grab()
             
         ret, frame = cap.read()
         if not ret:
             print("FATAL: Failed to capture frame during first run.")
             sys.exit(1)
             
         cleaned_sprite = clean_sprite_from_frame(frame, "summary_sprite_roi")
         if cleaned_sprite is None:
             print("FATAL: Could not isolate sprite during first run. Check your ROI coordinates.")
             sys.exit(1)
             
         # Save the baseline image
         baseline_img_path = CHECKS_DIR / "attempt_0_baseline.png"
         cv2.imwrite(str(baseline_img_path), cleaned_sprite)
         os.chmod(str(baseline_img_path), 0o666)
         
         # Prompt the user
         print("\nWe have captured a baseline sprite.")
         print(f"Please open and inspect the image at: {baseline_img_path}")
         print("1. Does it look like a clean, isolated sprite of the Pokémon?")
         print("2. Is it the NORMAL (non-shiny) color palette?")
         
         while True:
             response = input("Does the baseline image look correct? (y/n): ").strip().lower()
             if response == 'y':
                 print("Great! Extracting palette from baseline image...")
                 baseline_palette = extract_palette(cleaned_sprite)
                 if baseline_palette is None:
                     print("FATAL: Could not extract palette from baseline image.")
                     sys.exit(1)
                 
                 # Save the baseline palette
                 with open(baseline_palette_path, "w") as f:
                     json.dump(baseline_palette, f)
                 
                 # Treat this as attempt 1 (or the next attempt if resuming)
                 completed_attempts += 1
                 save_state(completed_attempts, previous_runtime)
                 print(f"First attempt logged as attempt #{completed_attempts}.")
                 break
             elif response == 'n':
                 print("Okay, please check your config.json ROI coordinates or restart the script.")
                 baseline_img_path.unlink(missing_ok=True)
                 sys.exit(0)
             else:
                 print("Please answer 'y' or 'n'.")
    else:
        # Load the existing baseline palette
        print("Loading baseline palette from previous run...")
        with open(baseline_palette_path, "r") as f:
            baseline_palette = json.load(f)

    # Start background threads
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
            
            # Flush the buffer by rapidly grabbing a few frames
            for _ in range(5):
                cap.grab()
            
            ret, frame = cap.read() # Now grab the fresh frame

            if not ret:
                print("Warning: Failed to capture frame.")
                continue

            cleaned_sprite = clean_sprite_from_frame(frame, "summary_sprite_roi")
            if cleaned_sprite is None:
                print("Warning: Could not create a clean sprite for analysis.")
                continue
            
            # Save the full frame and cleaned sprite for verification
            # Use os.chmod to make sure the files are easily deletable by any user
            full_img_path = str(CHECKS_DIR / f"attempt_{attempt}_full.png")
            cleaned_img_path = str(CHECKS_DIR / f"attempt_{attempt}_cleaned.png")
            
            cv2.imwrite(full_img_path, frame)
            os.chmod(full_img_path, 0o666)
            
            cv2.imwrite(cleaned_img_path, cleaned_sprite)
            os.chmod(cleaned_img_path, 0o666)

            # --- Intelligent Detection using Baseline ---
            live_palette = extract_palette(cleaned_sprite)
            if not live_palette:
                 print("Warning: Could not extract a palette from the cleaned sprite.")
                 continue

            dist_to_baseline = palette_distance(live_palette, baseline_palette)
            
            print(f"Dist to Baseline Normal: {dist_to_baseline:.2f}")

            # It's a shiny if it is significantly different from the live baseline.
            shiny_found = dist_to_baseline > 150.0

            session_runtime = int(time.time() - start_time)
            total_runtime = previous_runtime + session_runtime

            if shiny_found:
                save_state(attempt, total_runtime)
                message = f"Shiny {TARGET_POKEMON} found after {attempt} attempts! (Dist: {dist_to_baseline:.2f})"
                print(f"\n✨ {message} — STOPPING BOT ✨")
                send_notification(message)
                
                # Keep both images and add a shiny prefix
                Path(full_img_path).rename(CHECKS_DIR / f"SHINY_FOUND_attempt_{attempt}_full.png")
                Path(cleaned_img_path).rename(CHECKS_DIR / f"SHINY_FOUND_attempt_{attempt}_cleaned.png")
                break
            else:
                print("Not shiny. Looping again...")
                save_state(attempt, total_runtime)

            attempt += 1

    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C.")
    finally:
        stop_requested = True
        cap.release()
        cv2.destroyAllWindows() # Destroy any lingering OpenCV windows
        if not args.test_run:
            session_runtime = int(time.time() - start_time)
            total_runtime = previous_runtime + session_runtime
            last_saved = load_state()["attempt"]
            save_state(last_saved, total_runtime)
            print("\nBot stopped.")
            print(f"Last saved attempt: {last_saved}")
            print(f"Total runtime: {format_hms(total_runtime)}")

if __name__ == "__main__":
    main()
