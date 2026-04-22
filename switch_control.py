import json
import random
import time
import socket
from pathlib import Path
import requests
from urllib.parse import urlparse

# --- Config Loading ---
BASE_DIR = Path(__file__).resolve().parent
with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

PICO_URL = CONFIG["pico_server"]["url"]
TIMING = CONFIG["timing"]


# --- Core Control Functions ---

def press_button(button: str, delay: float = None):
    """Sends a button press command to the Switch using a raw socket for maximum reliability."""
    if delay is None:
        delay = TIMING["default_time"]

    try:
        parsed_url = urlparse(PICO_URL)
        host = parsed_url.hostname
        port = parsed_url.port

        # JITTER: Randomize how long the button is physically held down (80ms - 160ms)
        hold_time = random.randint(80, 160)
        body = f"press {button} {hold_time}"

        request = (
            f"POST /cmd HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"User-Agent: curl/8.7.1\r\n"
            f"Accept: */*\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Content-Type: application/x-www-form-urlencoded\r\n"
            f"\r\n"
            f"{body}"
        )

        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall(request.encode("utf-8"))
            sock.recv(1024)

    except Exception as e:
        print(f"Error pressing button {button}: {e}")
        time.sleep(5)

    time.sleep(delay)


def reset_game():
    """Resets the game via the pico server."""
    print("Resetting game")
    try:
        requests.post(f"{PICO_URL}/reset", timeout=5)
    except requests.RequestException as e:
        print(f"Reset failed: {e}")
        time.sleep(5)


def wait(seconds: float, max_jitter_seconds: float = 0.2):
    """Pauses execution for a specified number of seconds, with capped random jitter."""
    raw_jitter = random.uniform(-0.10, 0.15) * seconds
    capped_jitter = max(-max_jitter_seconds, min(raw_jitter, max_jitter_seconds))
    actual_wait = max(0.1, seconds + capped_jitter)

    print(f"Waiting {actual_wait:.3f}s")
    time.sleep(actual_wait)


# --- Sequence ---

def run_starter_sequence():
    """Executes the full sequence for a single starter shiny hunt attempt."""
    print("\nStarting new starter sequence...")

    reset_game()
    wait(TIMING["boot_to_title_screen_delay"])

    # Initial boot seed variation
    max_delay = TIMING.get("random_delay_max_seconds", 3.0)
    seed_delay = random.uniform(0.5, max_delay)
    print(f"Seed delay: {seed_delay:.3f}s")
    time.sleep(seed_delay)

    for _ in range(5):
        press_button("+", TIMING["load_time"])

    press_button("+", 1.0)
    wait(1)

    print("Navigating main menu...")
    for _ in range(7):
        press_button("A", TIMING["text_time"])

    print("Selecting starter...")
    for _ in range(6):
        press_button("A", TIMING["text_time"])

    press_button("A", 1.0)

    print("Declining nickname...")
    press_button("B", 0.5)
    press_button("B", 0.5)

    print("Waiting for rival...")
    for _ in range(4):
        press_button("B", 0.5)

    for _ in range(6):
        press_button("B", 1.0)

    press_button("B", 1.5)

    press_button("+", 1.5)
    press_button("A", 1.0)
    press_button("A", 0.5)
    press_button("A", 1.0)
    press_button("A", 0.0)

    print("Sequence complete. Check for shiny 👀")


if __name__ == "__main__":
    print("Starting shiny hunting loop...")
    while True:
        run_starter_sequence()