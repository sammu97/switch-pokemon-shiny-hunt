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
        # Parse the hostname and port from the PICO_URL in the config file
        parsed_url = urlparse(PICO_URL)
        host = parsed_url.hostname
        port = parsed_url.port

        # Randomize how long the button is physically held down (between 80ms and 160ms)
        hold_time = random.randint(80, 160)
        body = f"press {button} {hold_time}"

        # Construct the raw HTTP request, identical to the working curl command
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
            sock.recv(1024) # Wait for a response to ensure the command was received

    except Exception as e:
        print(f"Error pressing button {button}: {e}")
        time.sleep(5)

    time.sleep(delay)

def reset_game():
    """Resets the game via the pico server."""
    print("Resetting game")
    try:
        # This request is simple and works fine with the requests library
        requests.post(f"{PICO_URL}/reset", timeout=5)
    except requests.RequestException as e:
        print(f"Reset failed: {e}")
        time.sleep(5)


def wait(seconds: float, max_jitter_seconds: float = 0.2):
    """
    Pauses execution for a specified number of seconds, with capped random jitter.

    :param seconds: The base amount of time to wait.
    :param max_jitter_seconds: The absolute maximum time (in seconds) the jitter can add or subtract.
    """
    # Calculate a base percentage-based jitter (between -10% and +15% of the wait time)
    raw_jitter = random.uniform(-0.10, 0.15) * seconds

    # Clamp (limit) the jitter so it never exceeds your maximum allowance
    # For example, if max_jitter is 0.2, the jitter is forced to stay between -0.2 and 0.2
    capped_jitter = max(-max_jitter_seconds, min(raw_jitter, max_jitter_seconds))

    # Calculate the final wait time, ensuring it never accidentally drops below 0.1s
    actual_wait = max(0.1, seconds + capped_jitter)

    print(f"Waiting {actual_wait:.3f}s (base: {seconds}s, jitter: {capped_jitter:+.3f}s)")
    time.sleep(actual_wait)

# --- Sequence ---

def run_starter_sequence():
    """Executes the full, simplified sequence for a single starter shiny hunt attempt."""
    print("\nStarting new starter sequence...")

    reset_game()
    wait(TIMING["boot_to_title_screen_delay"])

    # 🔥 Main seed variation point
    max_delay = TIMING.get("random_delay_max_seconds", 3.0)
    seed_delay = random.uniform(0.5, max_delay)
    print(f"Seed delay: {seed_delay:.3f}s")
    time.sleep(seed_delay)

    # Load game
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

# --- Main Loop ---

if __name__ == "__main__":
    print("Starting shiny hunting loop...")

    while True:
        run_starter_sequence()
