import json
import random
import time
import socket
from pathlib import Path
import requests

# --- Config Loading ---
BASE_DIR = Path(__file__).resolve().parent
with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

PICO_URL = CONFIG["pico_server"]["url"]
TIMING = CONFIG["timing"]

# --- Timing Helpers ---

def jitter(base: float, spread: float = 0.08):
    """Adds small randomness to timing."""
    return max(0, base + random.uniform(-spread, spread))

def random_pause(chance=0.3, min_s=0.1, max_s=0.4):
    """Occasional random pause to break timing patterns."""
    if random.random() < chance:
        delay = random.uniform(min_s, max_s)
        print(f"Micro delay: {delay:.3f}s")
        time.sleep(delay)

# --- Core Control Functions ---

def press_button(button: str, delay: float = None):
    if delay is None:
        delay = TIMING["default_time"]

    host = "192.168.1.95"
    port = 8080

    body = f"press {button} 120"

    request = (
        "POST /cmd HTTP/1.1\r\n"
        "Host: 192.168.1.95:8080\r\n"
        "User-Agent: curl/8.7.1\r\n"
        "Accept: */*\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "\r\n"
        f"{body}"
    )

    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall(request.encode("utf-8"))
            sock.recv(1024)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)

    time.sleep(jitter(delay))

def reset_game():
    print("Resetting game")
    try:
        requests.post(f"{PICO_URL}/reset", timeout=5)
    except requests.RequestException as e:
        print(f"Reset failed: {e}")
        time.sleep(5)

def wait(seconds: float):
    delay = jitter(seconds, 0.2)
    print(f"Waiting {delay:.3f}s")
    time.sleep(delay)

# --- Sequence ---

def run_starter_sequence():
    print("\nStarting new starter sequence...")

    reset_game()

    # 🔥 Main seed variation point
    seed_delay = random.uniform(0.5, 3.0)
    print(f"Seed delay: {seed_delay:.3f}s")
    wait(TIMING["reset_time"])
    time.sleep(seed_delay)

    # Load game
    for _ in range(5):
        press_button("+", jitter(TIMING["load_time"]))
        random_pause()

    press_button("+", jitter(1.0))
    wait(1)

    print("Navigating main menu...")
    for _ in range(7):
        press_button("A", jitter(TIMING["text_time"]))
        random_pause()

    print("Selecting starter...")
    for _ in range(6):
        press_button("A", jitter(TIMING["text_time"]))
        random_pause()

    press_button("A", jitter(1.0))

    print("Declining nickname...")
    press_button("B", jitter(0.5))
    press_button("B", jitter(0.5))

    print("Waiting for rival...")
    for _ in range(4):
        press_button("B", jitter(0.5))
        random_pause()

    for _ in range(6):
        press_button("B", jitter(1.0))
        random_pause()

    press_button("B", jitter(1.5))

    press_button("+", jitter(1.5))
    press_button("A", jitter(1.0))
    press_button("A", jitter(0.5))
    press_button("A", jitter(1.0))
    press_button("A", 0.0)

    print("Sequence complete. Check for shiny 👀")

# --- Main Loop ---

if __name__ == "__main__":
    print("Starting shiny hunting loop...")

    while True:
        run_starter_sequence()